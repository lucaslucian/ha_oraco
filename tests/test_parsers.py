"""Fixture-based tests, no real switch required."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "ha_oraco"

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_mac_classification():
    mac = load("mac")
    assert mac.normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert mac.mac_classification("02:11:22:33:44:55") == "locally_administered"
    assert mac.mac_classification("00:11:22:33:44:55") == "globally_administered"
    assert mac.mac_classification("01:00:5E:00:00:01") == "multicast"

def test_fdb_and_graph():
    mac = load("mac")
    topology = load("topology")
    html = """<table><tr><th>MAC Address</th><th>Type</th><th>Port</th><th>VLAN</th></tr>
    <tr><td>00:11:22:33:44:55</td><td>Dynamic</td><td>Port 2</td><td>10</td></tr></table>"""
    entries, pages = mac.parse_mac_page(html)
    assert pages == 1
    assert entries[0]["vlan"] == "10"
    graph = topology.build_topology("192.0.2.5", {"2": {"up": True, "speed": "1G"}}, entries)
    assert len(graph["edges"]) == 2
    assert graph["edges"][1]["confidence"] == "observed"

def test_optical_ddmi():
    advanced = load("advanced")
    html = """<table class="infotbl">
    <tr><td>Temperature</td><td id="temp">25-0</td></tr>
    <tr><td>Voltage</td><td id="voltage">12-34</td></tr>
    <tr><td>RX power</td><td id="rxpower">0-100</td></tr></table>"""
    result = advanced.parse_sfp(html)
    assert result["temperature_c"] > 24
    assert result["rx_dbm"] < 0

def test_snooping():
    a = load("advanced")
    assert a.parse_dhcp('<input name="enable_dhcpsnp" checked>')["enabled"] is True
    assert a.parse_igmp('<input name="enable_igmp">')["enabled"] is False

def test_optical_no_fiber_floor_value():
    a = load("advanced")
    html = """<table class="infotbl"><tr><td>RX Power</td><td id="rxpower">0-1</td></tr><tr><td>TX Power</td><td id="txpower">0-1</td></tr></table>"""
    value = a.parse_sfp(html)
    assert value["rx_dbm"] == -40.0
    assert value["tx_dbm"] == -40.0

def test_optical_raw_zero_is_unknown():
    a = load("advanced")
    html = """<table class="infotbl"><tr><td>RX Power</td><td id="rxpower">0-0</td></tr></table>"""
    assert a.parse_sfp(html)["rx_dbm"] is None

def test_actual_sfp_page_labels_and_optics():
    a=load("advanced")
    html="""<table class="infotbl">
    <tr><th>Port:</th><td>Port 9</td></tr>
    <tr><th>OE Present:</th><td>Yes</td></tr>
    <tr><th>Loss of Signal:</th><td>No</td></tr>
    <tr><th>Transceiver Type:</th><td>SFP/SFP+</td></tr>
    <tr><th>Connector Type:</th><td>SC</td></tr>
    <tr><th>Transmission Media:</th><td>Single Mode</td></tr>
    <tr><th>Vendor Name:</th><td>ODI</td></tr>
    <tr><th>Vendor PN:</th><td>DFP-34X-2IY3</td></tr>
    <tr><th>Vendor SN:</th><td>XPON26080833</td></tr>
    <tr><th>Temperature(C):</th><td id=temp>66-107</td></tr>
    <tr><th>Voltage(V):</th><td id=voltage>121-66</td></tr>
    <tr><th>Current(mA):</th><td id=current>0-0</td></tr>
    <tr><th>Input Power(dBm):</th><td id=rxpower>0-1</td></tr>
    </table>"""
    data=a.parse_sfp(html)
    assert data["module_present"]=="Yes"
    assert data["vendor"]=="ODI"
    assert data["part_number"]=="DFP-34X-2IY3"
    assert data["serial_number"]=="XPON26080833"
    assert data["current_ma"]==0
    assert data["rx_dbm"]==-40
