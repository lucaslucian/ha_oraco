"""Persistent MAC inventory; history is bounded to 2000 identities."""
from datetime import datetime, timezone
from homeassistant.helpers.storage import Store

class MacInventory:
    def __init__(self, hass, key):
        self.store = Store(hass, 1, "ha_oraco_mac_" + key.replace(".", "_").replace(":", "_"))
        self.history = {}
        self.current = []
        self.last_scan = None

    async def load(self):
        saved = await self.store.async_load() or {}
        self.history = saved.get("history", {})

    async def observe(self, items, vendors=None):
        timestamp = datetime.now(timezone.utc).isoformat()
        current = {}
        for original in items:
            item = dict(original)
            identity = str(item.get("vlan")) + "|" + item["mac"]
            previous = self.history.get(identity, {})
            item["first_seen"] = previous.get("first_seen", timestamp)
            item["last_seen"] = timestamp
            item["moved_from"] = previous.get("port") if previous.get("port") != item["port"] else None
            if vendors:
                item["vendor"] = vendors.lookup(item["mac"])
            current[identity] = item
        self.current = list(current.values())
        self.history.update(current)
        recent = sorted(self.history.items(), key=lambda pair: pair[1]["last_seen"], reverse=True)
        self.history = dict(recent[:2000])
        self.last_scan = timestamp
        await self.store.async_save({"history": self.history})

    def summary(self):
        return {
            "mac_current": len(self.current),
            "mac_known": len(self.history),
            "mac_local": sum(x["classification"] == "locally_administered" for x in self.current),
            "mac_last_scan": self.last_scan,
            "mac_entries": self.current[:25],
            "mac_truncated": len(self.current) > 25,
        }
