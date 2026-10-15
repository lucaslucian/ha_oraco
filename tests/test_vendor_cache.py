"""Regression coverage for persisted OUI refresh state."""
import asyncio
import copy
import importlib.util
import sys
import types
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"


def make_vendor(monkeypatch):
    home=types.ModuleType("homeassistant")
    helpers=types.ModuleType("homeassistant.helpers")
    storage=types.ModuleType("homeassistant.helpers.storage")
    class Store:
        def __init__(self,hass,version,key):
            self.hass=hass
        async def async_load(self):
            return copy.deepcopy(self.hass.saved)
        async def async_save(self,data):
            self.hass.saved=copy.deepcopy(data)
    storage.Store=Store
    for name,value in (("homeassistant",home),("homeassistant.helpers",helpers),
                       ("homeassistant.helpers.storage",storage)):
        monkeypatch.setitem(sys.modules,name,value)
    package=types.ModuleType("hora_vendor_test")
    package.__path__=[str(ROOT)]
    monkeypatch.setitem(sys.modules,package.__name__,package)
    macspec=importlib.util.spec_from_file_location("hora_vendor_test.mac",ROOT/"mac.py")
    mac=importlib.util.module_from_spec(macspec)
    monkeypatch.setitem(sys.modules,macspec.name,mac)
    macspec.loader.exec_module(mac)
    spec=importlib.util.spec_from_file_location("hora_vendor_test.vendors",ROOT/"vendors.py")
    mod=importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules,spec.name,mod)
    spec.loader.exec_module(mod)
    return mod.VendorCache


class BrokenSession:
    def get(self,*_args,**_kwargs):
        class Request:
            async def __aenter__(self):
                raise OSError("offline")
            async def __aexit__(self,*_args):
                return None
        return Request()


def test_failed_oui_attempt_is_persisted_without_deleting_existing_cache(monkeypatch):
    Cache=make_vendor(monkeypatch)
    async def run():
        hass=types.SimpleNamespace(saved={
            "prefixes":{"B827EB":"Raspberry Pi"},
            "last_updated":"2026-10-01T10:00:00+00:00"})
        obj=Cache(hass)
        await obj.load()
        assert obj.last_attempt is None
        await obj.refresh(BrokenSession())
        assert obj.last_attempt
        assert obj.last_updated=="2026-10-01T10:00:00+00:00"
        assert obj.prefixes["B827EB"]=="Raspberry Pi"
        assert hass.saved["last_attempt"]==obj.last_attempt
        assert hass.saved["sources"]["github_oui_mirror"]["status"]=="failed"
        restored=Cache(hass)
        await restored.load()
        assert restored.last_attempt==obj.last_attempt
        assert restored.source_status["github_oui_mirror"]["status"]=="failed"
    asyncio.run(run())
