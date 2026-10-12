"""Read-only firmware metadata fixtures."""
import importlib.util
from pathlib import Path
path=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"/"firmware.py"
spec=importlib.util.spec_from_file_location("fwparser",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_firmware_version_only():
    html="""<html><form method="post" action="fwug.cgi">
    <table><tr><th>Firmware Version:</th><td>V200.2.4</td></tr></table>
    <input type="hidden" name="cmd" value="enter_loader">
    </form></html>"""
    assert module.parse_firmware(html)["version"]=="V200.2.4"

def test_reject_no_version():
    try:
        module.parse_firmware('<input name="cmd" value="enter_loader">')
    except ValueError:
        return
    assert False, "missing firmware version must fail"
