"""Sanitized Home Assistant diagnostics for HA Oraco."""
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN

async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    return {
        "integration": DOMAIN,
        "endpoint_health": coordinator.diagnostics.get("endpoints", {}),
        "last_success": coordinator.diagnostics.get("last_success"),
        "last_error": coordinator.diagnostics.get("last_error"),
        "port_count": len(data.get("ports", {})),
        "mac_current": data.get("mac", {}).get("mac_current"),
        "mac_known": data.get("mac", {}).get("mac_known"),
        "sfp_fields": sorted(data.get("sfp", {}).get("sfp", {}).keys()),
        "network_groups": sorted(data.get("network", {}).keys()),
        "vendor_cache_available": bool(coordinator.vendors and coordinator.vendors.prefixes),
        # Never export credentials, raw MACs, addresses, hostnames, or raw HTML.
    }
