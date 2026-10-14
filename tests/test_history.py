"""SQLite history integration tests without Home Assistant runtime."""
import asyncio
import importlib.util
import sys
import types
import time
from pathlib import Path
from tempfile import TemporaryDirectory


def load():
    directory=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"
    package=types.ModuleType("hora_history_test_package")
    package.__path__=[str(directory)]
    sys.modules[package.__name__]=package
    helper_spec=importlib.util.spec_from_file_location(
        "hora_history_test_package.traffic_guard",directory/"traffic_guard.py")
    helper=importlib.util.module_from_spec(helper_spec)
    sys.modules[helper_spec.name]=helper
    helper_spec.loader.exec_module(helper)
    spec=importlib.util.spec_from_file_location(
        "hora_history_test_package.history",directory/"history.py")
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module

class FakeHass:
    def __init__(self, root):
        self.root=Path(root)
        self.config=self

    def path(self, *parts):
        return str(self.root.joinpath(*parts))

    async def async_add_executor_job(self, func, *args):
        return await asyncio.to_thread(func, *args)


def test_sqlite_persists_traffic_and_inventory():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root), "test_switch")
        await db.initialize()
        await db.record_traffic({"2":{"rx_bps":1500,"tx_bps":2500}})
        first=await db.traffic_summary()
        assert first["peaks"]["total"]["rx_bps"]==1500
        assert len(first["traffic_history"])==1
        assert first["traffic_history"][0]["tx"]==2500
        record={"mac":"00:11:22:33:44:55","vlan":"20","port":"2",
                "first_seen":"2026-01-01T00:00:00+00:00",
                "last_seen":"2026-01-02T00:00:00+00:00",
                "vendor":"Desconhecido","classification":"globally_administered"}
        await db.record_inventory([record])
        record["vendor"]="Example Vendor"
        record["last_seen"]="2026-01-03T00:00:00+00:00"
        await db.record_inventory([record])
        from sqlite3 import connect
        with connect(db.path) as connection:
            row=connection.execute("SELECT vendor,first_seen,last_seen FROM mac_inventory").fetchone()
        assert row==("Example Vendor","2026-01-01T00:00:00+00:00","2026-01-03T00:00:00+00:00")
        reloaded=load().HistoryDatabase(FakeHass(root),"test_switch")
        await reloaded.initialize()
        assert len((await reloaded.traffic_summary())["traffic_history"])==1

    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_reclassification_and_deduplicated_snapshots():
    class Vendors:
        def lookup(self, mac):
            return "Example Manufacturer" if mac == "00:11:22:33:44:55" else "Desconhecido"

    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"other_switch")
        await db.initialize()
        await db.record_inventory([{
            "mac":"00:11:22:33:44:55", "vlan":"1", "port":"3",
            "first_seen":"2026-01-01T00:00:00+00:00",
            "last_seen":"2026-01-02T00:00:00+00:00",
            "vendor":"Desconhecido","classification":"globally_administered",
        }])
        updated=await db.reclassify_inventory(Vendors())
        assert updated==1
        inventory=await db.inventory_summary()
        assert inventory["mac_history_entries"][0]["vendor"]=="Example Manufacturer"
        assert inventory["mac_history_entries"][0]["first_seen"]=="2026-01-01T00:00:00+00:00"
        await db.record_snapshot("vlan_ports",{"port_count":1})
        await db.record_snapshot("vlan_ports",{"port_count":1})
        await db.record_snapshot("vlan_ports",{"port_count":2})
        assert len(await db.recent_changes())==2
        day_views=await db.snapshot_history("vlan_ports")
        assert len(day_views)==1 and day_views[0]["checks"]==3
        assert day_views[0]["changes"]==2

    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_30_day_buckets_daily_traffic_and_history_filters():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"bucket_switch")
        await db.initialize()
        # Initial counters establish the baseline; they are not counted as traffic.
        await db.record_traffic({"2":{"rx_bps":1500,"tx_bps":900,
                                     "rx_bytes":10000,"tx_bytes":30000}})
        await asyncio.sleep(0.05)
        await db.record_traffic({"2":{"rx_bps":2500,"tx_bps":1200,
                                     "rx_bytes":12000,"tx_bytes":35000}})
        totals=await db.daily_totals("2")
        assert sum(r["rx_bytes"] for r in totals)==2000
        assert sum(r["tx_bytes"] for r in totals)==5000
        whole=await db.daily_totals("__total__")
        assert whole[0]["rx_bytes"]==2000
        assert whole[0]["tx_bytes"]==5000
        series=await db.series("2",720)
        assert series
        assert max(r["rx"] for r in series)>=1500
        assert (await db.traffic_summary())["peaks"]["ports"]["2"]["rx_bps"]==2500
        await db.record_snapshot("vlan_ports",{"ports":{"2":{"mode":"trunk"}}})
        snapshots=await db.snapshot_history("vlan_ports")
        assert snapshots and snapshots[0]["events"][0]["data"]["ports"]["2"]["mode"]=="trunk"
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_existing_raw_samples_upgrade_to_five_minute_buckets():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"migrating")
        await db.initialize()
        await db.record_traffic({"1":{"rx_bps":6000,"tx_bps":8000}})
        from sqlite3 import connect
        with connect(db.path) as conn:
            conn.execute("DELETE FROM traffic_5m")
            conn.execute("PRAGMA user_version=0")
        new_db=load().HistoryDatabase(FakeHass(root),"migrating")
        await new_db.initialize()
        history=await new_db.series("1",720)
        assert history and history[-1]["rx"]==6000
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_restart_restores_recent_baselines_and_avoids_double_counts():
    async def scenario(root):
        factory = load().HistoryDatabase
        first = factory(FakeHass(root), "restart")
        await first.initialize()
        await first.record_traffic({"2": {"rx_bps":80, "tx_bps":40,
                                         "rx_bytes":1000, "tx_bytes":2000}})
        second = factory(FakeHass(root), "restart")
        await second.initialize()
        assert second.previous_counters["2"] == (1000, 2000)
        await asyncio.sleep(0.05)
        await second.record_traffic({"2": {"rx_bps":120, "tx_bps":80,
                                          "rx_bytes":1300, "tx_bytes":2500}})
        values = await second.daily_totals("2")
        assert sum(x["rx_bytes"] for x in values) == 300
        assert sum(x["tx_bytes"] for x in values) == 500
        await second.initialize()
        values2 = await second.daily_totals("2")
        assert values2 == values
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_unknown_dates_do_not_replace_known_mac_timestamps():
    async def scenario(root):
        db = load().HistoryDatabase(FakeHass(root), "dates")
        await db.initialize()
        item={"mac":"00:11:22:33:44:55","vlan":"1","port":"2","vendor":"Example",
              "classification":"globally_administered",
              "first_seen":"2026-01-01T00:00:00+00:00",
              "last_seen":"2026-01-02T00:00:00+00:00"}
        await db.record_inventory([item])
        item["first_seen"]=None
        item["last_seen"]=None
        await db.record_inventory([item])
        saved=await db.inventory_summary()
        assert saved["mac_history_entries"][0]["first_seen"]=="2026-01-01T00:00:00+00:00"
        assert saved["mac_history_entries"][0]["last_seen"]=="2026-01-02T00:00:00+00:00"
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_daily_totals_reject_resets_and_impossible_jumps():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"unsafe_counters")
        await db.initialize()
        base={"speed":"100M","rx_bps":1000,"tx_bps":1000,
              "rx_bytes":1000,"tx_bytes":1000}
        await db.record_traffic({"2":base})
        await asyncio.sleep(0.05)
        await db.record_traffic({"2":{**base,"rx_bytes":2000,"tx_bytes":2000}})
        # One counter resets; the other advances safely.
        await asyncio.sleep(0.05)
        await db.record_traffic({"2":{**base,"rx_bytes":25,"tx_bytes":3000}})
        # The new RX baseline is 25, so the next valid sample counts from 25.
        await asyncio.sleep(0.05)
        await db.record_traffic({"2":{**base,"rx_bytes":125,"tx_bytes":10**11}})
        await asyncio.sleep(0.05)
        await db.record_traffic({"2":{**base,"rx_bytes":225,"tx_bytes":10**11+500}})
        total=(await db.daily_totals("2"))[0]
        assert total["rx_bytes"] == 1200
        assert total["tx_bytes"] == 2500
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_old_snapshot_events_not_hidden_by_zero_change_daily_summary():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"history_migration")
        await db.initialize()
        await db.record_snapshot("stp_ports",{"ports":{"1":{"state":"Forwarding"}}})
        from sqlite3 import connect
        with connect(db.path) as conn:
            conn.execute("UPDATE snapshot_daily SET changes=0 WHERE switch_id=?",("history_migration",))
        rows=await db.snapshot_history("stp_ports")
        assert len(rows)==1
        assert rows[0]["changes"]==1
        assert len(rows[0]["events"])==1
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_sfp_temperature_independent_from_change_audit():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"sfp_series")
        await db.initialize()
        base={"vendor":"ODI","part_number":"DFP-34X-2IY3","module_present":"Yes",
              "temperature_c":64.25,"temp":"64-64","voltage_v":3.12}
        await db.record_snapshot("sfp",base)
        await db.record_snapshot("sfp",{**base,"temperature_c":68.50,"temp":"68-128"})
        days=await db.snapshot_history("sfp")
        assert len(days)==1
        assert days[0]["checks"]==2
        assert days[0]["changes"]==1
        assert len(days[0]["events"])==1
        assert "temperature_c" not in days[0]["events"][0]["data"]
        assert "temp" not in days[0]["events"][0]["data"]
        series=await db.temperature_history(24)
        assert series["count"]==2
        assert series["min"]==64.25
        assert series["max"]==68.50
        assert abs(series["average"]-66.375)<0.0001
        assert len(series["items"])==1
        await db.record_snapshot("sfp",{**base,"temperature_c":70.0,"voltage_v":3.25,"module_present":"No"})
        days=await db.snapshot_history("sfp")
        assert days[0]["changes"]==2
        assert len(days[0]["events"])==2
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_sfp_temperature_rejects_invalid_measurements_and_survives_restart():
    async def scenario(root):
        factory=load().HistoryDatabase
        db=factory(FakeHass(root),"sfp_valid")
        await db.initialize()
        for invalid in (None, float("nan"), 300, -90, True, "65"):
            await db.record_snapshot("sfp",{"vendor":"ODI","temperature_c":invalid})
        assert (await db.temperature_history(24))["count"]==0
        await db.record_snapshot("sfp",{"vendor":"ODI","temperature_c":65.1})
        reopened=factory(FakeHass(root),"sfp_valid")
        await reopened.initialize()
        result=await reopened.temperature_history(24)
        assert result["count"]==1
        assert result["min"]==result["max"]==65.1
        # A former snapshot containing raw temperature must not trigger a
        # new event simply because the parser now removes temperature.
        from sqlite3 import connect
        import json,hashlib
        with connect(reopened.path) as con:
            con.execute("DELETE FROM snapshots WHERE switch_id=? AND kind='sfp'",("sfp_valid",))
            legacy={"vendor":"ODI","temperature_c":62.0,"temp":"62-0"}
            encoded=json.dumps(legacy,sort_keys=True)
            digest=hashlib.sha256(encoded.encode()).hexdigest()
            from datetime import datetime,timezone
            con.execute("INSERT INTO snapshots VALUES(?,?,?,?,?)",(
                "sfp_valid","sfp",datetime.now(timezone.utc).isoformat(),digest,encoded))
        old_count=(await reopened.snapshot_history("sfp"))[0]["changes"]
        await reopened.record_snapshot("sfp",{"vendor":"ODI","temperature_c":67.0})
        assert (await reopened.snapshot_history("sfp"))[0]["changes"]==old_count
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_sfp_volatile_optics_do_not_generate_changes():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"sfp_volatility")
        await db.initialize()
        initial={
            "vendor":"ODI","part_number":"DFP-34X-2IY3",
            "module_present":"Yes","loss_of_signal":"No",
            "temperature_c":64.0,"temp":"64-0",
            "voltage_v":3.12,"voltage":"121-66",
            "current_ma":0.0,"current":"0-0",
            "rx_dbm":-40.0,"rxpower":"0-1",
            "tx_dbm":-40.0,"txpower":"0-1",
        }
        await db.record_snapshot("sfp",initial)
        changed={**initial,"temperature_c":67.0,"temp":"67-0",
                 "voltage_v":3.27,"voltage":"127-188",
                 "current_ma":12.0,"current":"23-112",
                 "rx_dbm":-17.5,"rxpower":"1-120",
                 "tx_dbm":1.3,"txpower":"3-120"}
        await db.record_snapshot("sfp",changed)
        days=await db.snapshot_history("sfp")
        assert days[0]["checks"]==2
        assert days[0]["changes"]==1
        assert len(days[0]["events"])==1
        for field in ("temperature_c","voltage_v","current_ma","rx_dbm","tx_dbm",
                      "temp","voltage","current","rxpower","txpower"):
            assert field not in days[0]["events"][0]["data"]
        await db.record_snapshot("sfp",{**changed,"loss_of_signal":"Yes"})
        days=await db.snapshot_history("sfp")
        assert days[0]["changes"]==2
        assert days[0]["events"][0]["data"]["loss_of_signal"]=="Yes"
        await db.record_snapshot("sfp",{**changed,"part_number":"DIFFERENT"})
        days=await db.snapshot_history("sfp")
        assert days[0]["changes"]==3
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))


