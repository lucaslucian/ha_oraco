"""Register the native Home Assistant sidebar and cached-data WebSocket API."""
from pathlib import Path
import voluptuous as vol

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
from .const import DOMAIN

PANEL_URL = "/ha_oraco_static/ha-oraco-panel.js"

@websocket_api.websocket_command({vol.Required("type"): "ha_oraco/dashboard"})
@websocket_api.require_admin
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
            "name": data.get("device", {}).get("name") or data.get("device", {}).get("model") or f"Switch {coordinator.client.host}",
            "device": data.get("device", {}),
            "ports": data.get("ports", {}),
            "sfp": data.get("sfp", {}),
            "mac": data.get("mac", {}),
            "topology": data.get("topology", {}),
            "network": data.get("network", {}),
            "diagnostics": data.get("diagnostics", {}),
            "peaks": data.get("peaks", {}),
            "traffic_history": data.get("traffic_history", []),
            "traffic_by_port": data.get("traffic_by_port", {}),
            "recent_changes": data.get("recent_changes", []),
            "oui": {"prefix_count": len(coordinator.vendors.prefixes) if coordinator.vendors else 0,
                    "last_updated": coordinator.vendors.last_updated if coordinator.vendors else None,
                    "last_attempt": coordinator.vendors.last_attempt if coordinator.vendors else None,
                    "sources": coordinator.vendors.source_status if coordinator.vendors else {}},
        })
    connection.send_result(msg["id"], {"switches": switches})

@websocket_api.websocket_command({
    vol.Required("type"): "ha_oraco/history",
    vol.Required("entry_id"): str,
    vol.Required("mode"): vol.In(["traffic","daily","snapshots"]),
    vol.Optional("port", default="__total__"): str,
    vol.Optional("hours", default=24): vol.All(vol.Coerce(int),vol.Range(min=1,max=720)),
    vol.Optional("kind", default="sfp"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def history_data(hass, connection, msg):
    coordinator=hass.data.get(DOMAIN,{}).get(msg["entry_id"])
    if not hasattr(coordinator,"client") or coordinator.history_db is None:
        connection.send_error(msg["id"],"not_found","History database unavailable")
        return
    database=coordinator.history_db
    if msg["mode"]=="traffic":
        result={"series":await database.series(msg["port"],msg["hours"]),
                "total":await database.period_totals(msg["port"],msg["hours"])}
    elif msg["mode"]=="daily":
        result=await database.daily_totals(msg["port"])
    else:
        result=await database.snapshot_history(msg["kind"])
    if msg["mode"]=="traffic":
        connection.send_result(msg["id"],{"items":result["series"],"total":result["total"]})
    else:
        connection.send_result(msg["id"],{"items":result})

async def register_panel(hass):
    """Serve frontend file and register one native-looking custom sidebar panel."""
    if hass.data.setdefault(DOMAIN, {}).get("_panel_registered"):
        return
    static_file = Path(__file__).parent / "frontend" / "ha-oraco-panel.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_URL, str(static_file), False),
         StaticPathConfig("/ha_oraco_static/brand/icon.svg", str(static_file.parent / "brand" / "icon.svg"), False)]
    )
    websocket_api.async_register_command(hass, dashboard_data)
    websocket_api.async_register_command(hass, history_data)
    frontend.async_register_built_in_panel(
        hass, "custom",
        sidebar_title="HoraInfo",
        sidebar_icon="mdi:lan",
        frontend_url_path="ha-oraco",
        config={"_panel_custom": {
            "name": "ha-oraco-panel",
            "module_url": PANEL_URL + "?v=0.4.13",
            "embed_iframe": False,
            "trust_external": False,
        }},
        require_admin=True,
    )
    hass.data[DOMAIN]["_panel_registered"] = True
