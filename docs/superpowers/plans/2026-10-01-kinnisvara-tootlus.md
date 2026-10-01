# Kinnisvara üüritootlus — rakendusplaan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Python-programm, mis kogub kv.ee korterite müügi- ja üürikuulutused, hoiab ajalugu SQLite'is, arvutab piirkondade bruto üüritootluse (ajapunktide mediaan) ja näitab seda staatilisel GitHub Pages lehel.

**Architecture:** Puhas HTML-parser (`parser.py`) + HTTP/lehekülgede kiht (`scraper.py`) → `store.py` (runs/listings/observations) → `analyze.py` (piirkonnad `regions.py` abil, mediaanid käivituse kaupa, siis üle käivituste) → `docs/data/results.json` → staatiline UI `docs/`. `pipeline.py` seob kogumise ja analüüsi; `run.py` on CLI; `server.py` serveerib UI-d kohalikult koos "Käivita uuesti" API-ga.

**Tech Stack:** Python 3.14, requests, beautifulsoup4 (+lxml), sqlite3, http.server, pytest; vanilla HTML/CSS/JS.

**Spec:** `docs/superpowers/specs/2026-10-01-kinnisvara-tootlus-design.md`

## Global Constraints

- Ainult korterid; toarühmad `"1"`, `"2"`, `"3"`, `"4+"` ja `"all"`.
- Tasemed: `county`, `county_ex_center`, `city`, `district`, `subdistrict`.
- Kehtiv ajapunkt nõuab müügi- ja üürikuulutusi kumbagi ≥ `MIN_SAMPLES = 5`.
- Tootlus = `üür_m2_mediaan × 12 / müük_m2_mediaan`, arvutatakse ainult sama käivituse andmetest; lõpptulemus on kehtivate ajapunktide tootluste mediaan.
- Puhastus: pind 10–300 m², müük 200–15 000 €/m², üür 2–60 €/m².
- Päringute vahel 1,5 s paus, max 3 korduskatset, brauserilaadne User-Agent.
- Maakond salvestatakse käivitusse ainult siis, kui nii müük kui ka üür kogutud edukalt.
- Top 500 parimat müügikuulutust (viimane käivitus).
- Kõik kasutajale nähtav tekst on eesti keeles.
- Testid ei tee võrgupäringuid.

## Review Focus

1. **Aadress ainult linnaga või prügiga** ("Narva", "0 € lepingutasu, Pirita, Tallinn") — ei tohi krahhida; prügi ei tohi saada linnaosaks. → Task 2 testid.
2. **Lehekülgede vahetus üle lõpu** tagastab viimase lehe uuesti — kogumine peab peatuma, mitte lõputult käima. → Task 3 test.
3. **Hind "Kuumakse …" lisatekstiga või puuduv hind/pind** — ei tohi minna hinnaks; kuulutus jääb analüüsist välja. → Task 1 ja 5 testid.
4. **Osaliselt ebaõnnestunud käivitus** (üks maakond katkes) — teiste maakondade tulemused peavad jääma kehtima ja katkenud maakond ei tohi saada vale tootlust. → Task 6 test.
5. **Kahe käivituse vahel muutunud kuulutus** (sama ID, uus hind) — mõlemad hinnad säilivad ja kumbki käivitus kasutab oma hinda. → Task 4 ja 5 testid.

---

## File Structure

```
requirements.txt
.gitignore
README.md
run.py                     CLI
tootlus/__init__.py
tootlus/config.py          konstandid: maakonnad, keskused, lävendid
tootlus/parser.py          kv.ee otsingulehe HTML -> list[Listing]
tootlus/scraper.py         HTTP + lehekülgede läbimine ühe maakonna kohta
tootlus/regions.py         location-string -> Location(city, district, subdistrict)
tootlus/store.py           SQLite
tootlus/analyze.py         tootluse arvutus -> dict / results.json
tootlus/pipeline.py        üks täiskäivitus (kogu + salvesta + analüüsi)
tootlus/server.py          kohalik server + /api/run, /api/status
docs/.nojekyll
docs/index.html, docs/style.css, docs/app.js
docs/data/results.json     genereeritud
data/kv.sqlite             genereeritud, commititakse
tests/fixtures/search_page.html
tests/test_parser.py, test_regions.py, test_scraper.py, test_store.py,
tests/test_analyze.py, test_pipeline.py, test_server.py
```

---

### Task 1: Projekti alus, config ja parser

**Files:**
- Create: `requirements.txt`, `.gitignore`, `tootlus/__init__.py`, `tootlus/config.py`, `tootlus/parser.py`
- Test: `tests/test_parser.py`, `tests/fixtures/search_page.html`, `tests/__init__.py`

**Interfaces:**
- Produces: `parser.Listing` dataclass `(id:int, url:str, address:str, location:str, rooms:int|None, area_m2:float|None, price:float|None, floor:int|None, build_year:int|None, condition:str|None)`; `parser.parse_page(html:str) -> list[Listing]`; `config.*` konstandid.

- [ ] **Step 1: Loo `requirements.txt`, `.gitignore`, `tootlus/__init__.py` (tühi), `tests/__init__.py` (tühi)**

`requirements.txt`:
```
requests>=2.31
beautifulsoup4>=4.12
lxml>=5.0
pytest>=8.0
```

`.gitignore`:
```
__pycache__/
.pytest_cache/
*.pyc
.venv/
```

Run: `pip install -r requirements.txt`

- [ ] **Step 2: Loo `tootlus/config.py`**

```python
"""Projekti konstandid."""

BASE_URL = "https://www.kv.ee/search"
SITE_URL = "https://www.kv.ee"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

DEAL_SALE = 1
DEAL_RENT = 2

PAGE_SIZE = 50
REQUEST_DELAY_S = 1.5
MAX_RETRIES = 3
MAX_PAGES = 300

# kv.ee maakonna ID -> nimi
COUNTIES = {
    1: "Harjumaa", 2: "Hiiumaa", 3: "Ida-Virumaa", 4: "Jõgevamaa", 5: "Järvamaa",
    6: "Läänemaa", 7: "Lääne-Virumaa", 8: "Põlvamaa", 9: "Pärnumaa", 10: "Raplamaa",
    11: "Saaremaa", 12: "Tartumaa", 13: "Valgamaa", 14: "Viljandimaa", 15: "Võrumaa",
}

# Ametlikud maakonnakeskused ("ilma keskuseta" vaate jaoks)
COUNTY_CENTERS = {
    "Harjumaa": "Tallinn", "Hiiumaa": "Kärdla", "Ida-Virumaa": "Jõhvi",
    "Jõgevamaa": "Jõgeva", "Järvamaa": "Paide", "Läänemaa": "Haapsalu",
    "Lääne-Virumaa": "Rakvere", "Põlvamaa": "Põlva", "Pärnumaa": "Pärnu",
    "Raplamaa": "Rapla", "Saaremaa": "Kuressaare", "Tartumaa": "Tartu",
    "Valgamaa": "Valga", "Viljandimaa": "Viljandi", "Võrumaa": "Võru",
}

TALLINN_DISTRICTS = frozenset({
    "Haabersti", "Kesklinn", "Kristiine", "Lasnamäe",
    "Mustamäe", "Nõmme", "Pirita", "Põhja-Tallinn",
})

MIN_SAMPLES = 5
AREA_RANGE = (10.0, 300.0)
SALE_M2_RANGE = (200.0, 15000.0)
RENT_M2_RANGE = (2.0, 60.0)
TOP_LISTINGS = 500
ROOM_GROUPS = ("1", "2", "3", "4+")
```

- [ ] **Step 3: Loo fixture `tests/fixtures/search_page.html`** (struktuur kopeeritud päris kv.ee kaartidelt)

```html
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Korterite müük</title></head><body>
<div class="results results-default">
<article class="default object-type-apartment " data-object-id="3760481" data-object-url="/korge-i-korrusega-avar-korter-3760481.html" >
  <div class="media"><div class="relative"><div class="images swiper"></div></div></div>
  <div class="description">
    <div class="h2">
      <a data-key="a1" class="object-promoted" title="Tasemeteenus"><i class="fas fa-star"></i> 36 </a>
      <a data-key="a2" href="/korge-i-korrusega-avar-korter-3760481.html" data-skeleton="object"> <strong>Sammu tn 10-56</strong>, Kristiine City, Kristiine, Tallinn </a>
    </div>
    <p class="object-important-note red"> Ridamaja tüüpi avar perekorter! </p>
    <p class="object-excerpt"> Korrus 1/7, Korteriomand, paneelmaja, ehitusaasta 2026, uus, lift </p>
    <p class="object-excerpt"> Kõrge I korrusega avar korter. </p>
  </div>
  <div class="rooms"> 4 </div>
  <div class="area"> 79.4&nbsp;m² </div>
  <div class="add-time"> </div>
  <div class="price"> 293 980 € <small> 3 703 €/m² </small> <div class="label campaign" data-price="293980"> </div> </div>
</article>
<article class="default object-type-apartment has-sub-images" data-object-id="3899344" data-object-url="/supluse-3899344" >
  <div class="description">
    <div class="h2"><a data-key="b1" href="/supluse-3899344" data-skeleton="object"> <strong>Supluse pst 1</strong>, 0 € lepingutasu, Pirita, Tallinn </a></div>
    <p class="object-excerpt"> Korrus 2/3, Korteriomand, ehitusaasta 2005, heas korras, elektripliit </p>
  </div>
  <div class="rooms"> 2 </div>
  <div class="area"> 107.3&nbsp;m² </div>
  <div class="price"> 1 300 € <small> 12.1 €/m² </small> </div>
</article>
<article class="default object-type-apartment " data-object-id="111" data-object-url="/hind-kokkuleppel-111" >
  <div class="description">
    <div class="h2"><a data-key="c1" href="/hind-kokkuleppel-111" data-skeleton="object"> Narva </a></div>
    <p class="object-excerpt"> Korteriomand, kivimaja </p>
  </div>
  <div class="rooms"> </div>
  <div class="area"> </div>
  <div class="price"> Hind kokkuleppel </div>
</article>
<article class="default object-type-apartment " data-object-id="3726792" data-object-url="/seebi-3726792.html" >
  <div class="description">
    <div class="h2"><a data-key="d1" href="/seebi-3726792.html" data-skeleton="object"> <strong>Seebi 24a-8</strong>, Kristiine City, Kristiine, Tallinn </a></div>
    <p class="object-excerpt"> Korrus 2/7, Korteriomand, paneelmaja, ehitusaasta 2026, uus </p>
  </div>
  <div class="rooms"> 3 </div>
  <div class="area"> 71.5&nbsp;m² </div>
  <div class="price"> 285 000 € <small> 3 986 €/m² </small> Kuumakse 1 157 € </div>
</article>
<article class="grouped-objects with-table show-preview" data-object-id="999">
  <div class="h2"><a href="/projekt-999">Arendusprojekt</a></div>
</article>
</div>
<a href="?start=50">2</a>
</body></html>
```

