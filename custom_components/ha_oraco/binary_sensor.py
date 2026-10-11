"""Per-port connectivity sensors."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .entities import port_info


async def async_setup_entry(hass, entry, async_add_entities):
    c = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(OracoLink(c, p) for p in c.data["ports"])


class OracoLink(CoordinatorEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_has_entity_name = True
    _attr_name = "Link"

    def __init__(self, coordinator, port):
        super().__init__(coordinator)
        self.port = port
        self._attr_unique_id = f"{DOMAIN}_{coordinator.client.host}_{port}_link"
        self._attr_device_info = port_info(coordinator, port)

    @property
    def is_on(self):
        return self.coordinator.data["ports"].get(self.port, {}).get("up")
