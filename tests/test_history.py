"""SQLite history integration tests without Home Assistant runtime."""
import asyncio
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory


def load():
    path=Path(__file__).resolve().parents[1]/"custom_components"/"ha_oraco"/"history.py"
    spec=importlib.util.spec_from_file_location("hora_history",path)
    module=importlib.util.module_from_spec(spec)
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

    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))

def test_30_day_buckets_daily_traffic_and_history_filters():
    async def scenario(root):
        db=load().HistoryDatabase(FakeHass(root),"bucket_switch")
        await db.initialize()
        # Initial counters establish the baseline; they are not counted as traffic.
        await db.record_traffic({"2":{"rx_bps":1500,"tx_bps":900,
                                     "rx_bytes":10000,"tx_bytes":30000}})
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
        assert snapshots and snapshots[0]["data"]["ports"]["2"]["mode"]=="trunk"
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
        new_db=load().HistoryDatabase(FakeHass(root),"migrating")
        await new_db.initialize()
        history=await new_db.series("1",720)
        assert history and history[-1]["rx"]==6000
    with TemporaryDirectory() as root:
        asyncio.run(scenario(root))
