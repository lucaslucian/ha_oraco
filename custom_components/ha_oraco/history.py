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


class HistoryDatabase:
    def __init__(self, hass, key):
        self.hass = hass
        self.path = Path(hass.config.path(".storage", "ha_oraco_history.db"))
        self.key = key

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
            db.execute("""CREATE INDEX IF NOT EXISTS idx_mac_seen
                ON mac_inventory(switch_id,last_seen)""")

    async def initialize(self):
        await self.hass.async_add_executor_job(self._initialize)

    def _record_traffic(self, ports):
        stamp = datetime.now(timezone.utc).isoformat()
        values = []
        total_rx = total_tx = 0.0
        for number, p in ports.items():
            rx, tx = p.get("rx_bps"), p.get("tx_bps")
            if not isinstance(rx, (int, float)) or not isinstance(tx, (int, float)):
                continue
            if not (0 <= rx < 1e13 and 0 <= tx < 1e13):
                continue
            values.append((self.key, stamp, str(number), rx, tx))
            total_rx += rx
            total_tx += tx
        if not values:
            return
        values.append((self.key, stamp, "__total__", total_rx, total_tx))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
        with self._connect() as db:
            db.executemany("""INSERT OR REPLACE INTO traffic
                (switch_id,timestamp,port,rx_bps,tx_bps) VALUES (?,?,?,?,?)""", values)
            db.execute("DELETE FROM traffic WHERE timestamp < ?", (cutoff,))

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
            rows=db.execute("""SELECT mac,vlan,port,vendor,classification,first_seen,last_seen
                FROM mac_inventory WHERE switch_id=?
                ORDER BY last_seen DESC LIMIT 200""", (self.key,)).fetchall()
        return {
            "mac_known": total,
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
            latest = db.execute("SELECT checksum FROM snapshots WHERE switch_id=? AND kind=? ORDER BY timestamp DESC LIMIT 1", (self.key,kind)).fetchone()
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
