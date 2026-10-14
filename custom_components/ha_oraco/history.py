"""Persistent bounded time-series database for HoraInfo (per Home Assistant instance).

All SQLite operations run in Home Assistant's executor, off the event loop.
No switch credentials are stored here. Do not store user-provided SQL fragments.
"""
from __future__ import annotations

import sqlite3
import json
import hashlib
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .traffic_guard import counter_delta, valid_counter


# Continuous optical measurements belong to telemetry, not change auditing.
# Retain module identity, presence and loss-of-signal transitions as events.
SFP_TELEMETRY_FIELDS = frozenset((
    "temperature_c", "temp", "voltage_v", "voltage", "current_ma", "current",
    "rx_dbm", "tx_dbm", "rxpower", "txpower", "rx_power", "tx_power",
    "input_power_dbm", "output_power_dbm",
))


def _snapshot_state(kind, payload):
    if kind != "sfp":
        return payload
    return {key: value for key, value in payload.items()
            if key not in SFP_TELEMETRY_FIELDS}


class HistoryDatabase:
    def __init__(self, hass, key):
        self.hass = hass
        self.path = Path(hass.config.path(".storage", "ha_oraco_history.db"))
        self.key = key
        self.tz = ZoneInfo(getattr(hass.config, 'time_zone', None) or 'UTC')
        self.previous_counters = {}
        self.previous_stamps = {}

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.execute("PRAGMA busy_timeout=15000")
        return con

    def _initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS traffic (
                switch_id TEXT NOT NULL, timestamp TEXT NOT NULL,
                port TEXT NOT NULL, rx_bps REAL NOT NULL, tx_bps REAL NOT NULL,
                PRIMARY KEY (switch_id,timestamp,port)
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS idx_traffic_recent
                ON traffic(switch_id,port,timestamp)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_traffic_expiry ON traffic(timestamp)")
            db.execute("""CREATE TABLE IF NOT EXISTS traffic_5m (
                switch_id TEXT, bucket TEXT, port TEXT, rx_sum REAL, tx_sum REAL,
                count INTEGER, peak_rx REAL, peak_tx REAL,
                PRIMARY KEY(switch_id,bucket,port)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS traffic_baselines (
                switch_id TEXT NOT NULL, port TEXT NOT NULL,
                rx_bytes INTEGER NOT NULL, tx_bytes INTEGER NOT NULL,
                recorded_at TEXT NOT NULL, PRIMARY KEY(switch_id,port)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS daily_traffic (
                switch_id TEXT, day TEXT, port TEXT, rx_bytes INTEGER, tx_bytes INTEGER,
                PRIMARY KEY(switch_id,day,port)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_5m_expiry ON traffic_5m(bucket)")
            cols={row[1] for row in db.execute("PRAGMA table_info(traffic_5m)")}
            for name in ("rx_bytes","tx_bytes"):
                if name not in cols:
                    db.execute(f"ALTER TABLE traffic_5m ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")

            # Legacy migration must run only once; otherwise a subsequent restart
            # can reinsert expired data and change previously consolidated values.
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                db.execute("""INSERT OR IGNORE INTO traffic_5m
                    (switch_id,bucket,port,rx_sum,tx_sum,count,peak_rx,peak_tx)
                    SELECT switch_id,
                        substr(timestamp,1,14) ||
                        printf('%02d',CAST(substr(timestamp,15,2) AS INTEGER)/5*5) ||
                        ':00+00:00',port,
                        SUM(rx_bps),SUM(tx_bps),COUNT(*),MAX(rx_bps),MAX(tx_bps)
                    FROM traffic WHERE rx_bps>=0 AND tx_bps>=0
                    GROUP BY switch_id,
                        substr(timestamp,1,14) ||
                        printf('%02d',CAST(substr(timestamp,15,2) AS INTEGER)/5*5) ||
                        ':00+00:00',port
                """)
                db.execute("PRAGMA user_version=1")

            db.execute("""CREATE TABLE IF NOT EXISTS mac_inventory (
                switch_id TEXT NOT NULL, vlan TEXT NOT NULL, mac TEXT NOT NULL,
                port TEXT, vendor TEXT, classification TEXT,
                first_seen TEXT, last_seen TEXT,
                PRIMARY KEY (switch_id,vlan,mac)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS snapshots (
                switch_id TEXT NOT NULL, kind TEXT NOT NULL,
                timestamp TEXT NOT NULL, checksum TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (switch_id,kind,timestamp)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_expiry ON snapshots(timestamp)")
            db.execute("""CREATE TABLE IF NOT EXISTS sfp_temperature_5m (
                switch_id TEXT NOT NULL, bucket TEXT NOT NULL,
                sample_count INTEGER NOT NULL, temp_sum REAL NOT NULL,
                temp_min REAL NOT NULL, temp_max REAL NOT NULL,
                PRIMARY KEY(switch_id,bucket)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_sfp_temperature_expiry ON sfp_temperature_5m(bucket)")
            db.execute("""CREATE TABLE IF NOT EXISTS sfp_optical_5m (
                switch_id TEXT NOT NULL, metric TEXT NOT NULL, bucket TEXT NOT NULL,
                sample_count INTEGER NOT NULL, value_sum REAL NOT NULL,
                value_min REAL NOT NULL, value_max REAL NOT NULL,
                PRIMARY KEY(switch_id,metric,bucket)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_sfp_optical_expiry ON sfp_optical_5m(bucket)")
            db.execute("""CREATE TABLE IF NOT EXISTS snapshot_daily (
                switch_id TEXT, kind TEXT, day TEXT, checked_at TEXT,
                checksum TEXT, checks INTEGER, changes INTEGER,
                PRIMARY KEY(switch_id,kind,day)
            )""")

            db.execute("""CREATE INDEX IF NOT EXISTS idx_mac_seen
                ON mac_inventory(switch_id,last_seen)""")

    async def initialize(self):
        await self.hass.async_add_executor_job(self._initialize)
        self.previous_counters = await self.hass.async_add_executor_job(self._load_baselines)

    def _load_baselines(self):
        cutoff = datetime.now(timezone.utc)-timedelta(minutes=3)
        with self._connect() as db:
            rows = db.execute("SELECT port,rx_bytes,tx_bytes,recorded_at FROM traffic_baselines WHERE switch_id=?", (self.key,)).fetchall()
        result = {}
        for port,rx,tx,recorded in rows:
            try:
                if datetime.fromisoformat(recorded)>=cutoff:
                    result[port]=(rx,tx)
                    self.previous_stamps[port]=datetime.fromisoformat(recorded)
            except (ValueError,TypeError):
                continue
        return result

    def _record_traffic(self, ports):
        stamp = datetime.now(timezone.utc)
        timestamp = stamp.isoformat()
        bucket = stamp.replace(minute=stamp.minute // 5 * 5, second=0, microsecond=0).isoformat()
        day = stamp.astimezone(self.tz).date().isoformat()
        raw_rows = []
        buckets = []
        daily = []
        rx_total = tx_total = 0.0
        bytes_rx = bytes_tx = 0
        increments = {}
        baselines = []
        for number, port in ports.items():
            number = str(number)
            rx, tx = port.get("rx_bps"), port.get("tx_bps")
            rx_ok = isinstance(rx,(int,float)) and not isinstance(rx,bool) and math.isfinite(rx) and 0 <= rx < 1e13
            tx_ok = isinstance(tx,(int,float)) and not isinstance(tx,bool) and math.isfinite(tx) and 0 <= tx < 1e13
            if rx_ok and tx_ok:
                # Do not persist a fabricated zero for an unavailable direction.
                # Byte-counter daily deltas are still validated independently.
                measured_rx = rx
                measured_tx = tx
                rx_total += measured_rx
                tx_total += measured_tx
                raw_rows.append((self.key,timestamp,number,measured_rx,measured_tx))
                buckets.append((self.key,bucket,number,measured_rx,measured_tx,1,measured_rx,measured_tx))
            counters = (port.get("rx_bytes"), port.get("tx_bytes"))
            previous = self.previous_counters.get(number)
            previous_stamp = self.previous_stamps.get(number)
            if all(valid_counter(value) for value in counters):
                deltas = []
                for index in range(2):
                    old = previous[index] if previous else None
                    elapsed = (stamp - previous_stamp).total_seconds() if previous_stamp else None
                    delta, _reason = counter_delta(old, counters[index], elapsed, port.get("speed"))
                    deltas.append(delta)
                # Account directions independently: a TX reset must not erase valid RX.
                drx, dtx = (value if value is not None else 0 for value in deltas)
                if any(value is not None for value in deltas):
                    daily.append((self.key,day,number,drx,dtx))
                    increments[number]=(drx,dtx)
                    bytes_rx += drx
                    bytes_tx += dtx
                baselines.append((self.key,number,counters[0],counters[1],timestamp))
        if not raw_rows and not baselines:
            return
        if raw_rows:
            raw_rows.append((self.key,timestamp,"__total__",rx_total,tx_total))
            buckets.append((self.key,bucket,"__total__",rx_total,tx_total,1,rx_total,tx_total))
        if daily:
            daily.append((self.key,day,"__total__",bytes_rx,bytes_tx))
            increments["__total__"]=(bytes_rx,bytes_tx)
        with self._connect() as db:
            if raw_rows:
                db.executemany("INSERT OR REPLACE INTO traffic (switch_id,timestamp,port,rx_bps,tx_bps) VALUES(?,?,?,?,?)",raw_rows)
            db.executemany("""INSERT INTO traffic_5m (switch_id,bucket,port,rx_sum,tx_sum,count,peak_rx,peak_tx) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(switch_id,bucket,port) DO UPDATE SET
                rx_sum=rx_sum+excluded.rx_sum,tx_sum=tx_sum+excluded.tx_sum,
                count=count+1,peak_rx=MAX(peak_rx,excluded.peak_rx),
                peak_tx=MAX(peak_tx,excluded.peak_tx)""",buckets)
            if baselines:
                db.executemany("""INSERT INTO traffic_baselines
                    (switch_id,port,rx_bytes,tx_bytes,recorded_at) VALUES (?,?,?,?,?)
                    ON CONFLICT(switch_id,port) DO UPDATE SET
                    rx_bytes=excluded.rx_bytes,tx_bytes=excluded.tx_bytes,
                    recorded_at=excluded.recorded_at""",baselines)
            if increments:
                db.executemany("""UPDATE traffic_5m SET rx_bytes=rx_bytes+?,
                    tx_bytes=tx_bytes+? WHERE switch_id=? AND bucket=? AND port=?""",
                    [(values[0],values[1],self.key,bucket,num) for num,values in increments.items()])
            if daily:
                db.executemany("""INSERT INTO daily_traffic (switch_id,day,port,rx_bytes,tx_bytes) VALUES(?,?,?,?,?)
                    ON CONFLICT(switch_id,day,port) DO UPDATE SET
                    rx_bytes=rx_bytes+excluded.rx_bytes,
                    tx_bytes=tx_bytes+excluded.tx_bytes""",daily)
            db.execute("DELETE FROM traffic WHERE timestamp < ?",((stamp-timedelta(days=2)).isoformat(),))
            db.execute("DELETE FROM traffic_5m WHERE bucket < ?",((stamp-timedelta(days=30)).isoformat(),))
            db.execute("DELETE FROM daily_traffic WHERE day < ?",((stamp.astimezone(self.tz)-timedelta(days=30)).date().isoformat(),))
        # Move the in-memory baseline only after the transaction commits.
        for _switch, number, rx, tx, recorded in baselines:
            self.previous_counters[number] = (rx, tx)
            self.previous_stamps[number] = datetime.fromisoformat(recorded)

    async def record_traffic(self, ports):
        await self.hass.async_add_executor_job(self._record_traffic, ports)

    def _traffic_summary(self):
        with self._connect() as db:
            peaks = db.execute("""SELECT port,MAX(peak_rx),MAX(peak_tx)
                FROM traffic_5m WHERE switch_id=? GROUP BY port""", (self.key,)).fetchall()
            series = db.execute("""SELECT timestamp,rx_bps,tx_bps FROM traffic
                WHERE switch_id=? AND port='__total__'
                ORDER BY timestamp DESC LIMIT 240""", (self.key,)).fetchall()
            by_port = {}
            for (number,) in db.execute("SELECT DISTINCT port FROM traffic WHERE switch_id=? AND port!='__total__' LIMIT 64", (self.key,)).fetchall():
                data = db.execute("""SELECT timestamp,rx_bps,tx_bps FROM traffic
                    WHERE switch_id=? AND port=? ORDER BY timestamp DESC LIMIT 120""", (self.key,number)).fetchall()
                by_port[number] = [{"timestamp":row[0], "rx":row[1], "tx":row[2]} for row in reversed(data)]
        return {
            "peaks": {
                "total": {"rx_bps": next((r[1] for r in peaks if r[0]=="__total__"), 0),
                          "tx_bps": next((r[2] for r in peaks if r[0]=="__total__"), 0)},
                "ports": {r[0]: {"rx_bps": r[1], "tx_bps": r[2]}
                          for r in peaks if r[0]!="__total__"},
                "scope": "retained_30_days",
            },
            "traffic_by_port": by_port,
            "traffic_history": [{"timestamp": r[0], "rx": r[1], "tx": r[2]}
                                for r in reversed(series)],
        }

    async def traffic_summary(self):
        return await self.hass.async_add_executor_job(self._traffic_summary)

    def _record_inventory(self, records):
        values = []
        for item in records:
            if not item.get("mac"):
                continue
            values.append((self.key, str(item.get("vlan") or ""), item["mac"],
                           str(item.get("port") or ""), item.get("vendor"),
                           item.get("classification"), item.get("first_seen"),
                           item.get("last_seen")))
        with self._connect() as db:
            db.executemany("""INSERT INTO mac_inventory
                (switch_id,vlan,mac,port,vendor,classification,first_seen,last_seen)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(switch_id,vlan,mac) DO UPDATE SET
                port=excluded.port,
                vendor=CASE WHEN excluded.vendor IN ('Desconhecido','') OR excluded.vendor IS NULL
                  THEN mac_inventory.vendor ELSE excluded.vendor END,
                classification=excluded.classification,
                first_seen=CASE
                    WHEN mac_inventory.first_seen IS NULL THEN excluded.first_seen
                    WHEN excluded.first_seen IS NULL THEN mac_inventory.first_seen
                    WHEN mac_inventory.first_seen <= excluded.first_seen THEN mac_inventory.first_seen
                    ELSE excluded.first_seen END,
                last_seen=CASE
                    WHEN mac_inventory.last_seen IS NULL THEN excluded.last_seen
                    WHEN excluded.last_seen IS NULL THEN mac_inventory.last_seen
                    WHEN mac_inventory.last_seen >= excluded.last_seen THEN mac_inventory.last_seen
                    ELSE excluded.last_seen END
            """, values)

    async def record_inventory(self, records):
        await self.hass.async_add_executor_job(self._record_inventory, records)

    def _inventory_summary(self):
        with self._connect() as db:
            total=db.execute("SELECT COUNT(*) FROM mac_inventory WHERE switch_id=?", (self.key,)).fetchone()[0]
            local_known=db.execute("""SELECT COUNT(*) FROM mac_inventory WHERE switch_id=? AND classification=?""",
                (self.key,"locally_administered")).fetchone()[0]
            matched=db.execute("""SELECT COUNT(*) FROM mac_inventory
                WHERE switch_id=? AND classification='globally_administered'
                AND vendor IS NOT NULL
                AND vendor NOT IN ('', 'Desconhecido', 'MAC local/privado', 'Multicast')
            """, (self.key,)).fetchone()[0]
            rows=db.execute("""SELECT mac,vlan,port,vendor,classification,first_seen,last_seen
                FROM mac_inventory WHERE switch_id=?
                ORDER BY last_seen DESC LIMIT 200""", (self.key,)).fetchall()
        return {
            "mac_known": total,
            "mac_local_known": local_known,
            "mac_vendor_matched": matched,
            "mac_history_entries": [
                dict(zip(("mac","vlan","port","vendor","classification","first_seen","last_seen"),r))
                for r in rows
            ],
        }

    async def inventory_summary(self):
        return await self.hass.async_add_executor_job(self._inventory_summary)

    def _record_snapshot(self, kind, payload):
        allowed=("sfp","vlan_ports","isolation","stp_ports","storm_control","stp_global","aggregation")
        if kind not in allowed:
            return
        clean=_snapshot_state(kind,payload)
        encoded=json.dumps(clean,ensure_ascii=False,sort_keys=True,default=str)
        digest=hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        now=datetime.now(timezone.utc)
        stamp=now.isoformat()
        day=now.astimezone(self.tz).date().isoformat()
        cutoff=(now-timedelta(days=90)).isoformat()
        day_cutoff=(now.astimezone(self.tz)-timedelta(days=90)).date().isoformat()
        temperature=payload.get("temperature_c") if kind=="sfp" else None
        valid_temperature=(type(temperature) in (int,float) and math.isfinite(temperature)
                           and -40 <= temperature <= 125)
        bucket=now.replace(minute=now.minute//5*5,second=0,microsecond=0).isoformat()
        optical_limits={
            "voltage_v":(0.0,6.0),
            "current_ma":(0.0,200.0),
            "rx_dbm":(-80.0,30.0),
            "tx_dbm":(-80.0,30.0),
        }
        optical_values={
            metric:float(payload[metric]) for metric,(low,high) in optical_limits.items()
            if kind=="sfp" and type(payload.get(metric)) in (int,float)
            and math.isfinite(payload[metric]) and low<=payload[metric]<=high
        }
        with self._connect() as db:
            for metric,value in optical_values.items():
                db.execute("""INSERT INTO sfp_optical_5m
                    (switch_id,metric,bucket,sample_count,value_sum,value_min,value_max)
                    VALUES (?,?,?,1,?,?,?)
                    ON CONFLICT(switch_id,metric,bucket) DO UPDATE SET
                        sample_count=sample_count+1,
                        value_sum=value_sum+excluded.value_sum,
                        value_min=MIN(value_min,excluded.value_min),
                        value_max=MAX(value_max,excluded.value_max)""",
                    (self.key,metric,bucket,value,value,value))
            if kind=="sfp":
                db.execute("DELETE FROM sfp_optical_5m WHERE bucket < ?",
                           ((now-timedelta(days=7)).isoformat(),))
            if valid_temperature:
                db.execute("""INSERT INTO sfp_temperature_5m
                    (switch_id,bucket,sample_count,temp_sum,temp_min,temp_max)
                    VALUES(?,?,1,?,?,?)
                    ON CONFLICT(switch_id,bucket) DO UPDATE SET
                        sample_count=sample_count+1,
                        temp_sum=temp_sum+excluded.temp_sum,
                        temp_min=MIN(temp_min,excluded.temp_min),
                        temp_max=MAX(temp_max,excluded.temp_max)""",
                    (self.key,bucket,temperature,temperature,temperature))
            if kind=="sfp":
                db.execute("DELETE FROM sfp_temperature_5m WHERE bucket < ?",
                           ((now-timedelta(days=30)).isoformat(),))
            previous=db.execute("""SELECT checksum,payload FROM snapshots
                WHERE switch_id=? AND kind=? ORDER BY timestamp DESC LIMIT 1""",
                (self.key,kind)).fetchone()
            if previous and kind=="sfp":
                try:
                    last=json.loads(previous[1])
                    last=_snapshot_state(kind,last)
                    changed=last!=clean
                except (ValueError,TypeError):
                    changed=previous[0]!=digest
            else:
                changed=previous is None or previous[0]!=digest
            if changed:
                db.execute("""INSERT INTO snapshots
                    (switch_id,kind,timestamp,checksum,payload) VALUES (?,?,?,?,?)""",
                    (self.key,kind,stamp,digest,encoded))
            db.execute("""INSERT INTO snapshot_daily
                (switch_id,kind,day,checked_at,checksum,checks,changes)
                VALUES (?,?,?,?,?,1,?)
                ON CONFLICT(switch_id,kind,day) DO UPDATE SET
                    checked_at=excluded.checked_at,checksum=excluded.checksum,
                    checks=checks+1,changes=changes+excluded.changes""",
                (self.key,kind,day,stamp,digest,int(changed)))
            db.execute("DELETE FROM snapshots WHERE timestamp < ?",(cutoff,))
            db.execute("DELETE FROM snapshot_daily WHERE day < ?",(day_cutoff,))

    def _temperature_history(self, hours):
        hours=max(1,min(720,int(hours)))
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        with self._connect() as db:
            rows=db.execute("""SELECT bucket,sample_count,temp_sum,temp_min,temp_max
                FROM sfp_temperature_5m WHERE switch_id=? AND bucket>=?
                ORDER BY bucket""",(self.key,cutoff)).fetchall()
        if not rows:
            return {"items":[],"min":None,"max":None,"average":None,"count":0}
        count=sum(row[1] for row in rows)
        step=max(1,math.ceil(len(rows)/400))
        items=[]
        for i in range(0,len(rows),step):
            group=rows[i:i+step]
            n=sum(r[1] for r in group)
            items.append({"timestamp":group[-1][0],
                          "avg":round(sum(r[2] for r in group)/n,3),
                          "min":min(r[3] for r in group),
                          "max":max(r[4] for r in group)})
        return {"items":items,"min":min(r[3] for r in rows),
                "max":max(r[4] for r in rows),
                "average":round(sum(r[2] for r in rows)/count,3),"count":count}

    def _optical_history(self,metric,hours):
        allowed=("voltage_v","current_ma","rx_dbm","tx_dbm")
        if metric not in allowed:
            raise ValueError("Unsupported optical metric")
        hours=max(1,min(168,int(hours)))
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        with self._connect() as db:
            rows=db.execute("""SELECT bucket,sample_count,value_sum,value_min,value_max
                FROM sfp_optical_5m WHERE switch_id=? AND metric=? AND bucket>=?
                ORDER BY bucket""",(self.key,metric,cutoff)).fetchall()
        if not rows:
            return {"items":[],"min":None,"max":None,"average":None,"count":0}
        total_count=sum(r[1] for r in rows)
        step=max(1,math.ceil(len(rows)/400))
        items=[]
        for idx in range(0,len(rows),step):
            group=rows[idx:idx+step]
            count=sum(r[1] for r in group)
            items.append({"timestamp":group[-1][0],
                "avg":round(sum(r[2] for r in group)/count,4),
                "min":min(r[3] for r in group),"max":max(r[4] for r in group)})
        return {"items":items,"min":min(r[3] for r in rows),
                "max":max(r[4] for r in rows),
                "average":round(sum(r[2] for r in rows)/total_count,4),
                "count":total_count}

    async def optical_history(self,metric,hours=24):
        return await self.hass.async_add_executor_job(self._optical_history,metric,int(hours))

    async def temperature_history(self,hours=24):
        return await self.hass.async_add_executor_job(self._temperature_history,int(hours))

    async def record_snapshot(self, kind, payload):
        await self.hass.async_add_executor_job(self._record_snapshot,kind,payload)

    def _reclassify_inventory(self, lookup):
        with self._connect() as db:
            rows=db.execute("SELECT vlan,mac,vendor FROM mac_inventory WHERE switch_id=?", (self.key,)).fetchall()
            updates=[]
            for vlan,mac,previous in rows:
                resolved=lookup(mac)
                if resolved not in ("", "Desconhecido", None) and resolved!=previous:
                    updates.append((resolved,self.key,vlan,mac))
            if updates:
                db.executemany("UPDATE mac_inventory SET vendor=? WHERE switch_id=? AND vlan=? AND mac=?", updates)
            return len(updates)

    async def reclassify_inventory(self, vendors):
        return await self.hass.async_add_executor_job(self._reclassify_inventory, vendors.lookup)

    def _recent_changes(self):
        with self._connect() as db:
            rows=db.execute("""SELECT kind,timestamp FROM snapshots
                WHERE switch_id=? ORDER BY timestamp DESC LIMIT 40""", (self.key,)).fetchall()
        return [{"kind":kind,"timestamp":timestamp} for kind,timestamp in rows]

    async def recent_changes(self):
        return await self.hass.async_add_executor_job(self._recent_changes)

    def _series(self, port, hours):
        if port != "__total__" and (not port.isdecimal() or len(port)>4):
            return []
        hours = max(1,min(720,int(hours)))
        cutoff = (datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        with self._connect() as db:
            rows = db.execute("""SELECT bucket,rx_sum,tx_sum,count,peak_rx,peak_tx,rx_bytes,tx_bytes
                FROM traffic_5m WHERE switch_id=? AND port=? AND bucket>=?
                ORDER BY bucket""",(self.key,port,cutoff)).fetchall()
            if hours <= 24:
                # Raw samples are retained for two days, giving finer 1/6/12h detail.
                raw = db.execute("""SELECT timestamp,rx_bps,tx_bps FROM traffic
                    WHERE switch_id=? AND port=? AND timestamp>=? ORDER BY timestamp""",
                    (self.key,port,cutoff)).fetchall()
            else:
                raw = []
        if raw:
            step = max(1, (len(raw)+599)//600)
            return [{"timestamp":raw[i][0], "rx":sum(v[1] for v in raw[i:i+step])/len(raw[i:i+step]),
                     "tx":sum(v[2] for v in raw[i:i+step])/len(raw[i:i+step])}
                    for i in range(0,len(raw),step)]
        step=max(1,(len(rows)+599)//600)
        result=[]
        for index in range(0,len(rows),step):
            group=rows[index:index+step]
            count=sum(r[3] for r in group)
            if count:
                result.append({"timestamp":group[-1][0],
                    "rx_bytes":sum(r[6] for r in group),
                    "tx_bytes":sum(r[7] for r in group),
                    "rx":sum(r[1] for r in group)/count,
                    "tx":sum(r[2] for r in group)/count,
                    "peak_rx":max(r[4] for r in group),
                    "peak_tx":max(r[5] for r in group)})
        return result

    def _period_totals(self,port,hours):
        if port != "__total__" and not (port.isdecimal() and len(port)<=4):
            return {"rx_bytes":0,"tx_bytes":0}
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=max(1,min(720,int(hours))))).isoformat()
        with self._connect() as db:
            values=db.execute("""SELECT COALESCE(SUM(rx_bytes),0),COALESCE(SUM(tx_bytes),0)
                FROM traffic_5m WHERE switch_id=? AND port=? AND bucket>=?""",
                (self.key,port,cutoff)).fetchone()
        return {"rx_bytes":values[0],"tx_bytes":values[1]}

    async def period_totals(self,port,hours):
        return await self.hass.async_add_executor_job(self._period_totals,str(port),int(hours))

    async def series(self, port, hours):
        return await self.hass.async_add_executor_job(self._series, str(port), int(hours))

    def _daily_totals(self, port, days):
        if port!="__total__" and (not port.isdecimal() or len(port)>4):
            return []
        cutoff=(datetime.now(self.tz)-timedelta(days=max(1,min(30,int(days))))).date().isoformat()
        with self._connect() as db:
            rows=db.execute("""SELECT day,rx_bytes,tx_bytes FROM daily_traffic
                WHERE switch_id=? AND port=? AND day>=? ORDER BY day DESC""",
                (self.key,port,cutoff)).fetchall()
        return [{"day":day,"rx_bytes":rx,"tx_bytes":tx} for day,rx,tx in rows]

    async def daily_totals(self, port="__total__", days=365):
        return await self.hass.async_add_executor_job(self._daily_totals,str(port),int(days))

    def _storage_summary(self):
        """Actual SQLite size, free pages and per-table row counts (all switches)."""
        tables=("traffic","traffic_5m","traffic_baselines","daily_traffic",
                "sfp_temperature_5m","sfp_optical_5m","mac_inventory",
                "snapshots","snapshot_daily")
        with self._connect() as db:
            page_size=db.execute("PRAGMA page_size").fetchone()[0]
            pages=db.execute("PRAGMA page_count").fetchone()[0]
            free=db.execute("PRAGMA freelist_count").fetchone()[0]
            counts={name:db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in tables}
            table_sizes={}
            try:
                for name,used in db.execute("SELECT name,SUM(pgsize) FROM dbstat GROUP BY name"):
                    if name in tables:
                        table_sizes[name]=used
            except sqlite3.OperationalError:
                pass
        return {"file_bytes":pages*page_size,"free_bytes":free*page_size,
                "used_bytes":(pages-free)*page_size,"rows":counts,
                "table_bytes":table_sizes,
                "scope":"whole_database","measured_at":datetime.now(timezone.utc).isoformat()}

    async def storage_summary(self):
        return await self.hass.async_add_executor_job(self._storage_summary)

    def _snapshot_history(self,kind):
        allowed=("sfp","vlan_ports","isolation","stp_ports","storm_control","stp_global","aggregation")
        if kind not in allowed:
            return []
        cutoff=(datetime.now(self.tz)-timedelta(days=90)).date().isoformat()
        with self._connect() as db:
            days=db.execute("""SELECT day,checked_at,checks,changes FROM snapshot_daily
                WHERE switch_id=? AND kind=? AND day>=?
                ORDER BY day DESC LIMIT 90""",(self.key,kind,cutoff)).fetchall()
            events=db.execute("""SELECT timestamp,payload FROM snapshots
                WHERE switch_id=? AND kind=? ORDER BY timestamp DESC LIMIT 180""",
                (self.key,kind)).fetchall()
        by_day={}
        for timestamp,payload in events:
            try:
                day=datetime.fromisoformat(timestamp).astimezone(self.tz).date().isoformat()
                by_day.setdefault(day,[]).append({"timestamp":timestamp,"data":json.loads(payload)})
            except (ValueError,TypeError):
                continue
        return [{"day":day,"checked_at":last,"checks":checks,
                 "changes":max(changes or 0,len(by_day.get(day,[]))),
                 "events":by_day.get(day,[])} for day,last,checks,changes in days]

    async def snapshot_history(self,kind):
        return await self.hass.async_add_executor_job(self._snapshot_history,kind)
