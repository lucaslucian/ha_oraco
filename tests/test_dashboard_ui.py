"""Guard the dashboard's read-only monitoring interactions."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"


def test_interactive_monitoring_sections_are_wired():
    text=(ROOT/"frontend"/"ha-oraco-panel.js").read_text(encoding="utf-8")
    for feature in (
        "portDialog()", "data-open-port", "data-port-history",
        "data-name-mac", "data-inventory-filter", "data-board-node",
        "data-add-manual", "data-remove-manual", "data-reset-board",
        "data-sfp-limit-metric", "data-compact-toggle", "snapshotDifference(",
        "data-chart-hours-select",
    ):
        assert feature in text
    assert "ha_oraco/preference" in text
    assert "data-wire-from" in text and "data-wire-to" in text
    assert "stroke-dasharray" in text


def test_admin_only_preferences_and_history_commands():
    text=(ROOT/"panel.py").read_text(encoding="utf-8")
    assert 'ha_oraco/preference' in text
    assert 'DashboardPreferences' in text
    assert 'require_admin' in text
    assert 'ha_oraco/history' in text
    assert 'sfp_optical' in text


def test_switch_remains_monitor_only():
    text=(ROOT/"frontend"/"ha-oraco-panel.js").read_text(encoding="utf-8")
    assert "Configurar limites" in text
    assert "Informado manualmente" in text
    assert "Conexões físicas" not in text or "lógica" in text


def test_chart_visuals_and_responsive_layout():
    js=(ROOT/"frontend"/"ha-oraco-panel.js").read_text(encoding="utf-8")
    for feature in ("xAt(i)", "const timeline=", "prefers-reduced-motion",
                    ".optical-history-grid{grid-template-columns:repeat(2",
                    "font-variant-numeric:tabular-nums",
                    ".audit-dialog{width:min(1100px"):
        assert feature in js
    assert "data-wire-from" in js

def test_history_websocket_sends_valid_optional_fields():
    js=(ROOT/"frontend"/"ha-oraco-panel.js").read_text(encoding="utf-8")
    assert 'if(mode==="sfp_optical")request.metric=kind;' in js
    assert 'if(mode==="snapshots")request.kind=kind;' in js
    assert 'mode,port,hours,kind,metric:kind' not in js

def test_history_errors_are_human_readable_and_retryable():
    js=(ROOT/"frontend"/"ha-oraco-panel.js").read_text(encoding="utf-8")
    assert "readableError(error)" in js
    assert "error:this.readableError(error)" in js
    assert 'data-retry-history' in js
    assert 'metric:kind' not in js
    assert 'Array.isArray(data)' in js
    assert 'history-array-item' in js


def test_signed_optical_limits_are_supported():
    js=(ROOT/"frontend"/"ha-oraco-panel.js").read_text(encoding="utf-8")
    assert 'parseSigned=value=>' in js
    assert 'replace("−","-")' in js
    assert 'Primeiro extremo' in js
    assert 'Math.min(a,b)' in js
    assert 'Math.max(a,b)' in js


def test_snapshot_history_errors_are_structured_and_retryable():
    js=(ROOT/"frontend"/"ha-oraco-panel.js").read_text(encoding="utf-8")
    assert 'this.escape(this.readableError(result.error))' in js
    assert 'data-retry-snapshot="true"' in js
    assert 'this.snapshotModal.kind' in js
    assert 'if(result?.error)throw result.error;' in js
    assert 'JSON.stringify(value)' in js
    assert 'value==="[object Object]"' in js
    panel=(ROOT/"panel.py").read_text(encoding="utf-8")
    manifest=(ROOT/"manifest.json").read_text(encoding="utf-8")
    assert '?v=0.4.37' in panel
    assert '"version": "0.4.37"' in manifest
