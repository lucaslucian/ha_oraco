"""Shared device registration helpers."""
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN


def device_info(coordinator):
    device = coordinator.data["device"]
    return DeviceInfo(identifiers={(DOMAIN, coordinator.client.host)},
                      name=f"Horaco {coordinator.client.host}", manufacturer="HORACO / OEM",
                      model=device.get("model"), sw_version=device.get("firmware"),
                      configuration_url=coordinator.client.base)


def port_info(coordinator, port):
    host = coordinator.client.host
    return DeviceInfo(identifiers={(DOMAIN, f"{host}_port_{port}")}, name=f"Port {port}",
                      via_device=(DOMAIN, host))
