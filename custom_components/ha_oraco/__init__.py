"""HA Oraco: read-only multi-cadence Horaco monitoring."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from time import monotonic
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import HoracoClient, parse_info, parse_stats
from .const import DOMAIN, INTERVALS
from .mac import parse_mac_page
from .inventory import MacInventory
from .vendors import VendorCache
from .advanced import parse_sfp, parse_dhcp, parse_igmp, parse_jumbo
from .topology import build_topology
from .vlans import parse_port_vlans
from .firmware import parse_firmware
from .protection import parse_isolation, parse_stp_ports, parse_storm_control
from .bridging import parse_stp_global, parse_aggregation
from .panel import register_panel
from .history import HistoryDatabase

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

    async def _async_update_data(self):
        now = monotonic()
        try:
            # /info.cgi contains both operational port status and static device fields.
            # Refresh fast for ports, but publish device fields only hourly.
            info, ports = parse_info(await self.client.get("/info.cgi"))
            if not ports:
                raise UpdateFailed("No ports found on switch info page")
            stats = parse_stats(await self.client.get("/port.cgi?page=stats"))
            for number, port in ports.items():
                port.update(stats.get(number, {}))
                old = self.prev_bytes.get(number, {})
                if self.prev_time is not None and now > self.prev_time:
                    for side in ("rx", "tx"):
                        field = f"{side}_bytes"
                        if field in port and field in old and port[field] >= old[field]:
                            port[f"{side}_bps"] = round(8 * (port[field] - old[field]) / (now - self.prev_time), 2)
                self.prev_bytes[number] = {key: port[key] for key in ("rx_bytes", "tx_bytes") if key in port}
            self.prev_time = now
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
                ("firmware_page", INTERVALS["static"], "/fwug.cgi", parse_firmware),
                ("isolation", 600, "/port.cgi?page=isolation", parse_isolation),
                ("stp_ports", 600, "/loop.cgi?page=stp_port", parse_stp_ports),
                ("storm_control", 600, "/fwd.cgi?page=storm_ctrl", parse_storm_control),
                ("stp_global", 600, "/loop.cgi?page=stp_global", parse_stp_global),
                ("aggregation", 600, "/trunk.cgi?page=group", parse_aggregation),
            )
            for name, interval, path, parser in plans:
                if name not in self.last or now - self.last[name] >= interval:
                    try:
                        parsed = parser(await self.client.get(path))
                        if name == "firmware_page":
                            self.cache["device"]["firmware"] = parsed["version"]
                        else:
                            self.cache["sfp" if name == "sfp" else "network"][name] = parsed
                        self.last[name] = now
                        self.diagnostics["endpoints"][name] = {"status": "ok", "last_success": datetime.now(timezone.utc).isoformat()}
                    except Exception as err:
                        _LOGGER.debug("%s unavailable on %s: %s", name, self.client.host, err)
                        self.diagnostics["endpoints"][name] = {"status": "unavailable", "error": type(err).__name__}
                        self.last[name] = now
            if self.inventory is not None and ("mac" not in self.last or now - self.last["mac"] >= 120):
                try:
                    rows, pages = parse_mac_page(await self.client.get("/mac.cgi?page=fwd_tbl"))
                    for page in range(2, pages + 1):
                        more, _ = parse_mac_page(await self.client.mac_page(page))
                        rows.extend(more)
                    await self.inventory.observe(rows, self.vendors)
                    self.cache["mac"] = self.inventory.summary()
                    if self.history_db:
                        try:
                            await self.history_db.record_inventory(self.inventory.history.values())
                            self.cache["mac"].update(await self.history_db.inventory_summary())
                        except Exception as err:
                            _LOGGER.warning("HoraInfo MAC history error: %s", type(err).__name__)
                    self.last["mac"] = now
                    self.diagnostics["endpoints"]["mac"] = {"status": "ok", "last_success": datetime.now(timezone.utc).isoformat()}
                except Exception as err:
                    _LOGGER.debug("MAC table unavailable on %s: %s", self.client.host, err)
                    self.diagnostics["endpoints"]["mac"] = {"status": "unavailable", "error": type(err).__name__}
                    self.last["mac"] = now
            self.cache["topology"] = build_topology(self.client.host, self.cache["ports"],
                                                      self.inventory.current if self.inventory else [])
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
        await coordinator.inventory.reclassify(vendors)
        coordinator.cache["mac"] = coordinator.inventory.summary()
    if coordinator.history_db:
        try:
            await coordinator.history_db.record_inventory(coordinator.inventory.history.values())
            coordinator.cache["mac"].update(await coordinator.history_db.inventory_summary())
            previous = await coordinator.history_db.traffic_summary()
            coordinator.cache["peaks"] = previous["peaks"]
            coordinator.cache["traffic_history"] = previous["traffic_history"]
        except Exception as err:
            _LOGGER.warning("HoraInfo history restore error: %s", type(err).__name__)
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
                                await item.history_db.record_inventory(item.inventory.history.values())
                                item.cache["mac"].update(await item.history_db.inventory_summary())
                            item.async_set_updated_data(dict(item.cache))
            except Exception as exc:
                _LOGGER.debug("IEEE vendor registry update failed: %s", type(exc).__name__)
            finally:
                data["_vendor_refresh_scheduled"] = False
        hass.async_create_task(refresh_oui())
    return True


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