- [ ] **Step 4: Kirjuta failivad testid `tests/test_parser.py`**

```python
from pathlib import Path

from tootlus.parser import parse_page

FIXTURE = (Path(__file__).parent / "fixtures" / "search_page.html").read_text(encoding="utf-8")


def by_id(listings):
    return {l.id: l for l in listings}


def test_parses_only_apartment_cards():
    ids = [l.id for l in parse_page(FIXTURE)]
    assert ids == [3760481, 3899344, 111, 3726792]


def test_full_card_fields():
    l = by_id(parse_page(FIXTURE))[3760481]
    assert l.url == "https://www.kv.ee/korge-i-korrusega-avar-korter-3760481.html"
    assert l.address == "Sammu tn 10-56, Kristiine City, Kristiine, Tallinn"
    assert l.location == "Kristiine City, Kristiine, Tallinn"
    assert l.rooms == 4
    assert l.area_m2 == 79.4
    assert l.price == 293980
    assert l.floor == 1
    assert l.build_year == 2026
    assert l.condition == "uus"


def test_price_ignores_monthly_payment_text():
    l = by_id(parse_page(FIXTURE))[3726792]
    assert l.price == 285000


def test_rent_price_with_thousands_separator():
    l = by_id(parse_page(FIXTURE))[3899344]
    assert l.price == 1300
    assert l.area_m2 == 107.3
    assert l.condition == "heas korras"


def test_missing_fields_become_none():
    l = by_id(parse_page(FIXTURE))[111]
    assert l.location == "Narva"
    assert l.address == "Narva"
    assert l.rooms is None
    assert l.area_m2 is None
    assert l.price is None
    assert l.floor is None
    assert l.build_year is None
    assert l.condition is None


def test_empty_page_returns_empty_list():
    assert parse_page("<html><body></body></html>") == []
```

- [ ] **Step 5: Käivita testid, veendu et kukuvad läbi**

Run: `python -m pytest tests/test_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tootlus.parser'`

- [ ] **Step 6: Kirjuta `tootlus/parser.py`**

```python
"""kv.ee otsingutulemuste lehe parsimine."""
from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from . import config


@dataclass(frozen=True)
class Listing:
    id: int
    url: str
    address: str
    location: str
    rooms: int | None
    area_m2: float | None
    price: float | None
    floor: int | None
    build_year: int | None
    condition: str | None


CONDITIONS = (
    "uus", "valmis", "renoveeritud", "heas korras", "keskmises seisukorras",
    "san. remont tehtud", "vajab san. remonti", "vajab renoveerimist", "alustamata ehitus",
)

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_THOUSANDS = re.compile(r"(?<=\d) (?=\d{3}\b)")


def _number(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = _THOUSANDS.sub("", " ".join(text.replace("\xa0", " ").split()))
    match = _NUMBER.search(cleaned)
    return float(match.group(0).replace(",", ".")) if match else None


def _text(node) -> str:
    return " ".join(node.get_text().split()) if node else ""


def _price(article) -> float | None:
    node = article.select_one(".price")
    if node is None:
        return None
    # Ainult hinna-div'i otsene tekst: <small> (€/m²) ja "Kuumakse" jäävad välja,
    # sest "Kuumakse" tuleb pärast € märki.
    own = " ".join(s for s in node.find_all(string=True, recursive=False))
    own = " ".join(own.replace("\xa0", " ").split())
    if "€" not in own:
        return None
    return _number(own.split("€")[0])


def _excerpt_fields(article) -> tuple[int | None, int | None, str | None]:
    node = article.select_one("p.object-excerpt")
    text = _text(node)
    floor_m = re.search(r"Korrus (\d+)", text)
    year_m = re.search(r"ehitusaasta (\d{4})", text)
    parts = [p.strip() for p in text.split(",")]
    condition = next((p for p in parts if p in CONDITIONS), None)
    return (
        int(floor_m.group(1)) if floor_m else None,
        int(year_m.group(1)) if year_m else None,
        condition,
    )


def _address(article) -> tuple[str, str]:
    link = article.select_one('.h2 a[data-skeleton="object"]')
    if link is None:
        return "", ""
    address = _text(link)
    strong = link.find("strong")
    if strong is None:
        return address, address
    street = _text(strong)
    location = address[len(street):].lstrip(" ,") if address.startswith(street) else address
    return address, location


def parse_page(html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "lxml")
    listings = []
    for article in soup.select("article.default.object-type-apartment[data-object-id]"):
        address, location = _address(article)
        floor, build_year, condition = _excerpt_fields(article)
        rooms = _number(_text(article.select_one(".rooms")))
        listings.append(Listing(
            id=int(article["data-object-id"]),
            url=config.SITE_URL + article.get("data-object-url", ""),
            address=address,
            location=location,
            rooms=int(rooms) if rooms is not None else None,
            area_m2=_number(_text(article.select_one(".area"))),
            price=_price(article),
            floor=floor,
            build_year=build_year,
            condition=condition,
        ))
    return listings
```

- [ ] **Step 7: Käivita testid**

Run: `python -m pytest tests/test_parser.py -v`
Expected: 6 passed

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .gitignore tootlus tests
git commit -m "feat: kv.ee otsingulehe parser"
```

---

### Task 2: Piirkondade tuvastus (`regions.py`)

**Files:**
- Create: `tootlus/regions.py`
- Test: `tests/test_regions.py`

**Interfaces:**
- Consumes: `config.TALLINN_DISTRICTS`, `config.COUNTY_CENTERS`
- Produces: `regions.Location(city:str|None, district:str|None, subdistrict:str|None)` (frozen dataclass); `regions.parse(location:str) -> Location`; `regions.is_center(county:str, loc:Location) -> bool`; `regions.build_district_map(locs:Iterable[Location]) -> dict[tuple[str,str], str]`; `regions.fill_district(loc:Location, district_map) -> Location`.

- [ ] **Step 1: Kirjuta failivad testid `tests/test_regions.py`**

```python
from tootlus.regions import Location, build_district_map, fill_district, is_center, parse


def test_tallinn_full():
    assert parse("Kristiine City, Kristiine, Tallinn") == Location("Tallinn", "Kristiine", "Kristiine City")


def test_tallinn_reversed_order_uses_known_district():
    assert parse("Kesklinn, Kadriorg, Tallinn") == Location("Tallinn", "Kesklinn", "Kadriorg")


def test_tallinn_only_subdistrict():
    assert parse("Kadriorg, Kadriorg, Tallinn") == Location("Tallinn", None, "Kadriorg")


def test_tallinn_district_only():
    assert parse("Kesklinn, Tallinn") == Location("Tallinn", "Kesklinn", None)


def test_junk_is_ignored():
    assert parse("0 € lepingutasu, Pirita, Tallinn") == Location("Tallinn", "Pirita", None)
    assert parse("soe garaaz, panipak, Mustamäe, Tallinn") == Location("Tallinn", "Mustamäe", None)


def test_city_only():
    assert parse("Narva") == Location("Narva", None, None)


def test_empty():
    assert parse("") == Location(None, None, None)


def test_tartu_drops_redundant_linn():
    assert parse("Südalinn, Kesklinn, Tartu linn, Tartu") == Location("Tartu", "Kesklinn", "Südalinn")
    assert parse("Kesklinn, Tartu linn, Tartu") == Location("Tartu", "Kesklinn", None)


def test_town_inside_parish():
    assert parse("Uus-Rapla, Rapla linn, Rapla vald") == Location("Rapla vald", "Rapla linn", "Uus-Rapla")
    assert parse("Hagudi alevik, Rapla vald") == Location("Rapla vald", "Hagudi alevik", None)


def test_duplicate_city_component():
    assert parse("Kohtla-Järve, Järve, Kohtla-Järve") == Location("Kohtla-Järve", "Järve", None)


def test_is_center():
    assert is_center("Harjumaa", Location("Tallinn", "Kesklinn", None))
    assert not is_center("Harjumaa", Location("Saue vald", "Saue linn", None))
    assert is_center("Raplamaa", Location("Rapla vald", "Rapla linn", "Uus-Rapla"))
    assert not is_center("Raplamaa", Location("Rapla vald", "Hagudi alevik", None))
    assert is_center("Tartumaa", Location("Tartu", "Kesklinn", None))
    assert not is_center("Tartumaa", Location("Tartu vald", "Raadi", None))
    assert is_center("Ida-Virumaa", Location("Jõhvi vald", "Jõhvi linn", None))


