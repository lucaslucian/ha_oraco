"""MAC topology must retain known friendly names and vendors."""
import importlib.util
from pathlib import Path

path=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"/"topology.py"
spec=importlib.util.spec_from_file_location("hora_topology",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_named_mac_nodes():
    ports={"2":{"up":True,"speed":"1000M"}}
    items=[{"mac":"E8:4C:4A:21:A8:5D","port":"2","vlan":"1",
            "vendor":"Example Manufacturer","name":"Access Point"}]
    topology=module.build_topology("10.0.0.254",ports,items)
    device=next(n for n in topology["nodes"] if n["kind"]=="learned_mac")
    assert device["label"]=="Access Point"
    assert device["vendor"]=="Example Manufacturer"
    assert device["mac"]=="E8:4C:4A:21:A8:5D"

def test_unnamed_mac_preserves_vendor():
    topology=module.build_topology("10.0.0.254",{"3":{"up":True}},
        [{"mac":"02:11:22:33:44:55","port":"3","vlan":"1","vendor":"Desconhecido"}])
    node=next(n for n in topology["nodes"] if n["kind"]=="learned_mac")
    assert node["label"]==node["mac"]
