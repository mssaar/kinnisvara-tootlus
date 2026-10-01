"""Aadressi koordinaadid Maa- ja Ruumiameti In-ADS aadressiotsingust, SQLite vahemäluga."""
from __future__ import annotations

import json
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

INADS_URL = "https://inaadress.maaamet.ee/inaadress/gazetteer?address={address}&results=1"
REQUEST_DELAY_S = 0.2

SCHEMA = """
CREATE TABLE IF NOT EXISTS geocodes (
    query TEXT PRIMARY KEY,
    lat REAL, lon REAL, asum TEXT,
    found INTEGER NOT NULL,
    fetched_at TEXT NOT NULL
);
"""

_APARTMENT = re.compile(r"^(.*\d+[A-Za-zÕÄÖÜõäöü]?)-\d+[A-Za-z]?$")


@dataclass(frozen=True)
class Geo:
    lat: float
    lon: float
    asum: str | None


def street_query(address: str, location: str) -> str | None:
    street = address[: len(address) - len(location)] if location and address.endswith(location) else ""
    street = street.strip().rstrip(",").strip()
    if not street:
        return None
    match = _APARTMENT.match(street)
    if match:
        street = match.group(1)
    return f"{street}, Tallinn"


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "kinnisvara-tootlus/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


class Geocoder:
    def __init__(self, conn: sqlite3.Connection, fetch=fetch_json, sleep=time.sleep):
        self.conn = conn
        self.fetch = fetch
        self.sleep = sleep
        self.conn.executescript(SCHEMA)

    def _cached(self, query: str):
        return self.conn.execute("SELECT lat, lon, asum, found FROM geocodes WHERE query = ?", (query,)).fetchone()

    def lookup(self, query: str) -> Geo | None:
        row = self._cached(query)
        if row is None or not row[3]:
            return None
        return Geo(row[0], row[1], row[2])

    def geocode_missing(self, queries: Iterable[str], progress=print) -> int:
        todo = sorted({q for q in queries if q and self._cached(q) is None})
        for i, query in enumerate(todo, 1):
            url = INADS_URL.format(address=urllib.parse.quote(query))
            try:
                data = self.fetch(url)
            except (urllib.error.URLError, OSError, ValueError) as exc:
                progress(f"Geokodeerimine: {query}: viga ({exc}), proovin järgmisel korral uuesti")
            else:
                addresses = (data.get("addresses") if isinstance(data, dict) else None) or []
                self._store(query, addresses)
            if i % 100 == 0:
                progress(f"Geokodeerimine: {i}/{len(todo)}")
            self.sleep(REQUEST_DELAY_S)
        return len(todo)

    def _store(self, query: str, addresses: list) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        first = addresses[0] if addresses else None
        try:
            lat, lon = float(first["viitepunkt_b"]), float(first["viitepunkt_l"])
        except (TypeError, KeyError, ValueError):
            self.conn.execute("INSERT OR REPLACE INTO geocodes VALUES (?, NULL, NULL, NULL, 0, ?)", (query, now))
        else:
            raw_asum = (first.get("asum") or "").split(",")[0].removesuffix(" asum").strip()
            asum = raw_asum or None
            self.conn.execute("INSERT OR REPLACE INTO geocodes VALUES (?, ?, ?, ?, 1, ?)", (query, lat, lon, asum, now))
        self.conn.commit()
