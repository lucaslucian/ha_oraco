"""Counter safety regression cases from switch behavior."""
import importlib.util
from pathlib import Path

path=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"/"traffic_guard.py"
spec=importlib.util.spec_from_file_location("hora_traffic_guard",path)
guard=importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

def test_valid_64_bit_byte_counter_and_line_rate():
    assert guard.counter_delta(2**32-10,2**32+90,30,"1000M")== (100,None)
    assert guard.counter_delta(1000,2000,30,"2500M")== (1000,None)

def test_reset_wrap_and_bad_payload():
    for old,new in [(9000,100),(2**64-10,22)]:
        assert guard.counter_delta(old,new,30,"1000M")[0] is None
    for current in [-1,2**64,3.14,"1000",None,True]:
        assert guard.counter_delta(0,current,30,"1000M")[0] is None

def test_impossible_traffic_never_creates_peak():
    # 100 Mbit link cannot transfer 1 GB in 30 seconds.
    delta,reason=guard.counter_delta(1000,1_000_001_000,30,"100M")
    assert delta is None and reason=="impossible_jump"
    # A valid 10MB delta over 30sec must be preserved.
    assert guard.counter_delta(1000,10_001_000,30,"100M")[0]==10_000_000

def test_delays_rebaseline_without_claiming_missing_usage():
    assert guard.counter_delta(100,200,180,"1000M")== (None,"collection_gap")
    assert guard.counter_delta(200,300,30,"1000M")== (100,None)
    assert guard.counter_delta(100,200,0,"1000M")[0] is None

def test_auto_and_unknown_speed_safe_fallback():
    assert guard.link_capacity("2500M")==2_500_000_000
    assert guard.link_capacity("100M")==100_000_000
    assert guard.link_capacity("Auto")==guard.UNKNOWN_LINK_BPS