def test_legacy_sfp_snapshots_with_optical_metrics_do_not_create_false_event():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"sfp_legacy_fields")
        await db.initialize()
        import json, hashlib
        from sqlite3 import connect
        from datetime import datetime,timezone
        old={"vendor":"ODI","module_present":"Yes","voltage_v":3.1,
             "rx_dbm":-40.0,"tx_dbm":-40.0,"current_ma":0.0,"temperature_c":65.0}
        encoded=json.dumps(old,sort_keys=True)
        with connect(db.path) as con:
            con.execute("INSERT INTO snapshots VALUES(?,?,?,?,?)",(
                "sfp_legacy_fields","sfp",datetime.now(timezone.utc).isoformat(),
                hashlib.sha256(encoded.encode()).hexdigest(),encoded))
        await db.record_snapshot("sfp",{"vendor":"ODI","module_present":"Yes",
                                        "voltage_v":3.25,"rx_dbm":-20.0,
                                        "tx_dbm":1.0,"current_ma":5.0,
                                        "temperature_c":70.0})
        days=await db.snapshot_history("sfp")
        assert len(days[0]["events"])==1
        assert days[0]["changes"]==1  # an existing legacy event remains counted
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_optical_7day_series_and_no_snapshot_noise():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"optical_switch")
        await db.initialize()
        initial={"vendor":"ODI","module_present":"Yes","temperature_c":65,
                 "voltage_v":3.13,"current_ma":0.0,"rx_dbm":-40.0,"tx_dbm":-40.0}
        await db.record_snapshot("sfp",initial)
        await db.record_snapshot("sfp",{**initial,
            "voltage_v":3.18,"current_ma":16.0,"rx_dbm":-17.5,"tx_dbm":1.0})
        changes=await db.snapshot_history("sfp")
        assert changes[0]["changes"]==1
        assert changes[0]["checks"]==2
        for metric,low,high in (
            ("voltage_v",3.13,3.18),("current_ma",0.0,16.0),
            ("rx_dbm",-40.0,-17.5),("tx_dbm",-40.0,1.0)):
            result=await db.optical_history(metric,24)
            assert result["count"]==2
            assert result["min"]==low
            assert result["max"]==high
            assert len(result["items"])==1
        with __import__("sqlite3").connect(db.path) as conn:
            # Artificially date a bucket >7 days ago to verify pruning on collection.
            conn.execute("""UPDATE sfp_optical_5m SET bucket='2020-01-01T00:00:00+00:00'
                WHERE switch_id=? AND metric='voltage_v'""",("optical_switch",))
        await db.record_snapshot("sfp",{**initial,"voltage_v":3.20})
        history=await db.optical_history("voltage_v",168)
        assert history["count"]==1
        assert history["min"]==3.20
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))


