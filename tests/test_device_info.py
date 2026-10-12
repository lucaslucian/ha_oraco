"""Verify device metadata and status from the actual overview page structure."""
import importlib.util
from pathlib import Path

path=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"/"api.py"
spec=importlib.util.spec_from_file_location("switch_api",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_multicolumn_device_info_and_ports():
    html='''<html><form method="post" action="/info.cgi"><table class="infotbl">
    <tr><th>Device Name:</th><td><input name="devName" value="HC-SWTGW218AS"></td>
        <th>Sys Uptime:</th><td>0Day1Hour0Minute17Second</td></tr>
    <tr><th>Device Model:</th><td>HC-SWTGW218AS</td>
        <th>Firmware Version:</th><td>V200.2.4</td></tr>
    <tr><th>IP Address:</th><td>10.0.0.254</td>
        <th>Netmask:</th><td>255.255.0.0</td></tr>
    <tr><th>MAC Address:</th><td>1C:2A:A3:31:D9:18</td></tr>
    </table></form><table>
    <tr><th>Port</th><th>Link Status</th><th>Duplex Status</th><th>Nego Speed Status</th><th>Flow Control</th></tr>
    <tr><td>Port 1</td><td>Link Down</td><td>Auto</td><td>Auto</td><td>Off</td></tr>
    <tr><td>Port 9</td><td>Link Up</td><td>Full Duplex</td><td>2500M</td><td>Off</td></tr></table></html>'''
    device,ports=module.parse_info(html)
    assert device["model"]=="HC-SWTGW218AS"
    assert device["name"]=="HC-SWTGW218AS"
    assert device["firmware"]=="V200.2.4"
    assert device["uptime"]=="1 h 17 s"
    assert device["uptime_seconds"]==3617
    assert device["mac"]=="1C:2A:A3:31:D9:18"
    assert device["ip_address"]=="10.0.0.254"
    assert device["netmask"]=="255.255.0.0"
    assert ports["9"]["up"] is True
    assert ports["9"]["speed"]=="2500M"
    assert ports["1"]["up"] is False
