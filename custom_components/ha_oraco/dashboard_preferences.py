"""Persist dashboard annotations independently of switch observations."""
import re
from homeassistant.helpers.storage import Store

class DashboardPreferences:
    def __init__(self, hass):
        self.store=Store(hass,1,"ha_oraco_dashboard_preferences")
        self.data={}

    async def load(self):
        loaded=await self.store.async_load()
        self.data=loaded if isinstance(loaded,dict) else {}

    def for_switch(self,entry_id):
        return self.data.get(entry_id,{})

    async def set_item(self,entry_id,category,key,value):
        if category not in ("ports","devices","layout","options"):
            raise ValueError("Invalid preference category")
        if not isinstance(key,str) or not 1<=len(key)<=128:
            raise ValueError("Invalid preference key")
        if category=="ports" and not re.fullmatch(r"\d{1,4}",key):
            raise ValueError("Invalid port")
        if category=="devices" and not re.fullmatch(r"[0-9A-Fa-f:]{17}",key):
            raise ValueError("Invalid MAC")
        if category=="layout" and not re.fullmatch(r"(?:mac:[0-9A-Fa-f:]{17}|port:\d{1,4})",key):
            raise ValueError("Invalid node")
        if category=="options" and key not in ("default_hours","compact"):
            raise ValueError("Invalid option")
        if category=="layout" and value is not None:
            if not isinstance(value,dict) or set(value)!={"x","y"} or any(type(v) not in (int,float) or not 0<=v<=100 for v in value.values()):
                raise ValueError("Invalid position")
        elif category=="options":
            if key=="compact" and type(value) is not bool:
                raise ValueError("Invalid compact")
            if key=="default_hours" and value not in (1,6,12,24,72,120,168,360,720):
                raise ValueError("Invalid range")
        elif not isinstance(value,str) or len(value)>80:
            raise ValueError("Invalid label")
        item=self.data.setdefault(entry_id,{}).setdefault(category,{})
        if value=="" or value is None:
            item.pop(key,None)
        else:
            item[key]=value
        await self.store.async_save(self.data)
