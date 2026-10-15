"""Offline IEEE vendor lookup with an optional periodically updated cache."""
import csv
import json
import io
import re
import logging

_LOGGER = logging.getLogger(__name__)
from datetime import datetime, timezone
from homeassistant.helpers.storage import Store
from .mac import mac_classification

SOURCES = (
    "https://standards-oui.ieee.org/oui/oui.csv",
    "https://standards-oui.ieee.org/oui28/mam.csv",
    "https://standards-oui.ieee.org/oui36/oui36.csv",
)

class VendorCache:
    def __init__(self, hass):
        self.store = Store(hass, 1, "ha_oraco_oui")
        self.prefixes = {}
        self.last_updated = None
        self.last_attempt = None
        self.source_status = {}

    async def load(self):
        data = await self.store.async_load() or {}
        self.prefixes = data.get("prefixes", {})
        self.last_updated = data.get("last_updated")
        self.last_attempt = data.get("last_attempt")
        self.source_status = data.get("sources", {})

    def lookup(self, mac):
        kind = mac_classification(mac)
        if kind == "locally_administered":
            return "MAC local/privado"
        if kind == "multicast":
            return "Multicast"
        value = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()
        for size in (9, 7, 6):
            if value[:size] in self.prefixes:
                return self.prefixes[value[:size]]
        return "Desconhecido"

    async def refresh(self, session):
        found = {}
        self.last_attempt = datetime.now(timezone.utc).isoformat()
        self.source_status = {}
        for url in SOURCES:
            try:
                async with session.get(url, timeout=45) as response:
                    response.raise_for_status()
                    document = await response.text()
                source_count = 0
                for row in csv.DictReader(io.StringIO(document)):
                    prefix = re.sub(r"[^0-9a-fA-F]", "", row.get("Assignment", "")).upper()
                    company = (row.get("Organization Name") or "").strip()
                    if len(prefix) in (6, 7, 9) and company:
                        found[prefix] = company
                        source_count += 1
                self.source_status[url.rsplit('/', 1)[-1]] = {'status': 'ok', 'count': source_count}
            except Exception as err:
                self.source_status[url.rsplit('/', 1)[-1]] = {'status': 'failed', 'error': type(err).__name__}
                _LOGGER.warning('HoraInfo IEEE download error %s: %s', url, type(err).__name__)
                continue
        # IEEE often returns 403 from cloud networks. Use a documented OUI mirror
        # as fallback, without claiming the three original sources succeeded.
        if not found:
            url = "https://raw.githubusercontent.com/jfisbein/ouidb-json/master/ouidb.json"
            try:
                async with session.get(url, timeout=90) as response:
                    response.raise_for_status()
                    data = await response.json(content_type=None)
                fallback = {}
                for entry in data:
                    prefix = re.sub(r"[^0-9A-Fa-f]", "", str(entry.get("prefix", ""))).upper()
                    company = (entry.get("organization") or {}).get("name", "").strip()
                    if len(prefix) == 6 and company:
                        fallback[prefix] = company
                if len(fallback) < 1000:
                    raise ValueError("OUI fallback dataset unexpectedly small")
                found = fallback
                self.source_status["github_oui_mirror"] = {"status":"ok","count":len(found)}
                self.last_updated = datetime.now(timezone.utc).isoformat()
            except Exception as err:
                self.source_status["github_oui_mirror"] = {"status":"failed","error":type(err).__name__}
                _LOGGER.warning("HoraInfo fallback OUI mirror unavailable: %s", type(err).__name__)
        if found:
            if any(x['status'] != 'ok' for x in self.source_status.values()):
                found = {**self.prefixes, **found}
            self.prefixes = found
            complete = len(self.source_status) == len(SOURCES) and all(x["status"] == "ok" for x in self.source_status.values())
            if complete:
                self.last_updated = datetime.now(timezone.utc).isoformat()
        await self.store.async_save({"prefixes": self.prefixes, "last_updated": self.last_updated,
                                     "last_attempt": self.last_attempt, "sources": self.source_status})
        return len(found)
