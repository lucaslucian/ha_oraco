"""Register the native Home Assistant sidebar and cached-data WebSocket API."""
from pathlib import Path
import voluptuous as vol

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
from .const import DOMAIN

PANEL_URL = "/ha_oraco_static/ha-oraco-panel.js"

@websocket_api.websocket_command({vol.Required("type"): "ha_oraco/dashboard"})
@websocket_api.async_response
async def dashboard_data(hass, connection, msg):
    switches = []
    for entry_id, coordinator in hass.data.get(DOMAIN, {}).items():
        if not hasattr(coordinator, "client"):
            continue
        data = coordinator.data or {}
        switches.append({
            "id": entry_id,
            "host": coordinator.client.host,
            "name": f"Horaco {coordinator.client.host}",
            "device": data.get("device", {}),
            "ports": data.get("ports", {}),
        })
    connection.send_result(msg["id"], {"switches": switches})

async def register_panel(hass):
    """Serve frontend file and register one native-looking custom sidebar panel."""
    if hass.data.setdefault(DOMAIN, {}).get("_panel_registered"):
        return
    static_file = Path(__file__).parent / "frontend" / "ha-oraco-panel.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_URL, str(static_file), False)]
    )
    websocket_api.async_register_command(hass, dashboard_data)
    frontend.async_register_built_in_panel(
        hass, "custom",
        sidebar_title="HA Oraco",
        sidebar_icon="mdi:lan",
        frontend_url_path="ha-oraco",
        config={"_panel_custom": {
            "name": "ha-oraco-panel",
            "module_url": PANEL_URL,
            "embed_iframe": False,
            "trust_external": False,
        }},
        require_admin=False,
    )
    hass.data[DOMAIN]["_panel_registered"] = True
