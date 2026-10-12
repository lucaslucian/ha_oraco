"""Test status table parsing only, excluding POST configuration forms."""
import importlib.util
from pathlib import Path

path=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"/"protection.py"
spec=importlib.util.spec_from_file_location("protection",path)
p=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

def test_isolation_status_not_form():
    html='''<form method="post"><table><tr><th>Port</th><th>Port Isolation List</th></tr>
    <tr><td><select><option>Port 4</option></select></td><td>BAD</td></tr></table></form>
    <div><table><tr><th>Port</th><th>Port Isolation List</th></tr>
    <tr><td>Port 1</td><td>1-9</td></tr><tr><td>Port 2</td><td>1,3,5-7</td></tr></table></div>'''
    result=p.parse_isolation(html)["ports"]
    assert result["1"]["listed_ports"]==list(range(1,10))
    assert result["2"]["listed_ports"]==[1,3,5,6,7]

def test_stp_status_ignores_form_defaults():
    html='''<form method="post"><select name="priority"><option selected>128</option></select></form>
    <table><tr><th>Port</th><th>State</th><th>Role</th><th colspan="2">Path Cost</th>
    <th>Priority</th><th colspan="2">P2P</th><th colspan="2">Edge</th></tr>
    <tr><th>Config</th><th>Actual</th><th>Config</th><th>Actual</th><th>Config</th><th>Actual</th></tr>
    <tr><td>Port 9</td><td>Forwarding</td><td>Disabled</td><td>Auto</td><td>17000</td>
    <td>128</td><td>Auto</td><td>True</td><td>False</td><td>False</td></tr></table>'''
    assert p.parse_stp_ports(html)["ports"]["9"]["path_cost_actual"]=="17000"

def test_storm_control_status_not_defaults():
    header='<tr><th>Port</th><th>Broadcast Rate (Kbit/sec)</th><th>Known Multicast Rate (Kbit/sec)</th><th>Unknown Multicast Rate (Kbit/sec)</th><th>Unknown Unicast Rate (Kbit/sec)</th></tr>'
    html='<form method="post"><table>'+header+'<tr><td><select><option>Port 9</option></select></td><td><input name="bc_rate"></td><td>Off</td><td>Off</td><td>Off</td></tr></table></form><form method="post"><table>'+header+'<tr><td>Port 9</td><td>Off</td><td>Off</td><td>Off</td><td>Off</td></tr></table><input type="hidden" name="cmd" value="storm_dft"></form>'
    result=p.parse_storm_control(html)["ports"]["9"]
    assert result["broadcast_kbps"] is None
    assert result["known_multicast_kbps"] is None
