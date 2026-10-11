"""Native sensors: operational metrics and slow device metadata."""
from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .entities import device_info, port_info

FIELDS = {
    "speed": ("Link speed", None, None),
    "duplex": ("Duplex", None, None),
    "rx_bytes": ("RX bytes", "B", SensorStateClass.TOTAL_INCREASING),
    "tx_bytes": ("TX bytes", "B", SensorStateClass.TOTAL_INCREASING),
    "rx_packets": ("RX packets", None, SensorStateClass.TOTAL_INCREASING),
    "tx_packets": ("TX packets", None, SensorStateClass.TOTAL_INCREASING),
    "rx_bps": ("RX rate", "bit/s", SensorStateClass.MEASUREMENT),
    "tx_bps": ("TX rate", "bit/s", SensorStateClass.MEASUREMENT),
}


async def async_setup_entry(hass, entry, async_add_entities):
    c = hass.data[DOMAIN][entry.entry_id]
    entities = [OracoSensor(c, n, k) for n in c.data["ports"] for k in FIELDS]
    entities += [OracoSensor(c, None, key) for key in ("model", "firmware", "uptime", "mac", "ports_up", "mac_current", "mac_known", "mac_local", "sfp_temperature", "sfp_voltage", "sfp_current", "sfp_rx_dbm", "sfp_tx_dbm")]
    async_add_entities(entities)


class OracoSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, port, key):
        super().__init__(coordinator)
        self.port = port
        self.key = key
        self._attr_unique_id = f"{DOMAIN}_{coordinator.client.host}_{port or 'device'}_{key}"
        self._attr_device_info = port_info(coordinator, port) if port else device_info(coordinator)
        name, unit, state_class = FIELDS.get(key, (key.replace("_", " ").title(), None, None))
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        optics = {
            "sfp_temperature": ("SFP temperature", "°C", SensorDeviceClass.TEMPERATURE),
            "sfp_voltage": ("SFP voltage", "V", SensorDeviceClass.VOLTAGE),
            "sfp_current": ("SFP current", "mA", SensorDeviceClass.CURRENT),
            "sfp_rx_dbm": ("SFP RX power", "dBm", None),
            "sfp_tx_dbm": ("SFP TX power", "dBm", None),
        }
        if key in optics:
            self._attr_name, self._attr_native_unit_of_measurement, device_cls = optics[key]
            self._attr_state_class = SensorStateClass.MEASUREMENT
            if device_cls is not None:
                self._attr_device_class = device_cls
        if key in ("rx_bytes", "tx_bytes"):
            self._attr_device_class = SensorDeviceClass.DATA_SIZE

    @property
    def native_value(self):
        data = self.coordinator.data
        if self.port is None:
            if self.key in ("mac_current", "mac_known", "mac_local"):
                return data.get("mac", {}).get(self.key)
            if self.key.startswith("sfp_"):
                fields = {"sfp_temperature": "temperature_c", "sfp_voltage": "voltage_v",
                          "sfp_current": "current_ma", "sfp_rx_dbm": "rx_dbm", "sfp_tx_dbm": "tx_dbm"}
                return data.get("sfp", {}).get("sfp", {}).get(fields.get(self.key))
            if self.key == "ports_up":
                return sum(p["up"] for p in data["ports"].values())
            return data["device"].get(self.key)
        return data["ports"].get(self.port, {}).get(self.key)
