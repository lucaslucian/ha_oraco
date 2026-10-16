"""HA Oraco: read-only multi-cadence Horaco monitoring."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from time import monotonic
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_time_interval
from .api import HoracoClient, parse_info, parse_stats
from .const import DOMAIN, INTERVALS
from .mac import parse_mac_page
from .inventory import MacInventory
from .vendors import VendorCache
from .advanced import parse_sfp, parse_dhcp, parse_igmp, parse_jumbo
from .topology import build_topology
from .vlans import parse_port_vlans
from .protection import parse_isolation, parse_stp_ports, parse_storm_control
from .bridging import parse_stp_global, parse_aggregation
from .panel import register_panel
from .history import HistoryDatabase
from .traffic_guard import counter_delta, valid_counter

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


class HoracoCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass, client, entry):
        super().__init__(hass, _LOGGER, name=f"HA Oraco {client.host}",
                         update_interval=timedelta(seconds=entry.options.get("fast_interval", 30)))
        self.client = client
        self.entry = entry
        self.last = {}
        self.cache = {"device": {}, "ports": {}, "mac": {}, "sfp": {}, "network": {}}
        self.inventory = None
        self.vendors = None
        self.history_db = None
        self.diagnostics = {"endpoints": {}, "last_success": None, "last_error": None}
        self.prev_bytes = {}
        self.prev_time = None
        self.peak_rates = {"total": {"rx_bps": 0, "tx_bps": 0}, "ports": {}}
        self._ddmi_lock = asyncio.Lock()
        self._ddmi_last_attempt = float("-inf")

    async def async_refresh_ddmi(self):
        """Read-only DDMI refresh; 30-second cooldown including failed attempts."""
        if self._ddmi_lock.locked():
            return {"status": "busy", "retry_after": 30}
        async with self._ddmi_lock:
            remaining = 30 - (monotonic() - self._ddmi_last_attempt)
            if remaining > 0:
                return {"status": "rate_limited", "retry_after": max(1, int(remaining + 0.999))}
            self._ddmi_last_attempt = monotonic()
            try:
                parsed = parse_sfp(await self.client.get("/transceiver.cgi"))
            except Exception as err:
                self.diagnostics["endpoints"]["sfp"] = {
                    "status": "unavailable", "error": type(err).__name__,
                    "last_attempt": datetime.now(timezone.utc).isoformat(),
                }
                self.cache.setdefault("sfp", {}).pop("sfp", None)
                self.cache["diagnostics"] = dict(self.diagnostics)
                self.async_set_updated_data(dict(self.cache))
                return {"status": "error", "error": type(err).__name__}
            stamp = datetime.now(timezone.utc).isoformat()
            self.cache.setdefault("sfp", {})["sfp"] = parsed
            self.last["sfp"] = monotonic()
            self.diagnostics["sfp_fields"] = sorted(parsed)
            self.diagnostics["endpoints"]["sfp"] = {"status": "ok", "last_success": stamp}
            if self.history_db:
                try:
                    await self.history_db.record_snapshot("sfp", parsed)
                except Exception as err:
                    self.diagnostics["endpoints"]["sfp"]["history_error"] = type(err).__name__
                    _LOGGER.warning("HoraInfo manual DDMI history error: %s", type(err).__name__)
            self.cache["diagnostics"] = dict(self.diagnostics)
            self.async_set_updated_data(dict(self.cache))
            return {"status": "ok", "last_success": stamp}

    async def _async_update_data(self):
        now = monotonic()
        try:
            # /info.cgi contains both operational port status and static device fields.
            # Refresh fast for ports, but publish device fields only hourly.
            info, ports = parse_info(await self.client.get("/info.cgi"))
            if not ports:
                raise UpdateFailed("No ports found on switch info page")
            stats = parse_stats(await self.client.get("/port.cgi?page=stats"))
            counter_warnings = {}
            elapsed = now - self.prev_time if self.prev_time is not None else None
            for number, port in ports.items():
                port.update(stats.get(number, {}))
                old = self.prev_bytes.get(number, {})
                new_baseline = {}
                for side in ("rx", "tx"):
                    field = f"{side}_bytes"
                    current = port.get(field)
                    if not valid_counter(current):
                        counter_warnings[f"{number}:{side}"] = "missing_or_invalid"
                        continue
                    new_baseline[field] = current
                    delta, reason = counter_delta(old.get(field), current, elapsed, port.get("speed"))
                    if reason is None:
                        port[f"{side}_bps"] = round(8 * delta / elapsed, 2)
                    elif reason not in ("baseline",):
                        counter_warnings[f"{number}:{side}"] = reason
                self.prev_bytes[number] = new_baseline
            self.prev_time = now
            self.diagnostics["traffic_counters"] = counter_warnings
            for number, port in ports.items():
                peaks = self.peak_rates["ports"].setdefault(number, {"rx_bps": 0, "tx_bps": 0})
                for direction in ("rx_bps", "tx_bps"):
                    measured = port.get(direction)
                    if isinstance(measured, (int, float)) and measured >= 0:
                        peaks[direction] = max(peaks[direction], measured)
            for direction in ("rx_bps", "tx_bps"):
                total = sum(p.get(direction, 0) or 0 for p in ports.values())
                self.peak_rates["total"][direction] = max(self.peak_rates["total"][direction], total)
            self.cache["peaks"] = {
                "total": dict(self.peak_rates["total"]),
                "ports": {n: dict(values) for n, values in self.peak_rates["ports"].items()},
                "scope": "since_integration_start",
            }
            self.cache["ports"] = ports
            if self.history_db:
                try:
                    await self.history_db.record_traffic(ports)
                    history = await self.history_db.traffic_summary()
                    self.cache["peaks"] = history["peaks"]
                    self.cache["traffic_history"] = history["traffic_history"]
                    self.cache["traffic_by_port"] = history["traffic_by_port"]
                except Exception as err:
                    _LOGGER.warning("HoraInfo traffic history error: %s", type(err).__name__)
            self.diagnostics["last_success"] = datetime.now(timezone.utc).isoformat()
            self.diagnostics["last_error"] = None
            if "device" not in self.last or now - self.last["device"] >= INTERVALS["device"]:
                self.cache["device"] = info
                self.last["device"] = now
            # On first start, discover administrative disabled ports. Afterwards
            # refresh configuration at network cadence, not every fast cycle.
            if "network" not in self.last or now - self.last["network"] >= INTERVALS["network"]:
                self.last["network"] = now
                # Deliberately do not infer admin state from ambiguous firmware markup.

            plans = (
                ("sfp", 60, "/transceiver.cgi", parse_sfp),
                ("dhcp", 300, "/dhcp_snooping.cgi?page=dump", parse_dhcp),
                ("igmp", 300, "/igmp.cgi?page=dump", parse_igmp),
                ("jumbo", 3600, "/fwd.cgi?page=jumboframe", parse_jumbo),
                ("vlan_ports", INTERVALS["vlans"], "/vlan.cgi?page=port_based", parse_port_vlans),
                ("isolation", 600, "/port.cgi?page=isolation", parse_isolation),
                ("stp_ports", 600, "/loop.cgi?page=stp_port", parse_stp_ports),
                ("storm_control", 600, "/fwd.cgi?page=storm_ctrl", parse_storm_control),
                ("stp_global", 600, "/loop.cgi?page=stp_global", parse_stp_global),
                ("aggregation", 600, "/trunk.cgi?page=group", parse_aggregation),
            )
            for name, interval, path, parser in plans:
                if name not in self.last or now - self.last[name] >= interval:
                    try:
                        if name == "sfp":
                            # Share the cooldown and lock with the manual DDMI
                            # command; regular and manual polls must not burst.
                            async with self._ddmi_lock:
                                if monotonic() - self._ddmi_last_attempt < 30:
                                    continue
                                self._ddmi_last_attempt = monotonic()
                                parsed = parser(await self.client.get(path))
                        else:
                            parsed = parser(await self.client.get(path))
                        self.cache["sfp" if name == "sfp" else "network"][name] = parsed
                        if name == "sfp":
                            self.diagnostics["sfp_fields"] = sorted(parsed)
                        self.last[name] = now
                        self.diagnostics["endpoints"][name] = {
                            "status": "ok",
                            "last_success": datetime.now(timezone.utc).isoformat(),
                        }
                        if self.history_db:
                            try:
                                await self.history_db.record_snapshot(name, parsed)
                            except Exception as history_err:
                                self.diagnostics["endpoints"][name]["history_error"] = type(history_err).__name__
                                _LOGGER.warning(
                                    "HoraInfo %s snapshot failed on %s: %s",
                                    name, self.client.host, history_err,
                                )
                    except Exception as err:
                        _LOGGER.debug("%s unavailable on %s: %s", name, self.client.host, err)
                        self.diagnostics["endpoints"][name] = {"status": "unavailable", "error": type(err).__name__, "detail": str(err)[:180]}
                        if name == "sfp":
                            # Never expose stale optical values as current after a failed
                            # collection; the historical measurements remain in SQLite.
                            self.cache["sfp"].pop("sfp", None)
                        self.last[name] = now
            if self.inventory is not None and ("mac" not in self.last or now - self.last["mac"] >= 120):
                try:
                    rows, pages = parse_mac_page(await self.client.get("/mac.cgi?page=fwd_tbl"))
                    for page in range(2, pages + 1):
                        more, _ = parse_mac_page(await self.client.mac_page(page))
                        rows.extend(more)
                    legacy_saved = await self.inventory.observe(rows, self.vendors)
                    self.cache["mac"] = self.inventory.summary()
                    if self.history_db:
                        try:
                            await self.history_db.record_inventory(self.inventory.history.values())
                            self.cache["mac"].update(await self.history_db.inventory_summary())
                        except Exception as err:
                            _LOGGER.warning("HoraInfo MAC history error: %s", type(err).__name__)
                    self.last["mac"] = now
                    self.diagnostics["endpoints"]["mac"] = {"status": "ok", "last_success": datetime.now(timezone.utc).isoformat()}
                    if not legacy_saved:
                        self.diagnostics["endpoints"]["mac"]["history_error"] = "LegacyStoreSaveFailed"
                except Exception as err:
                    _LOGGER.debug("MAC table unavailable on %s: %s", self.client.host, err)
                    self.diagnostics["endpoints"]["mac"] = {"status": "unavailable", "error": type(err).__name__}
                    self.last["mac"] = now
            if self.history_db:
                try:
                    self.cache["recent_changes"] = await self.history_db.recent_changes()
                except Exception as err:
                    _LOGGER.debug("HoraInfo recent changes unavailable: %s", type(err).__name__)
            # Enrich current FDB nodes from the persistent inventory. OUI
            # reclassification may happen later than the last MAC poll, so
            # current observations alone often lack a useful manufacturer.
            topology_entries = []
            if self.inventory:
                historic = self.cache.get("mac", {}).get("mac_history_entries", [])
                by_identity = {
                    (str(row.get("vlan")), row.get("mac", "").upper()): row
                    for row in historic if row.get("mac")
                }
                for row in self.inventory.current:
                    enriched = dict(row)
                    previous = by_identity.get((str(row.get("vlan")), row.get("mac", "").upper()), {})
                    for field in ("name", "vendor"):
                        if not enriched.get(field) or enriched[field] == "Desconhecido":
                            value = previous.get(field)
                            if value and value != "Desconhecido":
                                enriched[field] = value
                    if self.vendors and (not enriched.get("vendor") or enriched["vendor"] == "Desconhecido"):
                        enriched["vendor"] = self.vendors.lookup(row["mac"])
                    topology_entries.append(enriched)
            self.cache["topology"] = build_topology(
                self.client.host, self.cache["ports"], topology_entries
            )
            self.cache["diagnostics"] = dict(self.diagnostics)
            return self.cache
        except UpdateFailed as err:
            self.diagnostics["last_error"] = str(err)
            raise
        except Exception as err:
            self.diagnostics["last_error"] = type(err).__name__
            raise UpdateFailed(f"Could not read switch {self.client.host}: {err}") from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = HoracoClient(async_get_clientsession(hass), entry.data[CONF_HOST],
                          entry.data.get(CONF_PORT, 80), entry.data[CONF_USERNAME],
                          entry.data[CONF_PASSWORD])
    coordinator = HoracoCoordinator(hass, client, entry)
    coordinator.history_db = HistoryDatabase(hass, f"{client.host}_{entry.data.get(CONF_PORT, 80)}")
    try:
        await coordinator.history_db.initialize()
    except Exception as err:
        _LOGGER.warning("HoraInfo database init error: %s", type(err).__name__)
        coordinator.history_db = None
    coordinator.inventory = MacInventory(hass, f"{client.host}_{entry.data.get(CONF_PORT, 80)}")
    await coordinator.inventory.load()
    data = hass.data.setdefault(DOMAIN, {})
    vendors = data.get("_vendors")
    if vendors is None:
        vendors = VendorCache(hass)
        await vendors.load()
        data["_vendors"] = vendors
    coordinator.vendors = vendors
    if vendors.prefixes:
        try:
            await coordinator.inventory.reclassify(vendors)
            if coordinator.history_db:
                await coordinator.history_db.reclassify_inventory(vendors)
            coordinator.cache["mac"] = coordinator.inventory.summary()
        except Exception as err:
            _LOGGER.warning("HoraInfo MAC vendor reclassification error: %s", type(err).__name__)
    if coordinator.history_db:
        try:
            await coordinator.history_db.record_inventory(coordinator.inventory.history.values())
            coordinator.cache["mac"].update(await coordinator.history_db.inventory_summary())
            previous = await coordinator.history_db.traffic_summary()
            coordinator.cache["peaks"] = previous["peaks"]
            coordinator.cache["traffic_history"] = previous["traffic_history"]
            coordinator.cache["traffic_by_port"] = previous["traffic_by_port"]
            coordinator.cache["recent_changes"] = await coordinator.history_db.recent_changes()
        except Exception as err:
            _LOGGER.warning("HoraInfo history restore error: %s", type(err).__name__)
    if not coordinator.cache["mac"]:
        coordinator.cache["mac"] = coordinator.inventory.summary()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await register_panel(hass)
    # IEEE refresh happens independently of device polling; retain existing cache on failure.
    if not data.get("_vendor_refresh_scheduled"):
        data["_vendor_refresh_scheduled"] = True
        async def refresh_oui():
            try:
                stamp = datetime.fromisoformat(vendors.last_updated) if vendors.last_updated else None
                if stamp is None or datetime.now(timezone.utc) - stamp >= timedelta(days=30):
                    count = await vendors.refresh(async_get_clientsession(hass))
                    _LOGGER.info("HoraInfo IEEE OUI prefixes available: %d", count)
                    if count:
                        for item in hass.data.get(DOMAIN, {}).values():
                            if not isinstance(item, HoracoCoordinator):
                                continue
                            await item.inventory.reclassify(vendors)
                            item.cache["mac"] = item.inventory.summary()
                            if item.history_db:
                                try:
                                    await item.history_db.reclassify_inventory(vendors)
                                    await item.history_db.record_inventory(item.inventory.history.values())
                                    item.cache["mac"].update(await item.history_db.inventory_summary())
                                except Exception as history_err:
                                    _LOGGER.warning("HoraInfo MAC vendor database update failed: %s", type(history_err).__name__)
                            item.async_set_updated_data(dict(item.cache))
            except Exception as exc:
                _LOGGER.debug("IEEE vendor registry update failed: %s", type(exc).__name__)
            finally:
                data["_vendor_refresh_scheduled"] = False
        hass.async_create_task(refresh_oui())
        if "_oui_daily_unsub" not in data:
            async def daily_oui(_now):
                if not data.get("_vendor_refresh_scheduled"):
                    data["_vendor_refresh_scheduled"] = True
                    await refresh_oui()
            data["_oui_daily_unsub"] = async_track_time_interval(
                hass, daily_oui, timedelta(days=1)
            )
    return True


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        data = hass.data[DOMAIN]
        data.pop(entry.entry_id, None)
        if not any(isinstance(v, HoracoCoordinator) for v in data.values()):
            unsubscribe = data.pop("_oui_daily_unsub", None)
            if unsubscribe:
                unsubscribe()
    return ok