def test_optical_rejects_invalid_values_and_survives_restart():
    async def scenario(root):
        factory=load().HistoryDatabase
        db=factory(FakeHass(root),"optical_valid")
        await db.initialize()
        for invalid in (None,float("nan"),float("inf"),-50,1000,True,"3.2"):
            await db.record_snapshot("sfp",{"vendor":"ODI","voltage_v":invalid})
        assert (await db.optical_history("voltage_v",24))["count"]==0
        await db.record_snapshot("sfp",{"vendor":"ODI","voltage_v":3.22,
                                        "current_ma":0.0})
        other=factory(FakeHass(root),"optical_valid")
        await other.initialize()
        assert (await other.optical_history("voltage_v",24))["count"]==1
        assert (await other.optical_history("current_ma",24))["min"]==0
        try:
            await other.optical_history("bad_metric",24)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsupported optical metric should be rejected")
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_sqlite_storage_summary_reports_actual_rows_and_reusable_space():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"storage_test")
        await db.initialize()
        await db.record_traffic({"2":{"rx_bps":200,"tx_bps":500,
                                      "rx_bytes":1200,"tx_bytes":600}})
        await db.record_snapshot("sfp",{"vendor":"ODI","temperature_c":66.0,"voltage_v":3.1})
        data=await db.storage_summary()
        assert data["scope"]=="whole_database"
        assert data["file_bytes"]>=data["used_bytes"]>0
        assert data["free_bytes"]>=0
        assert data["file_bytes"]==data["used_bytes"]+data["free_bytes"]
        assert data["rows"]["traffic"]>=1
        assert data["rows"]["traffic_5m"]>=1
        assert data["rows"]["sfp_temperature_5m"]==1
        assert data["rows"]["sfp_optical_5m"]==1
        assert data["rows"]["snapshots"]==1
        assert data["rows"]["snapshot_daily"]==1
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))


