"""Offline IEEE vendor lookup with an optional periodically updated cache."""
import csv
import io
import re
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

    async def load(self):
        data = await self.store.async_load() or {}
        self.prefixes = data.get("prefixes", {})
        self.last_updated = data.get("last_updated")

    def lookup(self, mac):
        kind = mac_classification(mac)
        if kind == "locally_administered":
            return "MAC local/privado"
        if kind == "multicast":
            return "Multicast"
        value = mac.replace(":", "")
        for size in (9, 7, 6):
            if value[:size] in self.prefixes:
                return self.prefixes[value[:size]]
        return "Desconhecido"

    async def refresh(self, session):
        found = {}
        for url in SOURCES:
            try:
                async with session.get(url, timeout=45) as response:
                    response.raise_for_status()
                    document = await response.text()
                for row in csv.DictReader(io.StringIO(document)):
                    prefix = re.sub(r"[^0-9a-fA-F]", "", row.get("Assignment", "")).upper()
                    company = (row.get("Organization Name") or "").strip()
                    if len(prefix) in (6, 7, 9) and company:
                        found[prefix] = company
            except Exception:
                continue
        if found:
            self.prefixes = found
            self.last_updated = datetime.now(timezone.utc).isoformat()
            await self.store.async_save({"prefixes": found, "last_updated": self.last_updated})
        return len(found)
