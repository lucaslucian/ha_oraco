"""Offline regression for MAC pagination authentication renewal."""
import asyncio
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"/"api.py"
spec=importlib.util.spec_from_file_location("hora_http",ROOT)
api=importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

class Response:
    def __init__(self,status,body):
        self.status=status
        self.body=body
    async def __aenter__(self):
        return self
    async def __aexit__(self,*exc):
        pass
    async def text(self,**kwargs):
        return self.body

class Session:
    def __init__(self):
        self.mac_calls=0
        self.login_calls=0
    def post(self,url,**kwargs):
        if url.endswith("/login.cgi"):
            self.login_calls+=1
            return Response(200,"ok")
        self.mac_calls+=1
        if self.mac_calls==1:
            return Response(403,"expired")
        return Response(200,"<table><tr><td>Valid</td></tr></table>")

def test_mac_expired_session_recovers_once():
    async def scenario():
        session=Session()
        client=api.HoracoClient(session,"192.0.2.1",80,"admin","secret")
        html=await client.mac_page(2)
        assert "Valid" in html
        assert session.login_calls==2
        assert session.mac_calls==2
        await client.mac_page(2)
        assert session.login_calls==2
    asyncio.run(scenario())