def test_sfp_temp_pruning_runs_even_without_valid_temperature():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"expired_sfp")
        await db.initialize()
        await db.record_snapshot("sfp",{"vendor":"ODI","temperature_c":55})
        from sqlite3 import connect
        with connect(db.path) as connection:
            connection.execute("UPDATE sfp_temperature_5m SET bucket=? WHERE switch_id=?",
                               ("2020-01-01T00:00:00+00:00","expired_sfp"))
        await db.record_snapshot("sfp",{"vendor":"ODI","temperature_c":None})
        assert (await db.temperature_history(720))["count"]==0
        with connect(db.path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM sfp_temperature_5m").fetchone()[0]==0
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_snapshot_history_indicates_truncated_event_list():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"many_events")
        await db.initialize()
        from datetime import datetime,timedelta,timezone
        from sqlite3 import connect
        import hashlib,json
        with connect(db.path) as conn:
            base=datetime.now(timezone.utc)-timedelta(minutes=190)
            day=datetime.now(db.tz).date().isoformat()
            for i in range(190):
                payload=json.dumps({"sequence":i})
                ts=(base+timedelta(minutes=i)).isoformat()
                conn.execute("INSERT INTO snapshots VALUES(?,?,?,?,?)",
                    ("many_events","sfp",ts,hashlib.sha256(payload.encode()).hexdigest(),payload))
            conn.execute("INSERT INTO snapshot_daily VALUES(?,?,?,?,?,?,?)",
                ("many_events","sfp",day,datetime.now(timezone.utc).isoformat(),"hash",190,190))
        entries=await db.snapshot_history("sfp")
        assert entries[0]["events_limited"] is True
        assert entries[0]["events_total"]==190
        assert entries[0]["events_returned"]==180
        assert entries[0]["changes"]==190
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))