def test_fill_district_from_other_listings():
    locs = [
        Location("Tallinn", "Kesklinn", "Kadriorg"),
        Location("Tallinn", "Kesklinn", "Kadriorg"),
        Location("Tallinn", "Pirita", "Kadriorg"),
    ]
    m = build_district_map(locs)
    assert fill_district(Location("Tallinn", None, "Kadriorg"), m) == Location("Tallinn", "Kesklinn", "Kadriorg")
    assert fill_district(Location("Tallinn", None, "Tundmatu"), m) == Location("Tallinn", None, "Tundmatu")
    assert fill_district(Location("Tallinn", "Pirita", None), m) == Location("Tallinn", "Pirita", None)
```

- [ ] **Step 2: Käivita testid, veendu et kukuvad läbi**

Run: `python -m pytest tests/test_regions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tootlus.regions'`

- [ ] **Step 3: Kirjuta `tootlus/regions.py`**

```python
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
```

- [ ] **Step 4: Käivita testid**

Run: `python -m pytest tests/test_regions.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add tootlus/regions.py tests/test_regions.py
git commit -m "feat: aadressist piirkondade tuvastus"
```

---

### Task 3: Kogumine (`scraper.py`)

**Files:**
- Create: `tootlus/scraper.py`
- Test: `tests/test_scraper.py`

**Interfaces:**
- Consumes: `parser.parse_page`, `parser.Listing`, `config.*`
- Produces: `scraper.FetchError`, `scraper.ParseError` (exceptions); `scraper.search_url(deal_type:int, county_id:int, start:int) -> str`; `scraper.http_get(url:str, session=None, sleep=time.sleep) -> str`; `scraper.scrape_county(deal_type:int, county_id:int, fetch=http_get, sleep=time.sleep, on_page=None) -> list[Listing]` kus `on_page(page:int, total:int)`.

- [ ] **Step 1: Kirjuta failivad testid `tests/test_scraper.py`**

```python
import pytest

from tootlus import scraper


def card(i):
    return (
        f'<article class="default object-type-apartment" data-object-id="{i}" data-object-url="/x-{i}">'
        f'<div class="h2"><a data-skeleton="object"><strong>Tn {i}</strong>, Kesklinn, Tallinn</a></div>'
        f'<div class="rooms">2</div><div class="area">50 m²</div><div class="price">100 000 € <small>2 000 €/m²</small></div>'
        f"</article>"
    )


def page(ids):
    return "<html><body>" + "".join(card(i) for i in ids) + "</body></html>"


def test_search_url():
    assert scraper.search_url(2, 12, 100) == "https://www.kv.ee/search?deal_type=2&county=12&start=100"


def test_paginates_until_no_new_ids():
    pages = {0: page(range(1, 51)), 50: page(range(51, 61)), 100: page(range(51, 61))}
    requested = []

    def fetch(url):
        start = int(url.rsplit("start=", 1)[1])
        requested.append(start)
        return pages[start]

    progress = []
    result = scraper.scrape_county(1, 1, fetch=fetch, sleep=lambda s: None, on_page=lambda p, n: progress.append((p, n)))
    assert [l.id for l in result] == list(range(1, 61))
    assert requested == [0, 50, 100]
    assert progress == [(1, 50), (2, 60)]


def test_first_page_without_cards_is_parse_error():
    with pytest.raises(scraper.ParseError):
        scraper.scrape_county(1, 1, fetch=lambda url: "<html></html>", sleep=lambda s: None)


def test_fetch_error_propagates():
    def fetch(url):
        raise scraper.FetchError("katki")

    with pytest.raises(scraper.FetchError):
        scraper.scrape_county(1, 1, fetch=fetch, sleep=lambda s: None)


class FakeResponse:
    def __init__(self, status, body=b""):
        self.status_code = status
        self.content = body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, headers=None, timeout=None):
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_http_get_retries_then_succeeds():
    import requests

    s = FakeSession([requests.ConnectionError("x"), FakeResponse(503), FakeResponse(200, "ü".encode())])
    assert scraper.http_get("u", session=s, sleep=lambda t: None) == "ü"
    assert s.calls == 3


def test_http_get_gives_up():
    s = FakeSession([FakeResponse(500)] * 3)
    with pytest.raises(scraper.FetchError):
        scraper.http_get("u", session=s, sleep=lambda t: None)
```

- [ ] **Step 2: Käivita testid, veendu et kukuvad läbi**

Run: `python -m pytest tests/test_scraper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tootlus.scraper'`

- [ ] **Step 3: Kirjuta `tootlus/scraper.py`**

```python
"""kv.ee otsingutulemuste pärimine maakonna kaupa."""
from __future__ import annotations

import time

import requests

from . import config
from .parser import Listing, parse_page


class FetchError(Exception):
    """Lehte ei õnnestunud alla laadida."""


class ParseError(Exception):
    """Lehelt ei leitud oodatud kuulutusi (tõenäoliselt muutunud HTML)."""


def search_url(deal_type: int, county_id: int, start: int) -> str:
    return f"{config.BASE_URL}?deal_type={deal_type}&county={county_id}&start={start}"


def http_get(url: str, session=None, sleep=time.sleep) -> str:
    session = session or requests
    headers = {"User-Agent": config.USER_AGENT, "Accept-Language": "et-EE,et;q=0.9"}
    last_error = ""
    for attempt in range(config.MAX_RETRIES):
        try:
            response = session.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.content.decode("utf-8", errors="replace")
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
        if attempt < config.MAX_RETRIES - 1:
            sleep(2 ** attempt * 2)
    raise FetchError(f"{url}: {last_error}")


def scrape_county(deal_type: int, county_id: int, fetch=http_get, sleep=time.sleep, on_page=None) -> list[Listing]:
    seen: dict[int, Listing] = {}
    for page in range(config.MAX_PAGES):
        items = parse_page(fetch(search_url(deal_type, county_id, page * config.PAGE_SIZE)))
        if page == 0 and not items:
            raise ParseError(f"maakond {county_id}, tehing {deal_type}: esimeselt lehelt ei leitud kuulutusi")
        new = [item for item in items if item.id not in seen]
        if not new:
            break
        for item in new:
            seen[item.id] = item
        if on_page:
            on_page(page + 1, len(seen))
        sleep(config.REQUEST_DELAY_S)
    return list(seen.values())
```

- [ ] **Step 4: Käivita testid**

Run: `python -m pytest tests/test_scraper.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add tootlus/scraper.py tests/test_scraper.py
git commit -m "feat: kv.ee maakonna kaupa kogumine koos korduskatsetega"
```

---

### Task 4: Andmebaas (`store.py`)

**Files:**
- Create: `tootlus/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `parser.Listing`
- Produces: `store.Store(path:str)` meetoditega `start_run(now:str|None=None) -> int`, `save_listings(run_id:int, deal_type:int, county:str, listings:list[Listing]) -> None`, `finish_run(run_id:int, counties_ok:list[str], complete:bool) -> None`, `runs() -> list[dict]` (võtmed `id, started_at, finished_at, complete, counties_ok`; ainult käivitused, millel `counties_ok` pole tühi, kasvavas järjekorras), `observations(run_id:int) -> list[dict]` (võtmed `id, deal_type, county, location, address, url, rooms, area_m2, price, price_per_m2`), `close()`.

- [ ] **Step 1: Kirjuta failivad testid `tests/test_store.py`**

```python
from tootlus.parser import Listing
from tootlus.store import Store


def L(id, price, area=50.0, rooms=2, location="Kesklinn, Tallinn"):
    return Listing(id, f"https://www.kv.ee/x-{id}", f"Tn 1, {location}", location, rooms, area, price, 1, 2000, "uus")


def test_repeat_listing_keeps_old_price():
    s = Store(":memory:")
    r1 = s.start_run("2026-01-01T00:00:00")
    s.save_listings(r1, 1, "Harjumaa", [L(1, 100000)])
    s.finish_run(r1, ["Harjumaa"], True)
    r2 = s.start_run("2027-01-01T00:00:00")
    s.save_listings(r2, 1, "Harjumaa", [L(1, 120000)])
    s.finish_run(r2, ["Harjumaa"], True)

    assert s.observations(r1)[0]["price"] == 100000
    assert s.observations(r2)[0]["price"] == 120000
    assert s.observations(r1)[0]["price_per_m2"] == 2000
    row = s.conn.execute("SELECT first_seen_run, last_seen_run FROM listings WHERE id=1").fetchone()
    assert tuple(row) == (r1, r2)


def test_observation_keeps_its_own_area_and_rooms():
    s = Store(":memory:")
    r1 = s.start_run()
    s.save_listings(r1, 2, "Harjumaa", [L(1, 500, area=50.0, rooms=2)])
    r2 = s.start_run()
    s.save_listings(r2, 2, "Harjumaa", [L(1, 500, area=40.0, rooms=1)])
    o1, o2 = s.observations(r1)[0], s.observations(r2)[0]
    assert (o1["area_m2"], o1["rooms"]) == (50.0, 2)
    assert (o2["area_m2"], o2["rooms"]) == (40.0, 1)
    assert s.conn.execute("SELECT area_m2 FROM listings WHERE id=1").fetchone()[0] == 40.0


def test_sale_and_rent_with_same_id_are_separate():
    s = Store(":memory:")
    r = s.start_run()
    s.save_listings(r, 1, "Harjumaa", [L(1, 100000)])
    s.save_listings(r, 2, "Harjumaa", [L(1, 500)])
    obs = sorted(s.observations(r), key=lambda o: o["deal_type"])
    assert [(o["deal_type"], o["price"]) for o in obs] == [(1, 100000), (2, 500)]


def test_missing_price_gives_null_price_per_m2():
    s = Store(":memory:")
    r = s.start_run()
    s.save_listings(r, 1, "Harjumaa", [L(1, None)])
    assert s.observations(r)[0]["price_per_m2"] is None


