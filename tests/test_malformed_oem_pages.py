"""Realistic regression fixtures for malformed HORACO OEM HTML."""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"

def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+".py"))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_firmware_info_malformed_th_and_double_pair():
    html='''<html><head><title>System Information</title></head><body>
    <form method="post" action="/info.cgi"><table id="infotbl">
    <tr><th>Device Name:</td><td><input name="devName" value="HC-SWTGW218AS"></td>
    <th>Sys Uptime:</td><td>0Day1Hour0Minute17Second</td></tr>
    <tr><th>Device Model:</td><td>HC-SWTGW218AS</td>
    <th>Firmware Version:</td><td>V200.2.4</td></tr>
    <tr><th>MAC Address:</td><td>1C:2A:A3:31:D9:18</td></tr>
    </table></form></body></html>'''
    info,_=load("api").parse_info(html)
    assert info["name"]=="HC-SWTGW218AS"
    assert info["model"]=="HC-SWTGW218AS"
    assert info["firmware"]=="V200.2.4"
    assert info["mac"]=="1C:2A:A3:31:D9:18"
    assert info["uptime_seconds"]==3617

def test_sfp_malformed_first_row_and_mixed_cells():
    html='''<html><head><title>Fiber Module Status</title></head><body>
    <table class="infotbl" id="infotbl"></tr>
    <th>Port:</td><td>Port 9</td></tr>
    <tr><th>OE Present:</td><td>Yes</td></tr>
    <tr><th>Vendor Name:</td><td>ODI</td></tr>
    <tr><th>Vendor PN:</td><td>DFP-34X-2IY3</td></tr>
    <tr><th>Temperature(C):</td><td id=temp>66-107</td></tr>
    <tr><th>Voltage(V):</td><td id=voltage>121-66</td></tr>
    <tr><th>Current(mA):</td><td id=current>0-0</td></tr>
    <tr><th>Output Power(dBm):</td><td id=txpower>0-1</td></tr>
    </table><table class="infotbl" id="infotbl2"></table></body></html>'''
    result=load("advanced").parse_sfp(html)
    assert result["port"]=="Port 9"
    assert result["module_present"]=="Yes"
    assert result["vendor"]=="ODI"
    assert result["part_number"]=="DFP-34X-2IY3"
    assert result["current_ma"]==0
    assert result["temperature_c"]>66
    assert result["tx_dbm"]==-40.0
