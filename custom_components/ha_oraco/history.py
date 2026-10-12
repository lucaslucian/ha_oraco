"""Persistent bounded time-series database for HoraInfo (per Home Assistant instance).

All SQLite operations run in Home Assistant's executor, off the event loop.
No switch credentials are stored here. Do not store user-provided SQL fragments.
"""
from __future__ import annotations

import sqlite3
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
        return {
            "peaks": {
                "total": {"rx_bps": next((r[1] for r in peaks if r[0]=="__total__"), 0),
                          "tx_bps": next((r[2] for r in peaks if r[0]=="__total__"), 0)},
                "ports": {r[0]: {"rx_bps": r[1], "tx_bps": r[2]}
                          for r in peaks if r[0]!="__total__"},
                "scope": "retained_14_days",
            },
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