def test_runs_skips_empty_runs():
    s = Store(":memory:")
    r1 = s.start_run("2026-01-01T00:00:00")
    s.finish_run(r1, [], False)
    r2 = s.start_run("2026-02-01T00:00:00")
    s.finish_run(r2, ["Harjumaa", "Hiiumaa"], False)
    runs = s.runs()
    assert [r["id"] for r in runs] == [r2]
    assert runs[0]["counties_ok"] == ["Harjumaa", "Hiiumaa"]
    assert runs[0]["complete"] is False


def test_persists_to_file(tmp_path):
    path = tmp_path / "kv.sqlite"
    s = Store(str(path))
    r = s.start_run()
    s.save_listings(r, 1, "Harjumaa", [L(1, 100000)])
    s.finish_run(r, ["Harjumaa"], True)
    s.close()
    assert Store(str(path)).observations(r)[0]["price"] == 100000
```

- [ ] **Step 2: Käivita testid, veendu et kukuvad läbi**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tootlus.store'`

- [ ] **Step 3: Kirjuta `tootlus/store.py`**

```python
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
```

- [ ] **Step 4: Käivita testid**

Run: `python -m pytest tests/test_store.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add tootlus/store.py tests/test_store.py
git commit -m "feat: SQLite ajalugu käivituste kaupa"
```

---

### Task 5: Tootluse arvutus (`analyze.py`)

**Files:**
- Create: `tootlus/analyze.py`
- Test: `tests/test_analyze.py`

**Interfaces:**
- Consumes: `Store.runs()`, `Store.observations(run_id)`, `regions.*`, `config.*`
- Produces: `analyze.room_group(rooms:int|None) -> str|None`; `analyze.compute(store:Store, generated_at:str|None=None) -> dict` struktuuriga:
  ```
  {"generated_at": str,
   "runs": [{"id", "started_at", "complete", "counties_ok"}],
   "regions": [{"level", "name", "path": [str], "rooms", "yield_median", "yield_latest",
                "valid_runs", "sale_m2", "rent_m2", "n_sale", "n_rent", "enough"}],
   "listings": [{"id", "url", "address", "path": [str], "rooms", "area_m2", "price",
                 "rent_estimate", "yield", "rent_level"}]}
  ```
  `analyze.write_results(results:dict, path:Path) -> None`.

- [ ] **Step 1: Kirjuta failivad testid `tests/test_analyze.py`**

```python
import json

import pytest

from tootlus.analyze import compute, room_group, write_results
from tootlus.parser import Listing
from tootlus.store import Store

SALE, RENT = 1, 2
_next_id = [0]


def mk(location, price, area=50.0, rooms=2):
    _next_id[0] += 1
    i = _next_id[0]
    return Listing(i, f"https://www.kv.ee/x-{i}", f"Tn {i}, {location}", location, rooms, area, price, 1, 2000, None)


def run(store, county, sales, rents, when="2026-01-01T00:00:00"):
    r = store.start_run(when)
    store.save_listings(r, SALE, county, sales)
    store.save_listings(r, RENT, county, rents)
    store.finish_run(r, [county], True)
    return r


def region(results, level, path, rooms="all"):
    hits = [x for x in results["regions"] if x["level"] == level and x["path"] == path and x["rooms"] == rooms]
    assert len(hits) == 1, hits
    return hits[0]


KR = "Kristiine City, Kristiine, Tallinn"


def test_room_group():
    assert [room_group(r) for r in (None, 0, 1, 2, 3, 4, 7)] == [None, None, "1", "2", "3", "4+", "4+"]


def test_yield_formula_and_levels():
    s = Store(":memory:")
    run(s, "Harjumaa", [mk(KR, 100000)] * 1 + [mk(KR, 100000) for _ in range(4)],
        [mk(KR, 500) for _ in range(5)])
    res = compute(s, generated_at="t")
    # 500/50 = 10 €/m² üür, 100000/50 = 2000 €/m² müük -> 10*12/2000 = 0.06
    for level, path in [("county", ["Harjumaa"]), ("city", ["Harjumaa", "Tallinn"]),
                        ("district", ["Harjumaa", "Tallinn", "Kristiine"]),
                        ("subdistrict", ["Harjumaa", "Tallinn", "Kristiine", "Kristiine City"])]:
        r = region(res, level, path)
        assert r["yield_median"] == pytest.approx(0.06)
        assert r["sale_m2"] == pytest.approx(2000)
        assert r["rent_m2"] == pytest.approx(10)
        assert (r["n_sale"], r["n_rent"], r["valid_runs"], r["enough"]) == (5, 5, 1, True)
    assert region(res, "district", ["Harjumaa", "Tallinn", "Kristiine"], "2")["yield_median"] == pytest.approx(0.06)
    assert region(res, "county", ["Harjumaa"])["name"] == "Harjumaa"


def test_below_min_samples_is_not_enough():
    s = Store(":memory:")
    run(s, "Harjumaa", [mk(KR, 100000) for _ in range(5)], [mk(KR, 500) for _ in range(4)])
    r = region(compute(s), "district", ["Harjumaa", "Tallinn", "Kristiine"])
    assert r["yield_median"] is None
    assert r["enough"] is False
    assert r["n_rent"] == 4
    assert r["rent_m2"] == pytest.approx(10)


def test_median_over_runs():
    s = Store(":memory:")
    for i, rent in enumerate([500, 333.3333333, 416.6666667]):  # 0.06, 0.04, 0.05
        run(s, "Harjumaa", [mk(KR, 100000) for _ in range(5)], [mk(KR, rent) for _ in range(5)],
            when=f"202{6 + i}-01-01T00:00:00")
    r = region(compute(s), "district", ["Harjumaa", "Tallinn", "Kristiine"])
    assert r["yield_median"] == pytest.approx(0.05)
    assert r["yield_latest"] == pytest.approx(0.05)
    assert r["valid_runs"] == 3


def test_new_rents_never_matched_with_old_prices():
    s = Store(":memory:")
    run(s, "Harjumaa", [mk(KR, 100000) for _ in range(5)], [mk(KR, 500) for _ in range(5)])
    run(s, "Harjumaa", [], [mk(KR, 1000) for _ in range(5)], when="2027-01-01T00:00:00")
    r = region(compute(s), "district", ["Harjumaa", "Tallinn", "Kristiine"])
    assert r["yield_median"] == pytest.approx(0.06)
    assert r["valid_runs"] == 1
    assert r["yield_latest"] is None
    assert r["n_sale"] == 0


def test_county_without_center():
    s = Store(":memory:")
    saue = "Saue linn, Saue vald"
    run(s, "Harjumaa",
        [mk(KR, 100000) for _ in range(5)] + [mk(saue, 50000) for _ in range(5)],
        [mk(KR, 500) for _ in range(5)] + [mk(saue, 500) for _ in range(5)])
    res = compute(s)
    ex = region(res, "county_ex_center", ["Harjumaa"])
    assert ex["name"] == "Harjumaa (v.a Tallinn)"
    assert ex["yield_median"] == pytest.approx(0.12)
    assert (ex["n_sale"], ex["n_rent"]) == (5, 5)
    assert region(res, "county", ["Harjumaa"])["n_sale"] == 10


def test_outliers_removed():
    s = Store(":memory:")
    run(s, "Harjumaa",
        [mk(KR, 100000) for _ in range(5)] + [mk(KR, 1000), mk(KR, 100000, area=5), mk(KR, None)],
        [mk(KR, 500) for _ in range(5)] + [mk(KR, 100000)])
    r = region(compute(s), "district", ["Harjumaa", "Tallinn", "Kristiine"])
    assert (r["n_sale"], r["n_rent"]) == (5, 5)


def test_missing_district_inferred_from_subdistrict():
    s = Store(":memory:")
    run(s, "Harjumaa", [mk(KR, 100000) for _ in range(5)] + [mk("Kristiine City, Tallinn", 100000)],
        [mk(KR, 500) for _ in range(5)])
    assert region(compute(s), "district", ["Harjumaa", "Tallinn", "Kristiine"])["n_sale"] == 6


def test_best_listings_use_most_precise_level_with_enough_rents():
    s = Store(":memory:")
    other = "Tondi, Kristiine, Tallinn"
    run(s, "Harjumaa",
        [mk(KR, 100000) for _ in range(5)] + [mk(other, 60000)],
        [mk(KR, 500) for _ in range(5)] + [mk(other, 1000)])
    listings = {tuple(l["path"]): l for l in compute(s)["listings"]}
    tondi = listings[("Harjumaa", "Tallinn", "Kristiine", "Tondi")]
    # Tondis on 1 üür (<5) -> kasutatakse linnaosa Kristiine üüri: 6 kuulutust, mediaan 10 €/m²
    assert tondi["rent_level"] == "district"
    assert tondi["rent_estimate"] == pytest.approx(500)
    assert tondi["yield"] == pytest.approx(0.1)
    kr = listings[("Harjumaa", "Tallinn", "Kristiine", "Kristiine City")]
    assert kr["rent_level"] == "subdistrict"
    first = compute(s)["listings"][0]
    assert first["path"][-1] == "Tondi"  # sorditud tootluse järgi


def test_write_results(tmp_path):
    s = Store(":memory:")
    run(s, "Harjumaa", [mk(KR, 100000) for _ in range(5)], [mk(KR, 500) for _ in range(5)])
    out = tmp_path / "data" / "results.json"
    write_results(compute(s, generated_at="t"), out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["generated_at"] == "t"
    assert len(data["runs"]) == 1


def test_empty_store():
    res = compute(Store(":memory:"))
    assert res["regions"] == [] and res["listings"] == [] and res["runs"] == []
```

- [ ] **Step 2: Käivita testid, veendu et kukuvad läbi**

Run: `python -m pytest tests/test_analyze.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tootlus.analyze'`

- [ ] **Step 3: Kirjuta `tootlus/analyze.py`**

