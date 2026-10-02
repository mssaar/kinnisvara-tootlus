"""kv.ee aadressi asukohaosa tõlgendamine piirkondade hierarhiaks."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Iterable

from . import config


@dataclass(frozen=True)
class Location:
    city: str | None
    district: str | None
    subdistrict: str | None


_JUNK = re.compile(r"[\d€]")


def _plausible(name: str) -> bool:
    return bool(name) and name[0].isupper() and not _JUNK.search(name) and len(name) <= 40


def _dedupe(parts: list[str]) -> list[str]:
    out: list[str] = []
    for p in parts:
        if p not in out:
            out.append(p)
    return out


def parse(location: str) -> Location:
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if not parts:
        return Location(None, None, None)
    city = parts[-1]
    rest = _dedupe([p for p in parts[:-1] if p not in (city, f"{city} linn") and _plausible(p)])
    if city == "Tallinn":
        districts = [p for p in rest if p in config.TALLINN_DISTRICTS]
        others = [p for p in rest if p not in config.TALLINN_DISTRICTS]
        return Location(city, districts[-1] if districts else None, others[-1] if others else None)
    district = rest[-1] if rest else None
    subdistrict = rest[-2] if len(rest) >= 2 else None
    return Location(city, district, subdistrict)


def is_center(county: str, loc: Location) -> bool:
    center = config.COUNTY_CENTERS.get(county)
    if center is None:
        return False
    names = {center, f"{center} linn"}
    return loc.city in names or loc.district in names


def build_district_map(locs: Iterable[Location]) -> dict[tuple[str, str], str]:
    counts: dict[tuple[str, str], Counter] = {}
    for loc in locs:
        if loc.city and loc.district and loc.subdistrict:
            counts.setdefault((loc.city, loc.subdistrict), Counter())[loc.district] += 1
    return {key: c.most_common(1)[0][0] for key, c in counts.items()}


def fill_district(loc: Location, district_map: dict[tuple[str, str], str]) -> Location:
    if loc.district is None and loc.city and loc.subdistrict:
        district = district_map.get((loc.city, loc.subdistrict))
        if district:
            return replace(loc, district=district)
    return loc
