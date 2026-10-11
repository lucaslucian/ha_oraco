"""Offline tests for the devtools Horaco CGI simulator."""
import importlib.util
from pathlib import Path

def fixture_module():
    file = Path(__file__).resolve().parents[1] / "devtools" / "mock_switch.py"
    spec = importlib.util.spec_from_file_location("mock_switch", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_simulator_returns_variable_port_counts():
    m = fixture_module()
    from bs4 import BeautifulSoup
    for count in (5, 10, 16, 24):
        page = m.fixture("/info.cgi", count)
        tables = BeautifulSoup(page, "html.parser").find_all("table")
        assert len(tables[1].find_all("tr")) == count + 1

def test_simulator_covers_monitored_endpoints():
    m = fixture_module()
    for path in (
        "/info.cgi", "/port.cgi?page=stats", "/port.cgi",
        "/mac.cgi?page=fwd_tbl", "/transceiver.cgi",
        "/dhcp_snooping.cgi?page=dump",
        "/igmp.cgi?page=dump", "/fwd.cgi?page=jumboframe",
    ):
        assert m.fixture(path, 10)

def test_simulator_unknown_endpoint():
    m = fixture_module()
    assert m.fixture("/reboot.cgi", 10) is None