```python
"""Piirkondade üüritootluse arvutus."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from statistics import median

from . import config, regions
from .regions import Location

SALE, RENT = config.DEAL_SALE, config.DEAL_RENT
LISTING_LEVELS = ("subdistrict", "district", "city", "county")

Key = tuple[str, tuple[str, ...], str]  # (tase, rada, toarühm)


def room_group(rooms: int | None) -> str | None:
    if rooms is None or rooms < 1:
        return None
    return "4+" if rooms >= 4 else str(rooms)


def _in_range(value, bounds) -> bool:
    return value is not None and bounds[0] <= value <= bounds[1]


def _clean(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        bounds = config.SALE_M2_RANGE if r["deal_type"] == SALE else config.RENT_M2_RANGE
        if _in_range(r["area_m2"], config.AREA_RANGE) and _in_range(r["price_per_m2"], bounds):
            out.append(r)
    return out


def _paths(county: str, loc: Location) -> list[tuple[str, tuple[str, ...]]]:
    paths = [("county", (county,))]
    if not regions.is_center(county, loc):
        paths.append(("county_ex_center", (county,)))
    if loc.city:
        paths.append(("city", (county, loc.city)))
        if loc.district:
            paths.append(("district", (county, loc.city, loc.district)))
            if loc.subdistrict:
                paths.append(("subdistrict", (county, loc.city, loc.district, loc.subdistrict)))
    return paths


def _summarize(sale: list[float], rent: list[float]) -> dict:
    sale_m2 = median(sale) if sale else None
    rent_m2 = median(rent) if rent else None
    enough = len(sale) >= config.MIN_SAMPLES and len(rent) >= config.MIN_SAMPLES
    return {
        "sale_m2": sale_m2, "rent_m2": rent_m2, "n_sale": len(sale), "n_rent": len(rent),
        "yield": rent_m2 * 12 / sale_m2 if enough else None,
    }


def _run_stats(rows: list[dict]) -> dict[Key, dict]:
    buckets: dict[Key, tuple[list, list]] = {}
    for r in rows:
        groups = ["all"] + ([g] if (g := room_group(r["rooms"])) else [])
        for level, path in _paths(r["county"], r["loc"]):
            for g in groups:
                sale, rent = buckets.setdefault((level, path, g), ([], []))
                (sale if r["deal_type"] == SALE else rent).append(r["price_per_m2"])
    return {key: _summarize(sale, rent) for key, (sale, rent) in buckets.items()}


def _region_name(level: str, path: tuple[str, ...]) -> str:
    if level == "county_ex_center":
        return f"{path[0]} (v.a {config.COUNTY_CENTERS[path[0]]})"
    return path[-1]


def _round(value, digits):
    return round(value, digits) if value is not None else None


def _best_listings(rows: list[dict], stats: dict[Key, dict]) -> list[dict]:
    out = []
    for r in rows:
        group = room_group(r["rooms"])
        if r["deal_type"] != SALE or group is None:
            continue
        paths = dict(_paths(r["county"], r["loc"]))
        for level in LISTING_LEVELS:
            s = stats.get((level, paths.get(level), group)) if level in paths else None
            if s and s["n_rent"] >= config.MIN_SAMPLES:
                rent = r["area_m2"] * s["rent_m2"]
                out.append({
                    "id": r["id"], "url": r["url"], "address": r["address"],
                    "path": list(max(paths.values(), key=len)), "rooms": r["rooms"],
                    "area_m2": r["area_m2"], "price": r["price"],
                    "rent_estimate": round(rent, 2), "yield": round(rent * 12 / r["price"], 4),
                    "rent_level": level,
                })
                break
    out.sort(key=lambda x: x["yield"], reverse=True)
    return out[: config.TOP_LISTINGS]


def compute(store, generated_at: str | None = None) -> dict:
    runs = store.runs()
    rows_by_run = {run["id"]: _clean(store.observations(run["id"])) for run in runs}

    all_rows = [r for rows in rows_by_run.values() for r in rows]
    for r in all_rows:
        r["loc"] = regions.parse(r["location"] or "")
    district_map = regions.build_district_map(r["loc"] for r in all_rows)
    for r in all_rows:
        r["loc"] = regions.fill_district(r["loc"], district_map)

    stats_by_run = {run_id: _run_stats(rows) for run_id, rows in rows_by_run.items()}
    run_ids = [run["id"] for run in runs]

    keys = {key for stats in stats_by_run.values() for key in stats}
    region_rows = []
    for key in keys:
        level, path, group = key
        per_run = [stats_by_run[rid][key] for rid in run_ids if key in stats_by_run[rid]]
        valid = [s["yield"] for s in per_run if s["yield"] is not None]
        latest = per_run[-1]
        region_rows.append({
            "level": level, "name": _region_name(level, path), "path": list(path), "rooms": group,
            "yield_median": _round(median(valid), 4) if valid else None,
            "yield_latest": _round(latest["yield"], 4),
            "valid_runs": len(valid),
            "sale_m2": _round(latest["sale_m2"], 1), "rent_m2": _round(latest["rent_m2"], 2),
            "n_sale": latest["n_sale"], "n_rent": latest["n_rent"],
            "enough": bool(valid),
        })
    region_rows.sort(key=lambda x: (x["level"], x["path"], x["rooms"]))

    listings = []
    if run_ids:
        last = run_ids[-1]
        listings = _best_listings(rows_by_run[last], stats_by_run[last])

    return {
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
        "runs": [{k: run[k] for k in ("id", "started_at", "complete", "counties_ok")} for run in runs],
        "regions": region_rows,
        "listings": listings,
    }


def write_results(results: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
```

Märkus `test_new_rents_never_matched_with_old_prices` kohta: teises käivituses pole müüke, seega on selle käivituse `yield` `None` ja `n_sale` 0 — `latest` on viimane käivitus, kus võti esines.

- [ ] **Step 4: Käivita testid**

Run: `python -m pytest tests/test_analyze.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add tootlus/analyze.py tests/test_analyze.py
git commit -m "feat: tootluse arvutus piirkondade ja ajapunktide kaupa"
```

---

### Task 6: Pipeline ja CLI (`pipeline.py`, `run.py`)

**Files:**
- Create: `tootlus/pipeline.py`, `run.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `scraper.scrape_county`, `scraper.FetchError`, `scraper.ParseError`, `Store`, `analyze.compute`, `analyze.write_results`
- Produces: `pipeline.RESULTS_PATH: Path` (`docs/data/results.json`), `pipeline.DB_PATH: Path` (`data/kv.sqlite`); `pipeline.run_once(store, counties:dict[int,str]=config.COUNTIES, scrape=scraper.scrape_county, progress=print, results_path=RESULTS_PATH) -> dict`; `pipeline.analyze_only(store, results_path=RESULTS_PATH) -> dict`; `pipeline.publish(repo_root:Path, run=subprocess.run) -> None`.

- [ ] **Step 1: Kirjuta failivad testid `tests/test_pipeline.py`**

```python
import json

from tootlus import pipeline, scraper
from tootlus.parser import Listing
from tootlus.store import Store


def listings(location, price, n, start):
    return [Listing(start + i, f"u{start + i}", f"Tn, {location}", location, 2, 50.0, price, 1, 2000, None) for i in range(n)]


def test_run_once_saves_and_writes_results(tmp_path):
    def scrape(deal, county_id, on_page=None):
        if on_page:
            on_page(1, 5)
        if deal == 1:
            return listings("Kesklinn, Tallinn", 100000, 5, 0)
        return listings("Kesklinn, Tallinn", 500, 5, 100)

    out = tmp_path / "results.json"
    messages = []
    s = Store(":memory:")
    res = pipeline.run_once(s, counties={1: "Harjumaa"}, scrape=scrape, progress=messages.append, results_path=out)
    assert json.loads(out.read_text(encoding="utf-8"))["runs"][0]["counties_ok"] == ["Harjumaa"]
    assert any(r["level"] == "county" and r["enough"] for r in res["regions"])
    assert s.runs()[0]["complete"] is True
    assert any("Harjumaa" in m for m in messages)


def test_failed_county_is_skipped_but_others_kept(tmp_path):
    def scrape(deal, county_id, on_page=None):
        if county_id == 2 and deal == 2:
            raise scraper.FetchError("võrk maas")
        loc = "Kesklinn, Tallinn" if county_id == 1 else "Kärdla linn, Hiiumaa vald"
        return listings(loc, 100000 if deal == 1 else 500, 5, county_id * 1000 + deal * 100)

    s = Store(":memory:")
    messages = []
    res = pipeline.run_once(s, counties={1: "Harjumaa", 2: "Hiiumaa"}, scrape=scrape,
                            progress=messages.append, results_path=tmp_path / "r.json")
    run = s.runs()[0]
    assert run["counties_ok"] == ["Harjumaa"] and run["complete"] is False
    assert not [r for r in res["regions"] if r["path"][0] == "Hiiumaa"]
    # Hiiumaa müügid ei tohi andmebaasi jõuda ilma üürideta
    assert all(o["county"] == "Harjumaa" for o in s.observations(run["id"]))
    assert any("VIGA" in m and "Hiiumaa" in m for m in messages)


def test_publish_runs_git_commands(tmp_path):
    calls = []

    class Done:
        returncode = 0

    pipeline.publish(tmp_path, run=lambda args, cwd, check: calls.append(args) or Done())
    assert calls[0] == ["git", "add", "data", "docs/data"]
    assert calls[1][:3] == ["git", "commit", "-m"]
    assert calls[2] == ["git", "push"]
```

- [ ] **Step 2: Käivita testid, veendu et kukuvad läbi**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tootlus.pipeline'`

- [ ] **Step 3: Kirjuta `tootlus/pipeline.py`**

