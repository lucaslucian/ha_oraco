"""Prevent false SFP outages when only the optional historical recording fails."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "ha_oraco"

def test_sfp_read_route_is_allowed():
    source = (ROOT / "api.py").read_text(encoding="utf-8")
    assert '"/transceiver.cgi"' in source

def test_history_recording_failure_does_not_mask_successful_poll():
    source = (ROOT / "__init__.py").read_text(encoding="utf-8")
    start = source.index("for name, interval, path, parser in plans:")
    end = source.index("if self.inventory is not None",start)
    polling = source[start:end]
    assert 'self.diagnostics["endpoints"][name] = {' in polling
    assert 'try:\n                                await self.history_db.record_snapshot(name, parsed)' in polling
    assert '"history_error"' in polling

def test_system_tab_shows_endpoint_error_details():
    source = (ROOT / "frontend" / "ha-oraco-panel.js").read_text(encoding="utf-8")
    assert "v.history_error" in source
    assert "v.detail" in source
