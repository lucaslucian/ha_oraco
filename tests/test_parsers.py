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

def test_sfp_unexpected_html_has_safe_structural_diagnostics():
    a = load("advanced")
    html = '<html><head><title>Session expired</title></head><body><table><tr><td>Please log in</td><td>Again</td></tr></table></body></html>'
    try:
        a.parse_sfp(html)
    except ValueError as exc:
        assert "Session expired" in str(exc)
        assert "rows=1" in str(exc)
    else:
        raise AssertionError("Unexpected SFP HTML should not be interpreted as disconnected module")


def test_dhcp_trust_requires_explicit_read_only_status_table():
    parser=load("advanced")
    # A static binding form has checkboxes but must not imply trusted ports.
    form='<input name="enable_dhcpsnp" checked><form action="dhcp_snooping.cgi?page=static"><input class="chkp" id="p1" checked><label for="p1">Port 1</label></form>'
    data=parser.parse_dhcp(form)
    assert data["enabled"] is True
    assert data["trusted_ports"]=={}
    assert data["trust_status_available"] is False
    html=form+'''<table><tr><th>Port</th><th>Trusted</th></tr>
    <tr><td>Port 1</td><td>Yes</td></tr>
    <tr><td>Port 9</td><td>No</td></tr></table>'''
    data=parser.parse_dhcp(html)
    assert data["trusted_ports"]=={"1":True,"9":False}
    assert data["per_port"]["9"]["source"]=="observed_status_table"


def test_igmp_membership_uses_named_columns_and_safe_port_lists():
    parser=load("advanced")
    html='''<input name="enable_igmp" checked>
    <table><tr><th>VLAN</th><th>Group IP Address</th><th>Member Ports</th></tr>
    <tr><td>20</td><td>239.1.2.3</td><td>Port 1, 9</td></tr>
    <tr><td>30</td><td>239.5.6.7</td><td>Port 2</td></tr></table>'''
    data=parser.parse_igmp(html)
    assert len(data["groups"])==2
    assert data["groups"][0]["port_numbers"]==["1","9"]
    assert data["per_port"]["9"]==[{"group":"239.1.2.3","vlan":"20"}]
    assert data["per_port"]["2"]==[{"group":"239.5.6.7","vlan":"30"}]
    assert parser._port_numbers("invalid Port 99 maybe")==[]
    assert parser._port_numbers("1-100")==[]
    assert parser._port_numbers("Port 1, 9")==["1","9"]


def test_oem_multiline_tables_and_unknown_global_state():
    a=load("advanced")
    # Some OEM pages have a decorative title row before actual headings.
    dhcp='''<table><tr><td colspan="2">DHCP Snooping Status</td></tr>
    <tr><th>Interface</th><th>Trust State</th></tr>
    <tr><td>Port 9</td><td>Untrusted</td></tr>
    <tr><td>Port 1</td><td>Trusted</td></tr></table>'''
    result=a.parse_dhcp(dhcp)
    assert result["enabled"] is None
    assert result["per_port"]["1"]["trusted"] is True
    assert result["per_port"]["9"]["trusted"] is False
    assert result["trust_source"]=="explicit_status_table"
    igmp='''<table><tr><th colspan="3">IGMP Multicast Groups</th></tr>
    <tr><th>Group IP</th><th>VLAN ID</th><th>Member Ports</th></tr>
    <tr><td>239.1.2.3</td><td>2000</td><td>Port 1, 9</td></tr>
    <tr><td>239.1.2.4</td><td>1</td><td>CPU</td></tr></table>'''
    data=a.parse_igmp(igmp)
    assert data["enabled"] is None
    assert len(data["groups"])==2
    assert data["per_port"]["9"]==[{"group":"239.1.2.3","vlan":"2000"}]
    assert data["groups_unmapped"]==1


def test_configuration_form_cannot_invent_dhcp_trust_or_igmp_membership():
    a=load("advanced")
    form='''<input name="enable_dhcpsnp" checked>
      <form action="dhcp_snooping.cgi?page=static">
      <input class="chkp" checked id="t1"><label for="t1">Port 1</label>
      </form>'''
    assert not a.parse_dhcp(form)["trust_status_available"]
    igmp='''<input name="enable_igmp" checked>
      <table><tr><td>IP Address</td><td>Port</td><td>VLAN ID</td></tr>
      <tr><td>239.2.3.4</td><td>Port 2</td><td>20</td></tr></table>'''
    groups=a.parse_igmp(igmp)
    assert groups["per_port"]["2"][0]["group"]=="239.2.3.4"
    for method,invalid in ((a.parse_dhcp,"<html>Please login</html>"),
                           (a.parse_igmp,"<html>Please login</html>")):
        try:
            method(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Login page must not be accepted as monitoring data")