```python
"""Üks täiskäivitus: kogumine -> salvestus -> analüüs."""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

from . import analyze, config, scraper

ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = ROOT / "docs" / "data" / "results.json"
DB_PATH = ROOT / "data" / "kv.sqlite"

DEAL_LABELS = {config.DEAL_SALE: "müük", config.DEAL_RENT: "üür"}


def run_once(store, counties=config.COUNTIES, scrape=scraper.scrape_county, progress=print,
             results_path=RESULTS_PATH) -> dict:
    run_id = store.start_run()
    ok: list[str] = []
    for county_id, name in counties.items():
        collected = {}
        try:
            for deal in (config.DEAL_SALE, config.DEAL_RENT):
                label = f"{name} {DEAL_LABELS[deal]}"
                progress(f"{label}: alustan")
                collected[deal] = scrape(
                    deal, county_id,
                    on_page=lambda page, total, label=label: progress(f"{label}: leht {page}, {total} kuulutust"),
                )
        except (scraper.FetchError, scraper.ParseError) as exc:
            progress(f"{name}: VIGA, maakond jäetakse sellest käivitusest välja ({exc})")
            continue
        for deal, items in collected.items():
            store.save_listings(run_id, deal, name, items)
        ok.append(name)
    store.finish_run(run_id, ok, complete=len(ok) == len(counties))
    progress(f"Kogumine valmis: {len(ok)}/{len(counties)} maakonda")
    return analyze_only(store, results_path)


def analyze_only(store, results_path=RESULTS_PATH) -> dict:
    results = analyze.compute(store)
    analyze.write_results(results, results_path)
    return results


def publish(repo_root: Path, run=subprocess.run) -> None:
    run(["git", "add", "data", "docs/data"], cwd=repo_root, check=True)
    run(["git", "commit", "-m", f"Andmete uuendus {date.today().isoformat()}"], cwd=repo_root, check=True)
    run(["git", "push"], cwd=repo_root, check=True)
```

- [ ] **Step 4: Kirjuta `run.py`**

```python
"""Kinnisvara üüritootlus — käsurida.

    python run.py                 kogu kv.ee andmed, salvesta, arvuta tulemused
    python run.py --analyze-only  arvuta tulemused olemasolevast andmebaasist
    python run.py --publish       ... ja tee git commit + push
    python run.py --serve         ava kohalik leht "Käivita uuesti" nupuga
    python run.py --counties 1,2  ainult valitud maakonnad (kv.ee ID-d)
"""
from __future__ import annotations

import argparse
import sys

from tootlus import config, pipeline
from tootlus.store import Store


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="kv.ee korterite üüritootlus piirkondade kaupa")
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--counties", help="komaga eraldatud kv.ee maakonna ID-d, nt 1,12")
    args = parser.parse_args(argv)

    counties = config.COUNTIES
    if args.counties:
        counties = {int(c): config.COUNTIES[int(c)] for c in args.counties.split(",")}

    if args.serve:
        from tootlus.server import serve
        serve(args.port, counties)
        return 0

    pipeline.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = Store(str(pipeline.DB_PATH))
    try:
        if args.analyze_only:
            results = pipeline.analyze_only(store)
        else:
            results = pipeline.run_once(store, counties=counties)
    finally:
        store.close()
    print(f"Tulemused: {pipeline.RESULTS_PATH} ({len(results['regions'])} piirkonnarida, "
          f"{len(results['listings'])} kuulutust)")
    if args.publish:
        pipeline.publish(pipeline.ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Käivita testid**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: 3 passed

- [ ] **Step 6: Kontrolli CLI tühja andmebaasiga**

Run: `python run.py --analyze-only`
Expected: `Tulemused: ...docs\data\results.json (0 piirkonnarida, 0 kuulutust)`; fail `docs/data/results.json` on olemas.

- [ ] **Step 7: Commit**

```bash
git add tootlus/pipeline.py run.py tests/test_pipeline.py
git commit -m "feat: täiskäivituse pipeline ja käsurida"
```

---

### Task 7: Kohalik server (`server.py`)

**Files:**
- Create: `tootlus/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `pipeline.run_once`, `pipeline.DB_PATH`, `Store`
- Produces: `server.RunState` (lõimekindel olek: `running:bool`, `messages:list[str]`, `error:str|None`, `finished_at:str|None`; meetodid `start(runner) -> bool`, `snapshot() -> dict`); `server.make_server(port:int, docs_dir:Path, state:RunState, runner) -> ThreadingHTTPServer` kus `runner(progress)`; `server.serve(port:int, counties:dict) -> None`.
- HTTP: `GET /api/status` → 200 JSON `{"running", "messages", "error", "finished_at"}`; `POST /api/run` → 202 `{"started": true}` või 409 kui juba käib; muu → staatilised failid kaustast `docs/`.

- [ ] **Step 1: Kirjuta failivad testid `tests/test_server.py`**

```python
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from tootlus.server import RunState, make_server


@pytest.fixture
def server(tmp_path):
    (tmp_path / "index.html").write_text("<h1>tere</h1>", encoding="utf-8")
    gate = threading.Event()

    def runner(progress):
        progress("Harjumaa müük: leht 1")
        gate.wait(5)

    state = RunState()
    srv = make_server(0, tmp_path, state, runner)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", gate, state
    gate.set()
    srv.shutdown()


def get_json(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


def post(url):
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def wait_until(pred, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_serves_static_files(server):
    base, _, _ = server
    with urllib.request.urlopen(base + "/") as r:
        assert b"tere" in r.read()


def test_run_lifecycle(server):
    base, gate, _ = server
    assert get_json(base + "/api/status")["running"] is False
    assert post(base + "/api/run") == 202
    assert wait_until(lambda: get_json(base + "/api/status")["messages"] == ["Harjumaa müük: leht 1"])
    assert get_json(base + "/api/status")["running"] is True
    assert post(base + "/api/run") == 409
    gate.set()
    assert wait_until(lambda: get_json(base + "/api/status")["running"] is False)
    status = get_json(base + "/api/status")
    assert status["error"] is None and status["finished_at"]


def test_runner_error_is_reported():
    state = RunState()

    def boom(progress):
        raise RuntimeError("katki")

    assert state.start(boom)
    assert wait_until(lambda: not state.snapshot()["running"])
    assert "katki" in state.snapshot()["error"]
```

- [ ] **Step 2: Käivita testid, veendu et kukuvad läbi**

Run: `python -m pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tootlus.server'`

- [ ] **Step 3: Kirjuta `tootlus/server.py`**

```python
"""Kohalik veebiserver: serveerib docs/ kausta ja lubab kogumise uuesti käivitada."""
from __future__ import annotations

import json
import threading
import webbrowser
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import pipeline
from .store import Store

MAX_MESSAGES = 50


class RunState:
    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self.messages: list[str] = []
        self.error: str | None = None
        self.finished_at: str | None = None

    def _progress(self, message: str) -> None:
        with self._lock:
            self.messages = (self.messages + [message])[-MAX_MESSAGES:]

    def start(self, runner) -> bool:
        with self._lock:
            if self.running:
                return False
            self.running, self.messages, self.error, self.finished_at = True, [], None, None
        threading.Thread(target=self._work, args=(runner,), daemon=True).start()
        return True

    def _work(self, runner) -> None:
        error = None
        try:
            runner(self._progress)
        except Exception as exc:  # noqa: BLE001 - kõik vead tuleb kasutajale näidata
            error = f"{type(exc).__name__}: {exc}"
        with self._lock:
            self.running, self.error = False, error
            self.finished_at = datetime.now().isoformat(timespec="seconds")

    def snapshot(self) -> dict:
        with self._lock:
            return {"running": self.running, "messages": list(self.messages),
                    "error": self.error, "finished_at": self.finished_at}


def _handler(state: RunState, runner):
    class Handler(SimpleHTTPRequestHandler):
        def _json(self, code: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.split("?")[0] == "/api/status":
                return self._json(200, state.snapshot())
            return super().do_GET()

        def do_POST(self):
            if self.path.split("?")[0] != "/api/run":
                return self._json(404, {"error": "not found"})
            if state.start(runner):
                return self._json(202, {"started": True})
            return self._json(409, {"started": False, "error": "kogumine juba käib"})

        def end_headers(self):
            if not self.path.startswith("/api/"):
                self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, format, *args):
            pass

    return Handler


def make_server(port: int, docs_dir: Path, state: RunState, runner) -> ThreadingHTTPServer:
    handler = partial(_handler(state, runner), directory=str(docs_dir))
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(port: int, counties: dict) -> None:
    def runner(progress):
        pipeline.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        store = Store(str(pipeline.DB_PATH))
        try:
            pipeline.run_once(store, counties=counties, progress=progress)
        finally:
            store.close()

    server = make_server(port, pipeline.ROOT / "docs", RunState(), runner)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Leht avatud: {url}  (Ctrl+C lõpetab)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
```

- [ ] **Step 4: Käivita testid**

Run: `python -m pytest tests/test_server.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add tootlus/server.py tests/test_server.py
git commit -m "feat: kohalik server koos uuesti käivitamise API-ga"
```

---

### Task 8: Veebileht (`docs/`)

**Files:**
- Create: `docs/.nojekyll` (tühi), `docs/index.html`, `docs/style.css`, `docs/app.js`

