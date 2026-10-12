import importlib.util
from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'custom_components' / 'ha_oraco' / 'bridging.py'
spec = importlib.util.spec_from_file_location('bridging', p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def test_stp_global():
    html = '<table><tr><th>Spanning Tree Status</th><td>Disable</td></tr><tr><th>Version</th><td><select><option>STP</option><option selected>RSTP</option></select></td></tr><tr><th>Root Port</th><td>-</td></tr></table>'
    result = m.parse_stp_global(html)
    assert result['enabled'] is False
    assert result['version'] == 'RSTP'

def test_no_aggregation():
    html = '<table><tr><th>Select</th><th>Aggregate Group ID</th><th>Type</th><th>Member port</th><th>Aggregated Port</th></tr></table>'
    result = m.parse_aggregation(html)
    assert result['count'] == 0
