"""Regression checks for modal history and MAC sensor semantics."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"

def test_history_is_modal_not_expanded_inline():
    js=(ROOT/"frontend"/"ha-oraco-panel.js").read_text(encoding="utf-8")
    assert 'role="dialog"' in js
    assert 'data-close-audit' in js
    assert 'data-modal-backdrop' in js
    assert 'data-audit-day' in js
    assert 'this.snapshotDialog()' in js
    assert 'return \'<button class="history-action" data-snapshot-switch=' in js

def test_local_mac_sensor_is_explicitly_scoped():
    source=(ROOT/"sensor.py").read_text(encoding="utf-8")
    assert 'MACs privados (atuais)' in source
    assert 'MACs privados (histórico)' in source

def test_mac_classification_examples():
    import importlib.util
    spec=importlib.util.spec_from_file_location("hora_mac",ROOT/"mac.py")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for mac in ("E8:4C:4A:21:A8:5D","B8:27:EB:44:9E:FF","DC:A6:32:3D:35:CD"):
        assert mod.mac_classification(mac)=="globally_administered"
    assert mod.mac_classification("02:11:22:33:44:55")=="locally_administered"