**Interfaces:**
- Consumes: `docs/data/results.json` (Task 5 struktuur), `GET api/status`, `POST api/run` (Task 7; GitHub Pages'il puuduvad → nupp peidetud).

- [ ] **Step 1: Laadi `impeccable` oskus ja tee `shape`** — sisend: andmetihe töölaud kinnisvarainvestorile, eesti keel, kaks vaadet (piirkonnad / kuulutused), filtrid, sorditav tabel, hallid "vähe andmeid" read, mobiilis kasutatav. Allolev kood on funktsionaalne alus; impeccable'i soovitused rakendatakse `style.css` ja `index.html` struktuuri, ilma `app.js` andmeloogikat (filtrid, sortimine, API) muutmata.

- [ ] **Step 2: Kirjuta `docs/index.html`**

```html
<!doctype html>
<html lang="et">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Üüritootlus</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="top">
    <div>
      <h1>Üüritootlus</h1>
      <p class="sub" id="meta">Laen andmeid…</p>
    </div>
    <div class="run" id="run" hidden>
      <button id="run-btn" type="button">Käivita uuesti</button>
      <p class="run-log" id="run-log" aria-live="polite"></p>
    </div>
  </header>

  <nav class="tabs" role="tablist">
    <button role="tab" data-view="regions" aria-selected="true">Piirkonnad</button>
    <button role="tab" data-view="listings" aria-selected="false">Parimad kuulutused</button>
  </nav>

  <section class="filters">
    <label class="f-level">Tase
      <select id="level">
        <option value="county">Maakond</option>
        <option value="city">Linn / vald</option>
        <option value="district" selected>Linnaosa / alev</option>
        <option value="subdistrict">Asum / küla</option>
      </select>
    </label>
    <label class="f-excenter check"><input type="checkbox" id="ex-center"> Ilma maakonnakeskuseta</label>
    <label>Toad
      <select id="rooms">
        <option value="all">Kõik</option><option value="1">1</option><option value="2">2</option>
        <option value="3">3</option><option value="4+">4+</option>
      </select>
    </label>
    <label>Asukoht
      <select id="parent"><option value="">Kõik</option></select>
    </label>
    <label class="grow">Otsi <input type="search" id="query" placeholder="nt Kalamaja"></label>
    <label class="check"><input type="checkbox" id="show-thin" checked> Näita vähe andmetega ridu</label>
  </section>

  <main>
    <p class="hint" id="hint"></p>
    <div class="table-wrap"><table id="table"><thead></thead><tbody></tbody></table></div>
    <p class="empty" id="empty" hidden>Andmeid pole. Käivita <code>python run.py</code>.</p>
  </main>

  <footer class="foot">
    Bruto tootlus = üüri €/m² mediaan × 12 / müügi €/m² mediaan, arvutatud iga käivituse andmetest eraldi;
    „Tootlus” on käivituste mediaan. Rida loetakse kehtivaks, kui müügi- ja üürikuulutusi on kumbagi vähemalt 5.
    Allikas: kv.ee.
  </footer>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Kirjuta `docs/app.js`**

```js
"use strict";

const state = {
  data: null, view: "regions", level: "district", exCenter: false, rooms: "all",
  parent: "", query: "", showThin: true, sort: { key: "yield_median", dir: -1 },
};

const LEVEL_NAMES = { county: "maakond", county_ex_center: "maakond", city: "linn/vald",
  district: "linnaosa", subdistrict: "asum" };

const pct = new Intl.NumberFormat("et-EE", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
const eur = new Intl.NumberFormat("et-EE", { maximumFractionDigits: 0 });
const eur2 = new Intl.NumberFormat("et-EE", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const fmt = (f, v) => (v === null || v === undefined ? "–" : f.format(v));
const $ = (id) => document.getElementById(id);

const COLUMNS = {
  regions: [
    { key: "name", label: "Piirkond", cell: (r) => esc(r.name) },
    { key: "parent", label: "Asukoht", cell: (r) => esc(r.parent), cls: "muted" },
    { key: "yield_median", label: "Tootlus", num: true, cell: (r) => fmt(pct, r.yield_median), cls: "strong" },
    { key: "yield_latest", label: "Viimane", num: true, cell: (r) => fmt(pct, r.yield_latest) },
    { key: "sale_m2", label: "Müük €/m²", num: true, cell: (r) => fmt(eur, r.sale_m2) },
    { key: "rent_m2", label: "Üür €/m²", num: true, cell: (r) => fmt(eur2, r.rent_m2) },
    { key: "n_sale", label: "Müük / üür", num: true, cell: (r) => `${r.n_sale} / ${r.n_rent}` },
    { key: "valid_runs", label: "Ajapunkte", num: true, cell: (r) => r.valid_runs },
  ],
  listings: [
    { key: "address", label: "Aadress", cell: (r) => `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.address)}</a>` },
    { key: "parent", label: "Piirkond", cell: (r) => esc(r.parent), cls: "muted" },
    { key: "rooms", label: "Toad", num: true, cell: (r) => r.rooms },
    { key: "area_m2", label: "m²", num: true, cell: (r) => fmt(eur2, r.area_m2) },
    { key: "price", label: "Hind €", num: true, cell: (r) => fmt(eur, r.price) },
    { key: "rent_estimate", label: "Oodatav üür €", num: true, cell: (r) => fmt(eur, r.rent_estimate) },
    { key: "yield", label: "Tootlus", num: true, cell: (r) => fmt(pct, r.yield), cls: "strong" },
    { key: "rent_level", label: "Üür tasemelt", cell: (r) => LEVEL_NAMES[r.rent_level] || r.rent_level, cls: "muted" },
  ],
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function effectiveLevel() {
  return state.level === "county" && state.exCenter ? "county_ex_center" : state.level;
}

function regionRows() {
  const level = effectiveLevel();
  return state.data.regions
    .filter((r) => r.level === level && r.rooms === state.rooms)
    .map((r) => ({ ...r, parent: r.path.slice(0, -1).join(" › ") }));
}

function listingRows() {
  return state.data.listings
    .filter((r) => state.rooms === "all" || roomGroup(r.rooms) === state.rooms)
    .map((r) => ({ ...r, parent: r.path.join(" › ") }));
}

function roomGroup(n) { return n >= 4 ? "4+" : String(n); }

function rowsForView() {
  let rows = state.view === "regions" ? regionRows() : listingRows();
  if (state.parent) rows = rows.filter((r) => r.parent === state.parent || r.parent.startsWith(state.parent + " › "));
  if (state.query) {
    const q = state.query.toLocaleLowerCase("et");
    rows = rows.filter((r) => ((r.name || r.address) + " " + r.parent).toLocaleLowerCase("et").includes(q));
  }
  if (state.view === "regions" && !state.showThin) rows = rows.filter((r) => r.enough);
  const { key, dir } = state.sort;
  rows.sort((a, b) => {
    if (state.view === "regions" && a.enough !== b.enough) return a.enough ? -1 : 1;
    const x = a[key], y = b[key];
    if (x === null || x === undefined) return 1;
    if (y === null || y === undefined) return -1;
    return (typeof x === "string" ? x.localeCompare(y, "et") : x - y) * dir;
  });
  return rows;
}

function parentOptions() {
  const rows = state.view === "regions" ? regionRows() : listingRows();
  const set = new Set();
  rows.forEach((r) => {
    const parts = r.parent.split(" › ").filter(Boolean);
    for (let i = 1; i <= parts.length; i++) set.add(parts.slice(0, i).join(" › "));
  });
  return [...set].sort((a, b) => a.localeCompare(b, "et"));
}

function renderParent() {
  const sel = $("parent");
  const opts = parentOptions();
  if (state.parent && !opts.includes(state.parent)) state.parent = "";
  sel.innerHTML = `<option value="">Kõik</option>` +
    opts.map((o) => `<option value="${esc(o)}"${o === state.parent ? " selected" : ""}>${esc(o)}</option>`).join("");
}

function render() {
  const cols = COLUMNS[state.view];
  const rows = rowsForView();
  document.querySelectorAll(".tabs [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === state.view)));
  document.querySelectorAll(".f-level, .f-excenter").forEach((el) => (el.hidden = state.view !== "regions"));
  $("ex-center").disabled = state.level !== "county";
  $("show-thin").parentElement.hidden = state.view !== "regions";
  renderParent();

  $("table").querySelector("thead").innerHTML = "<tr>" + cols.map((c) => {
    const active = state.sort.key === c.key;
    const aria = active ? (state.sort.dir > 0 ? "ascending" : "descending") : "none";
    return `<th class="${c.num ? "num" : ""}" aria-sort="${aria}"><button type="button" data-sort="${c.key}">${c.label}</button></th>`;
  }).join("") + "</tr>";

  $("table").querySelector("tbody").innerHTML = rows.map((r) =>
    `<tr class="${state.view === "regions" && !r.enough ? "thin" : ""}">` +
    cols.map((c) => `<td class="${[c.num ? "num" : "", c.cls || ""].join(" ")}">${c.cell(r)}</td>`).join("") + "</tr>"
  ).join("");

  $("empty").hidden = rows.length > 0;
  $("hint").textContent = state.view === "regions"
    ? `${rows.length} piirkonda · hallid read: alla 5 müügi- või üürikuulutuse`
    : `${rows.length} müügikuulutust viimasest käivitusest · oodatav üür piirkonna üüri €/m² mediaanist`;
}

function renderMeta() {
  const runs = state.data.runs;
  if (!runs.length) { $("meta").textContent = "Andmeid pole veel kogutud."; return; }
  const last = runs[runs.length - 1];
  const when = new Date(last.started_at).toLocaleDateString("et-EE", { day: "numeric", month: "long", year: "numeric" });
  const partial = last.complete ? "" : ` · viimane käivitus osaline (${last.counties_ok.length} maakonda)`;
  $("meta").textContent = `Uuendatud ${when} · ${runs.length} ajapunkt${runs.length === 1 ? "" : "i"}${partial}`;
}

async function loadData() {
  const res = await fetch("data/results.json", { cache: "no-store" });
  state.data = res.ok ? await res.json() : { runs: [], regions: [], listings: [] };
  renderMeta();
  render();
}

async function pollStatus() {
  let status;
  try {
    const res = await fetch("api/status", { cache: "no-store" });
    if (!res.ok) return;
    status = await res.json();
  } catch { return; }
  $("run").hidden = false;
  $("run-btn").disabled = status.running;
  $("run-btn").textContent = status.running ? "Kogun…" : "Käivita uuesti";
  const last = status.messages[status.messages.length - 1];
  $("run-log").textContent = status.error ? `Viga: ${status.error}` : (status.running ? last || "Alustan…" : (status.finished_at ? "Valmis." : ""));
  if (status.running) setTimeout(pollStatus, 1500);
  else if (state.wasRunning) loadData();
  state.wasRunning = status.running;
}

function bind() {
  document.querySelectorAll(".tabs [role=tab]").forEach((b) => b.addEventListener("click", () => {
    state.view = b.dataset.view;
    state.parent = "";
    state.sort = { key: state.view === "regions" ? "yield_median" : "yield", dir: -1 };
    render();
  }));
  $("level").addEventListener("change", (e) => { state.level = e.target.value; state.parent = ""; render(); });
  $("ex-center").addEventListener("change", (e) => { state.exCenter = e.target.checked; render(); });
  $("rooms").addEventListener("change", (e) => { state.rooms = e.target.value; render(); });
  $("parent").addEventListener("change", (e) => { state.parent = e.target.value; render(); });
  $("query").addEventListener("input", (e) => { state.query = e.target.value.trim(); render(); });
  $("show-thin").addEventListener("change", (e) => { state.showThin = e.target.checked; render(); });
  $("table").querySelector("thead").addEventListener("click", (e) => {
    const key = e.target.closest("button")?.dataset.sort;
    if (!key) return;
    state.sort = { key, dir: state.sort.key === key ? -state.sort.dir : (key === "name" || key === "address" || key === "parent" ? 1 : -1) };
    render();
  });
  $("run-btn").addEventListener("click", async () => {
    $("run-btn").disabled = true;
    await fetch("api/run", { method: "POST" });
    state.wasRunning = true;
    pollStatus();
  });
}

bind();
loadData();
pollStatus();
```

- [ ] **Step 4: Kirjuta `docs/style.css`** (alus; impeccable `shape`/`polish` täiustab)

```css
:root {
  --bg: #f7f6f2; --surface: #ffffff; --ink: #1d1f1c; --muted: #6b6e66; --line: #e3e1da;
  --accent: #1f6f50; --accent-ink: #ffffff; --thin: #a3a59d;
  --radius: 6px; --font: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #151714; --surface: #1d201c; --ink: #e9e8e3; --muted: #9a9c94; --line: #2e322c;
    --accent: #5cc195; --accent-ink: #0d1a14; --thin: #62655e; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.45 var(--font); }
.top, .tabs, .filters, main, .foot { max-width: 1200px; margin: 0 auto; padding: 0 16px; }
.top { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; padding-top: 28px; padding-bottom: 16px; flex-wrap: wrap; }
h1 { margin: 0; font-size: 28px; letter-spacing: -0.01em; }
.sub { margin: 4px 0 0; color: var(--muted); }
.run { text-align: right; }
.run button { background: var(--accent); color: var(--accent-ink); border: 0; border-radius: var(--radius); padding: 9px 16px; font: inherit; font-weight: 600; cursor: pointer; }
.run button:disabled { opacity: .6; cursor: progress; }
.run-log { margin: 6px 0 0; color: var(--muted); font-size: 13px; min-height: 1.2em; }
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); }
.tabs button { background: none; border: 0; border-bottom: 2px solid transparent; padding: 10px 12px; font: inherit; color: var(--muted); cursor: pointer; }
.tabs button[aria-selected="true"] { color: var(--ink); border-color: var(--accent); font-weight: 600; }
.filters { display: flex; flex-wrap: wrap; gap: 12px 16px; align-items: flex-end; padding-top: 16px; padding-bottom: 8px; }
.filters label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--muted); }
.filters label.check { flex-direction: row; align-items: center; gap: 6px; padding-bottom: 8px; }
.filters label.grow { flex: 1 1 180px; }
.filters select, .filters input[type=search] { font: inherit; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 7px 9px; min-width: 120px; }
[hidden] { display: none !important; }
.hint { color: var(--muted); font-size: 13px; margin: 8px 0; }
.table-wrap { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--line); white-space: nowrap; }
th button { all: unset; cursor: pointer; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
th[aria-sort="ascending"] button::after { content: " ↑"; }
th[aria-sort="descending"] button::after { content: " ↓"; }
.num { text-align: right; }
td.strong { font-weight: 650; }
td.muted { color: var(--muted); }
tr.thin td { color: var(--thin); }
tbody tr:hover { background: color-mix(in srgb, var(--accent) 6%, transparent); }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.empty { color: var(--muted); padding: 24px 0; }
.foot { color: var(--muted); font-size: 13px; padding-top: 24px; padding-bottom: 40px; max-width: 760px; margin-left: max(0px, calc((100% - 1200px) / 2)); }
```

- [ ] **Step 5: Kontrolli brauseris näidisandmetega** — loo ajutine andmebaas skriptiga scratchpad'is (mitte repos), käivita `python -c "from tootlus.server import make_server, RunState; ..."` või lihtsalt `python run.py --serve` pärast Task 9 päris käivitust. Kontrolli: vaadete vahetus, tasemed, "ilma keskuseta" lüliti (ainult maakonna tasemel aktiivne), toafilter, asukohafilter, otsing, sortimine, hallid read, mobiililaius 375 px ilma horisontaalse lehe kerimiseta (tabel kerib oma kastis).

- [ ] **Step 6: impeccable `audit` + `polish`** ja paranda leitu `style.css`/`index.html`-s.

- [ ] **Step 7: Commit**

```bash
git add docs/.nojekyll docs/index.html docs/style.css docs/app.js
git commit -m "feat: veebileht piirkondade ja kuulutuste vaatega"
```

---

### Task 9: Päris käivitus, README ja GitHub Pages

**Files:**
- Modify: `README.md`
- Create (genereeritud): `data/kv.sqlite`, `docs/data/results.json`

- [ ] **Step 1: Kiire päris test ühe väikese maakonnaga**

Run: `python run.py --counties 2` (Hiiumaa)
Expected: logis "Hiiumaa müük: leht 1, N kuulutust", "Hiiumaa üür: …", "Kogumine valmis: 1/1 maakonda"; ilma Python veata.

- [ ] **Step 2: Kontrolli parseri tulemusi päris andmetel**

Run:
```bash
python -c "import sqlite3; c=sqlite3.connect('data/kv.sqlite'); print(c.execute('select deal_type,count(*),sum(price is null),sum(area_m2 is null),sum(rooms is null) from observations group by deal_type').fetchall()); print(c.execute('select location from listings limit 15').fetchall())"
```
Expected: puuduvate hindade/pindade osakaal väike (< 5%); `location` väärtused ilma tänavata.

- [ ] **Step 3: Kustuta testikäivitus ja tee täiskäivitus**

Testikäivitus oleks osaline ajapunkt, seega kustuta see: `rm data/kv.sqlite`, siis
Run: `python run.py` (ca 10–20 min)
Expected: "Kogumine valmis: 15/15 maakonda"; `docs/data/results.json` sisaldab ridu kõigil tasemetel.

- [ ] **Step 4: Kontrolli tulemuste mõistlikkust**

Run:
```bash
python -c "import json; d=json.load(open('docs/data/results.json',encoding='utf-8')); r=[x for x in d['regions'] if x['level']=='district' and x['rooms']=='all' and x['enough']]; r.sort(key=lambda x:-x['yield_median']); [print(x['path'], x['yield_median'], x['n_sale'], x['n_rent']) for x in r[:10]]; print(len(d['listings']))"
```
Expected: tootlused enamasti vahemikus 0,03–0,12; Tallinna linnaosad olemas; kuulutusi kuni 500.

- [ ] **Step 5: Kirjuta `README.md`**

````markdown
# Kinnisvara üüritootlus

Kogub kv.ee korterite müügi- ja üürikuulutused, hoiab ajalugu (`data/kv.sqlite`) ja arvutab, millistes
piirkondades on bruto üüritootlus kõige parem. Iga käivitus on eraldi ajapunkt; tulemus on ajapunktide mediaan.

## Kasutamine

```bash
pip install -r requirements.txt
python run.py              # kogu (10–20 min), salvesta, arvuta
python run.py --serve      # ava leht kohalikult koos "Käivita uuesti" nupuga
python run.py --publish    # kogu ja lükka tulemused GitHubi
python run.py --analyze-only
```

Veebileht asub kaustas `docs/` (GitHub Pages: Settings → Pages → Branch `main`, kaust `/docs`).

## Arvutus

- Tootlus = üüri €/m² mediaan × 12 / müügi €/m² mediaan, sama käivituse andmetest, piirkonna ja toarühma kaupa.
- Kehtiv ajapunkt vajab vähemalt 5 müügi- ja 5 üürikuulutust; „Tootlus” on kehtivate ajapunktide mediaan.
- „Ilma maakonnakeskuseta” jätab maakonna arvutusest välja keskuse (nt Harjumaa v.a Tallinn).
- Lävendid ja maakonnakeskused: `tootlus/config.py`.

## Testid

```bash
python -m pytest
```
````

- [ ] **Step 6: Täielik testikomplekt**

Run: `python -m pytest -v`
Expected: kõik testid läbivad (6 + 12 + 6 + 6 + 11 + 3 + 3 = 47).

- [ ] **Step 7: Commit**

```bash
git add README.md data/kv.sqlite docs/data/results.json
git commit -m "Esimene andmekogumine ja README"
```

- [ ] **Step 8: GitHub Pages** — kui repol on GitHubi remote (`git remote -v`), küsi kasutajalt luba push'iks ja Pages'i sisselülitamiseks (`gh api -X POST repos/{owner}/{repo}/pages -f "source[branch]=main" -f "source[path]=/docs"`). Kui remote puudub, anna kasutajale juhised.
