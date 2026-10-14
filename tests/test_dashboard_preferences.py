"""Dashboard preference persistence and validation, no Home Assistant installation."""
import asyncio
import copy
import importlib.util
import sys
import types
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"


def load(monkeypatch):
    class FakeStore:
        def __init__(self,hass,version,key):
            self.hass=hass
        async def async_load(self):
            return copy.deepcopy(self.hass.saved)
        async def async_save(self,value):
            self.hass.saved=copy.deepcopy(value)
    home=types.ModuleType("homeassistant")
    helpers=types.ModuleType("homeassistant.helpers")
    storage=types.ModuleType("homeassistant.helpers.storage")
    storage.Store=FakeStore
    monkeypatch.setitem(sys.modules,"homeassistant",home)
    monkeypatch.setitem(sys.modules,"homeassistant.helpers",helpers)
    monkeypatch.setitem(sys.modules,"homeassistant.helpers.storage",storage)
    spec=importlib.util.spec_from_file_location("hora_preferences",ROOT/"dashboard_preferences.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DashboardPreferences


def test_persist_names_layout_ranges_and_thresholds(monkeypatch):
    Preferences=load(monkeypatch)
    async def scenario():
        hass=types.SimpleNamespace(saved={})
        prefs=Preferences(hass)
        await prefs.load()
        await prefs.set_item("switch1","ports","2","ONU")
        await prefs.set_item("switch1","devices","E8:4C:4A:21:A8:5D","Camera")
        await prefs.set_item("switch1","layout","mac:E8:4C:4A:21:A8:5D|1",{"x":72.5,"y":40})
        await prefs.set_item("switch1","infrastructure","nabc",{"name":"Switch adicional","port":"2"})
        await prefs.set_item("switch1","layout","manual:nabc",{"x":44,"y":62})
        await prefs.set_item("switch1","options","default_hours",168)
        await prefs.set_item("switch1","options","compact",True)
        await prefs.set_item("switch1","thresholds","temperature_c",{"low":5,"high":85})
        restored=Preferences(hass)
        await restored.load()
        sw=restored.for_switch("switch1")
        assert sw["ports"]["2"]=="ONU"
        assert sw["devices"]["E8:4C:4A:21:A8:5D"]=="Camera"
        assert sw["layout"]["mac:E8:4C:4A:21:A8:5D|1"]["x"]==72.5
        assert sw["options"]["compact"] is True
        assert sw["infrastructure"]["nabc"]["port"]=="2"
        assert sw["thresholds"]["temperature_c"]["high"]==85
        await restored.set_item("switch1","layout","mac:E8:4C:4A:21:A8:5D|1",None)
        assert "mac:E8:4C:4A:21:A8:5D|1" not in restored.for_switch("switch1")["layout"]
        await restored.set_item("switch1","infrastructure","nabc",None)
        assert "nabc" not in restored.for_switch("switch1")["infrastructure"]
    asyncio.run(scenario())


def test_rejects_unsafe_or_invalid_preferences(monkeypatch):
    Preferences=load(monkeypatch)
    async def scenario():
        prefs=Preferences(types.SimpleNamespace(saved={}))
        await prefs.load()
        invalid=[
            ("devices","not-a-mac","Camera"),
            ("ports","../../etc/passwd","uplink"),
            ("layout","mac:E8:4C:4A:21:A8:5D|1",{"x":999,"y":5}),
            ("layout","bad-key",{"x":5,"y":5}),
            ("options","default_hours",9999),
            ("options","compact","yes"),
            ("thresholds","temperature_c",{"low":100,"high":20}),
            ("thresholds","rx_dbm",{"low":float("nan"),"high":0}),
            ("thresholds","bad_metric",{"low":0,"high":1}),
            ("ports","1","x"*81),
            ("infrastructure","unsafe key",{"name":"X","port":"1"}),
            ("infrastructure","safe",{"name":"X","port":"bad"}),
        ]
        for category,key,value in invalid:
            try:
                await prefs.set_item("switch1",category,key,value)
            except ValueError:
                continue
            raise AssertionError(f"Accepted invalid {category}:{key}")
    asyncio.run(scenario())
