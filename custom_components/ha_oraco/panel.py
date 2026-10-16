"""Register the native Home Assistant sidebar and cached-data WebSocket API."""
from pathlib import Path
import voluptuous as vol

from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
from .const import DOMAIN
from .dashboard_preferences import DashboardPreferences

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
            "preferences": hass.data[DOMAIN]["_dashboard_preferences"].for_switch(entry_id),
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
    vol.Required("mode"): vol.In(["traffic","daily","snapshots","sfp_temperature","sfp_optical","storage"]),
    vol.Optional("port", default="__total__"): str,
    vol.Optional("hours", default=24): vol.All(vol.Coerce(int),vol.Range(min=1,max=720)),
    vol.Optional("kind", default="sfp"): str,
    vol.Optional("metric", default="voltage_v"): vol.In(["voltage_v","current_ma","rx_dbm","tx_dbm"]),
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
    elif msg["mode"]=="sfp_temperature":
        result=await database.temperature_history(msg["hours"])
    elif msg["mode"]=="sfp_optical":
        result=await database.optical_history(msg["metric"],msg["hours"])
    elif msg["mode"]=="storage":
        result=await database.storage_summary()
    else:
        result=await database.snapshot_history(msg["kind"])
    if msg["mode"]=="traffic":
        connection.send_result(msg["id"],{"items":result["series"],"total":result["total"]})
    elif msg["mode"] in ("sfp_temperature","sfp_optical","storage"):
        connection.send_result(msg["id"],result)
    else:
        connection.send_result(msg["id"],{"items":result})

@websocket_api.websocket_command({
    vol.Required("type"): "ha_oraco/preference",
    vol.Required("entry_id"): str,
    vol.Required("category"): vol.In(["ports","devices","layout","options","thresholds","infrastructure"]),
    vol.Required("key"): str,
    vol.Required("value"): object,
})
@websocket_api.require_admin
@websocket_api.async_response
async def save_preference(hass,connection,msg):
    entry_id=msg["entry_id"]
    coordinator=hass.data.get(DOMAIN,{}).get(entry_id)
    if not hasattr(coordinator,"client"):
        connection.send_error(msg["id"],"not_found","Unknown switch")
        return
    preferences=hass.data[DOMAIN]["_dashboard_preferences"]
    try:
        await preferences.set_item(entry_id,msg["category"],msg["key"],msg["value"])
    except (ValueError,TypeError) as err:
        connection.send_error(msg["id"],"invalid_format",str(err))
        return
    connection.send_result(msg["id"],{"saved":True})

async def register_panel(hass):
    """Serve frontend file and register one native-looking custom sidebar panel."""
    if hass.data.setdefault(DOMAIN, {}).get("_panel_registered"):
        return
    preferences=DashboardPreferences(hass)
    await preferences.load()
    hass.data[DOMAIN]["_dashboard_preferences"]=preferences
    static_file = Path(__file__).parent / "frontend" / "ha-oraco-panel.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_URL, str(static_file), False),
         StaticPathConfig("/ha_oraco_static/brand/icon.svg", str(static_file.parent / "brand" / "icon.svg"), False)]
    )
    websocket_api.async_register_command(hass, dashboard_data)
    websocket_api.async_register_command(hass, history_data)
    websocket_api.async_register_command(hass, save_preference)
    frontend.async_register_built_in_panel(
        hass, "custom",
        sidebar_title="HoraInfo",
        sidebar_icon="mdi:lan",
        frontend_url_path="ha-oraco",
        config={"_panel_custom": {
            "name": "ha-oraco-panel",
            "module_url": PANEL_URL + "?v=0.4.38",
            "embed_iframe": False,
            "trust_external": False,
        }},
        require_admin=True,
    )
    hass.data[DOMAIN]["_panel_registered"] = True
