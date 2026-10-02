"""SQLite ajalugu: käivitused, kuulutused ja nende hinnad igas käivituses."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from .parser import Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    complete INTEGER NOT NULL DEFAULT 0,
    counties_ok TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER NOT NULL,
    deal_type INTEGER NOT NULL,
    url TEXT, address TEXT, location TEXT, county TEXT,
    rooms INTEGER, area_m2 REAL, floor INTEGER, build_year INTEGER, condition TEXT,
    first_seen_run INTEGER NOT NULL,
    last_seen_run INTEGER NOT NULL,
    PRIMARY KEY (id, deal_type)
);
CREATE TABLE IF NOT EXISTS observations (
    run_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL,
    deal_type INTEGER NOT NULL,
    price REAL, area_m2 REAL, rooms INTEGER, price_per_m2 REAL,
    PRIMARY KEY (run_id, listing_id, deal_type)
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def start_run(self, now: str | None = None) -> int:
        cur = self.conn.execute("INSERT INTO runs (started_at) VALUES (?)", (now or _now(),))
        self.conn.commit()
        return cur.lastrowid

    def save_listings(self, run_id: int, deal_type: int, county: str, listings: list[Listing]) -> None:
        for l in listings:
            self.conn.execute(
                """INSERT INTO listings (id, deal_type, url, address, location, county, rooms, area_m2,
                       floor, build_year, condition, first_seen_run, last_seen_run)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (id, deal_type) DO UPDATE SET
                       url=excluded.url, address=excluded.address, location=excluded.location,
                       county=excluded.county, rooms=excluded.rooms, area_m2=excluded.area_m2,
                       floor=excluded.floor, build_year=excluded.build_year,
                       condition=excluded.condition, last_seen_run=excluded.last_seen_run""",
                (l.id, deal_type, l.url, l.address, l.location, county, l.rooms, l.area_m2,
                 l.floor, l.build_year, l.condition, run_id, run_id),
            )
            per_m2 = l.price / l.area_m2 if l.price and l.area_m2 else None
            self.conn.execute(
                """INSERT OR REPLACE INTO observations
                   (run_id, listing_id, deal_type, price, area_m2, rooms, price_per_m2)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, l.id, deal_type, l.price, l.area_m2, l.rooms, per_m2),
            )
        self.conn.commit()

    def finish_run(self, run_id: int, counties_ok: list[str], complete: bool) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, complete=?, counties_ok=? WHERE id=?",
            (_now(), int(complete), ",".join(counties_ok), run_id),
        )
        self.conn.commit()

    def runs(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM runs WHERE counties_ok != '' ORDER BY id"
        ).fetchall()
        return [
            {"id": r["id"], "started_at": r["started_at"], "finished_at": r["finished_at"],
             "complete": bool(r["complete"]), "counties_ok": r["counties_ok"].split(",")}
            for r in rows
        ]

    def observations(self, run_id: int) -> list[dict]:
        rows = self.conn.execute(
            """SELECT l.id, o.deal_type, l.county, l.location, l.address, l.url,
                      o.rooms, o.area_m2, o.price, o.price_per_m2
               FROM observations o JOIN listings l ON l.id = o.listing_id AND l.deal_type = o.deal_type
               WHERE o.run_id = ?""",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()

    def listing_attrs(self) -> dict[tuple[int, int], dict]:
        rows = self.conn.execute("SELECT id, deal_type, floor, build_year, condition FROM listings").fetchall()
        return {(r["id"], r["deal_type"]): {"floor": r["floor"], "build_year": r["build_year"],
                                            "condition": r["condition"]} for r in rows}
