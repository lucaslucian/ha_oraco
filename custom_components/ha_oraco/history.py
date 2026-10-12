"""Persistent bounded time-series database for HoraInfo (per Home Assistant instance).

All SQLite operations run in Home Assistant's executor, off the event loop.
No switch credentials are stored here. Do not store user-provided SQL fragments.
"""
from __future__ import annotations

import sqlite3
import json
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


class HistoryDatabase:
    def __init__(self, hass, key):
        self.hass = hass
        self.path = Path(hass.config.path(".storage", "ha_oraco_history.db"))
        self.key = key
        self.tz = ZoneInfo(getattr(hass.config, 'time_zone', None) or 'UTC')
        self.previous_counters = {}

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
            db.execute("""CREATE TABLE IF NOT EXISTS daily_traffic (
                switch_id TEXT, day TEXT, port TEXT, rx_bytes INTEGER, tx_bytes INTEGER,
                PRIMARY KEY(switch_id,day,port)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_5m_expiry ON traffic_5m(bucket)")
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
            db.execute("""CREATE INDEX IF NOT EXISTS idx_mac_seen
                ON mac_inventory(switch_id,last_seen)""")

    async def initialize(self):
        await self.hass.async_add_executor_job(self._initialize)

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
        for number, port in ports.items():
            number = str(number)
            rx, tx = port.get("rx_bps"), port.get("tx_bps")
            if not isinstance(rx,(int,float)) or not isinstance(tx,(int,float)):
                continue
            if not (0 <= rx < 1e13 and 0 <= tx < 1e13):
                continue
            rx_total += rx
            tx_total += tx
            raw_rows.append((self.key,timestamp,number,rx,tx))
            buckets.append((self.key,bucket,number,rx,tx,1,rx,tx))
            counters = (port.get("rx_bytes"), port.get("tx_bytes"))
            previous = self.previous_counters.get(number)
            if all(isinstance(x,int) for x in counters):
                if previous and all(new >= old for new,old in zip(counters,previous)):
                    drx = counters[0]-previous[0]
                    dtx = counters[1]-previous[1]
                    daily.append((self.key,day,number,drx,dtx))
                    bytes_rx += drx
                    bytes_tx += dtx
                self.previous_counters[number] = counters
        if not raw_rows:
            return
        raw_rows.append((self.key,timestamp,"__total__",rx_total,tx_total))
        buckets.append((self.key,bucket,"__total__",rx_total,tx_total,1,rx_total,tx_total))
        if daily:
            daily.append((self.key,day,"__total__",bytes_rx,bytes_tx))
        with self._connect() as db:
            db.executemany("INSERT OR REPLACE INTO traffic VALUES(?,?,?,?,?)",raw_rows)
            db.executemany("""INSERT INTO traffic_5m VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(switch_id,bucket,port) DO UPDATE SET
                rx_sum=rx_sum+excluded.rx_sum,tx_sum=tx_sum+excluded.tx_sum,
                count=count+1,peak_rx=MAX(peak_rx,excluded.peak_rx),
                peak_tx=MAX(peak_tx,excluded.peak_tx)""",buckets)
            if daily:
                db.executemany("""INSERT INTO daily_traffic VALUES(?,?,?,?,?)
                    ON CONFLICT(switch_id,day,port) DO UPDATE SET
                    rx_bytes=rx_bytes+excluded.rx_bytes,
                    tx_bytes=tx_bytes+excluded.tx_bytes""",daily)
            db.execute("DELETE FROM traffic WHERE timestamp < ?",((stamp-timedelta(days=2)).isoformat(),))
            db.execute("DELETE FROM traffic_5m WHERE bucket < ?",((stamp-timedelta(days=30)).isoformat(),))

    async def record_traffic(self, ports):
        await self.hass.async_add_executor_job(self._record_traffic, ports)

    def _traffic_summary(self):
        with self._connect() as db:
            peaks = db.execute("""SELECT port,MAX(rx_bps),MAX(tx_bps)
                FROM traffic WHERE switch_id=? GROUP BY port""", (self.key,)).fetchall()
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
                "scope": "retained_14_days",
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
                first_seen=CASE WHEN mac_inventory.first_seen < excluded.first_seen
                  THEN mac_inventory.first_seen ELSE excluded.first_seen END,
                last_seen=CASE WHEN mac_inventory.last_seen > excluded.last_seen
                  THEN mac_inventory.last_seen ELSE excluded.last_seen END
            """, values)

    async def record_inventory(self, records):
        await self.hass.async_add_executor_job(self._record_inventory, records)

    def _inventory_summary(self):
        with self._connect() as db:
            total=db.execute("SELECT COUNT(*) FROM mac_inventory WHERE switch_id=?", (self.key,)).fetchone()[0]
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
            "mac_vendor_matched": matched,
            "mac_history_entries": [
                dict(zip(("mac","vlan","port","vendor","classification","first_seen","last_seen"),r))
                for r in rows
            ],
        }

    async def inventory_summary(self):
        return await self.hass.async_add_executor_job(self._inventory_summary)

    def _record_snapshot(self, kind, payload):
        allowed = ("sfp", "vlan_ports", "isolation", "stp_ports", "storm_control",
                   "stp_global", "aggregation")
        if kind not in allowed:
            return
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        stamp = datetime.now(timezone.utc).isoformat()
        cutoff = (datetime.now(timezone.utc)-timedelta(days=90)).isoformat()
        with self._connect() as db:
            latest = db.execute("SELECT checksum,timestamp FROM snapshots WHERE switch_id=? AND kind=? ORDER BY timestamp DESC LIMIT 1", (self.key,kind)).fetchone()
            if kind == "sfp" and latest:
                last_time = datetime.fromisoformat(latest[1])
                if datetime.now(timezone.utc) - last_time < timedelta(minutes=5):
                    return
            if latest is None or latest[0] != digest:
                db.execute("INSERT INTO snapshots (switch_id,kind,timestamp,checksum,payload) VALUES (?,?,?,?,?)", (self.key,kind,stamp,digest,encoded))
            db.execute("DELETE FROM snapshots WHERE timestamp < ?", (cutoff,))

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
            rows = db.execute("""SELECT bucket,rx_sum,tx_sum,count,peak_rx,peak_tx
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
                    "rx":sum(r[1] for r in group)/count,
                    "tx":sum(r[2] for r in group)/count,
                    "peak_rx":max(r[4] for r in group),
                    "peak_tx":max(r[5] for r in group)})
        return result

    async def series(self, port, hours):
        return await self.hass.async_add_executor_job(self._series, str(port), int(hours))

    def _daily_totals(self, port, days):
        if port!="__total__" and (not port.isdecimal() or len(port)>4):
            return []
        cutoff=(datetime.now(self.tz)-timedelta(days=max(1,min(730,int(days))))).date().isoformat()
        with self._connect() as db:
            rows=db.execute("""SELECT day,rx_bytes,tx_bytes FROM daily_traffic
                WHERE switch_id=? AND port=? AND day>=? ORDER BY day DESC""",
                (self.key,port,cutoff)).fetchall()
        return [{"day":day,"rx_bytes":rx,"tx_bytes":tx} for day,rx,tx in rows]

    async def daily_totals(self, port="__total__", days=365):
        return await self.hass.async_add_executor_job(self._daily_totals,str(port),int(days))

    def _snapshot_history(self,kind):
        valid=("sfp","vlan_ports","isolation","stp_ports","storm_control","stp_global","aggregation")
        if kind not in valid:
            return []
        cutoff=(datetime.now(timezone.utc)-timedelta(days=90)).isoformat()
        with self._connect() as db:
            rows=db.execute("""SELECT timestamp,payload FROM snapshots
                WHERE switch_id=? AND kind=? AND timestamp>=?
                ORDER BY timestamp DESC LIMIT 120""",(self.key,kind,cutoff)).fetchall()
        return [{"timestamp":timestamp,"data":json.loads(payload)} for timestamp,payload in rows]

    async def snapshot_history(self,kind):
        return await self.hass.async_add_executor_job(self._snapshot_history,kind)
