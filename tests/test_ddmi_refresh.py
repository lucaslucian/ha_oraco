"""Exercise the DDMI cooldown/refresh coroutine without Home Assistant runtime."""
import ast
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic


def method():
    code=(Path(__file__).resolve().parents[1]/
          "custom_components/ha_oraco/__init__.py").read_text(encoding="utf-8")
    parsed=ast.parse(code)
    cls=next(x for x in parsed.body if isinstance(x,ast.ClassDef)
             and x.name=="HoracoCoordinator")
    node=next(x for x in cls.body if isinstance(x,ast.AsyncFunctionDef)
              and x.name=="async_refresh_ddmi")
    module=ast.Module(body=[node],type_ignores=[])
    ast.fix_missing_locations(module)
    namespace={"datetime":datetime,"timezone":timezone,"monotonic":monotonic,
               "_LOGGER":logging.getLogger(__name__),
               "parse_sfp":lambda html: {"module_present":"Yes","temperature_c":37.2}}
    exec(compile(module,"<ddmi>", "exec"),namespace)
    return namespace["async_refresh_ddmi"]


def test_manual_ddmi_is_read_only_rate_limited_and_emits_update():
    async def scenario():
        calls=[]
        class Client:
            async def get(self,path):
                calls.append(path)
                await asyncio.sleep(0)
                return "<table/>"
        class Fake:
            def __init__(self):
                self.client=Client()
                self._ddmi_lock=asyncio.Lock()
                self._ddmi_last_attempt=float("-inf")
                self.cache={"sfp":{}}
                self.diagnostics={"endpoints":{}}
                self.last={}
                self.history_db=None
                self.updated=[]
            def async_set_updated_data(self,data):
                self.updated.append(data)
        fake=Fake()
        run=method()
        result=await run(fake)
        assert result["status"]=="ok"
        assert calls==["/transceiver.cgi"]
        assert fake.cache["sfp"]["sfp"]["temperature_c"]==37.2
        assert fake.updated
        second=await run(fake)
        assert second["status"]=="rate_limited" and second["retry_after"]>0
        assert len(calls)==1
        fake._ddmi_last_attempt=float("-inf")
        await fake._ddmi_lock.acquire()
        busy=await run(fake)
        fake._ddmi_lock.release()
        assert busy["status"]=="busy"
        assert len(calls)==1
    asyncio.run(scenario())


def test_manual_ddmi_failure_clears_stale_current_values():
    async def scenario():
        class Client:
            async def get(self,path):
                raise OSError("offline")
        class Fake:
            def __init__(self):
                self.client=Client()
                self._ddmi_lock=asyncio.Lock()
                self._ddmi_last_attempt=float("-inf")
                self.cache={"sfp":{"sfp":{"temperature_c":99}}}
                self.diagnostics={"endpoints":{}}
                self.last={}
                self.history_db=None
                self.updated=[]
            def async_set_updated_data(self,data):
                self.updated.append(data)
        fake=Fake()
        result=await method()(fake)
        assert result=={"status":"error","error":"OSError"}
        assert "sfp" not in fake.cache["sfp"]
        assert fake.diagnostics["endpoints"]["sfp"]["status"]=="unavailable"
        assert fake.updated
    asyncio.run(scenario())
