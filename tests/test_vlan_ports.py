"""Safe VLAN status parser tests. All values are synthetic."""
import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "custom_components" / "ha_oraco" / "vlans.py"
spec = importlib.util.spec_from_file_location("vlan_parser", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def fixture():
    return """<html>
    <form action="/vlan.cgi?page=port_based">
      <select name="vlan_access"><option value="4094">VLAN 4094</option></select>
      <input id="vlanState" value="1">
    </form>
    <div class="showdiv"><table>
    <tr><th>Port</th><th>Port vlan type</th><th>Access VLAN</th><th>Native VLAN</th><th>Trunk vlan</th></tr>
    <tr><td>Port 1</td><td>Hybrid:All</td><td>-</td><td>77</td>
    <td><div class="vlancontent">Tagged VLAN: 20,30</div>
    <div class="vlancontent">Untagged VLAN: 77</div></td></tr>
    <tr><td>Port 2</td><td>Trunk</td><td>-</td><td>1</td><td class="vlancontent">1,20</td></tr>
    <tr><td>Port 3</td><td>Access</td><td>30</td><td>-</td><td>-</td></tr>
    </table></div></html>"""

def test_vlan_status_table_and_dynamic_ports():
    result = module.parse_port_vlans(fixture())
    assert result["port_count"] == 3
    p1 = result["ports"]["1"]
    assert p1["mode"] == "hybrid"
    assert p1["accepted_frames"] == "All"
    assert p1["native_vlan"] == 77
    assert p1["tagged_vlans"] == [20, 30]
    assert p1["untagged_vlans"] == [77]
    assert result["ports"]["2"]["allowed_vlans"] == [1,20]
    assert result["ports"]["3"]["access_vlan"] == 30

def test_form_choices_not_reported_as_port_state():
    html = '<form><select><option>VLAN 4094</option></select></form>'
    try:
        module.parse_port_vlans(html)
    except ValueError:
        pass
    else:
        raise AssertionError("Edit form must not be treated as observed configuration")
    assert 4094 not in module.parse_port_vlans(fixture())["ports"]["1"]["tagged_vlans"]

def test_incomplete_status_is_rejected():
    try:
        module.parse_port_vlans('<div class="showdiv"><table><tr><th>Port</th></tr></table></div>')
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid format should be rejected")
