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
