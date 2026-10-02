# Kauguse mudel ja salvestatud lehtede import — rakendusplaan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** kv.ee salvestatud otsingulehtede import + Tallinna hinna-kauguse mudel (keskpunkt andmetest, "+100 m" mõju, alahinnatud asumid/kuulutused) koos teise veebilehega `docs/mudel.html`.

**Architecture:** `importer.py` loob salvestatud HTML-failidest tavalise käivituse (sama `Store`). `geocode.py` toob Tallinna aadressidele koordinaadid In-ADS-ist ja hoiab neid SQLite vahemälus. `model.py` (numpy vähimruutude regressioon) arvutab iga käivituse kohta keskpunkti, kauguse mõju ja hälbed ning kirjutab `docs/data/model.json`. `pipeline.analyze_only` käivitab nüüd ka geokodeerimise ja mudeli. Staatiline leht `docs/mudel.html` + `docs/mudel.js` (Leaflet + inline SVG).

**Tech Stack:** Python 3.14, numpy, beautifulsoup4/lxml, sqlite3, urllib, pytest; vanilla JS, Leaflet 1.9.4 (cdnjs), OpenStreetMap aluskaart.

**Spec:** `docs/superpowers/specs/2026-10-01-kauguse-mudel-design.md` (eelnev: `docs/superpowers/specs/2026-10-01-kinnisvara-tootlus-design.md`)

## Global Constraints

- Mitte mingit Cloudflare'i kontrolli lahendamist, brauseri matkimist ega kv.ee automaatkogumise "parandamist" — kv.ee andmed tulevad olemasolevast kogumisest või salvestatud lehtede impordist.
- Testid ei tee võrgupäringuid (In-ADS fetch süstitakse).
- Mudel ainult Tallinna kuulutustele (`regions.parse(location).city == "Tallinn"`).
- Kauguse murdepunktid 2, 5, 8 km; keskpunkti otsing lat 59.35–59.50, lon 24.55–24.95, samm 250 m, siis 50 m ±300 m.
- Alahinnatud kuulutus: hälve ≤ −15%. Asum tabelis/kaardil: ≥ 5 müügikuulutust.
- Käivitus mudelisse ainult kui Tallinna geokodeeritud müügivaatlusi ≥ 50 ja üürivaatlusi ≥ 30.
- Tüüpkorter kõvera jaoks: 2 tuba, 50 m², 1991–2010, heas korras, mitte 1. korrus.
- "+100 m" mõju kaugustel 1, 3, 6 km: `exp(kalle(d) × 0.1) − 1`.
- Vabaduse väljak: lat 59.4339, lon 24.7445.
- In-ADS: `https://inaadress.maaamet.ee/inaadress/gazetteer?address=<päring>&results=1`, väljad `viitepunkt_b` (lat), `viitepunkt_l` (lon), `asum`; päringute vahel 0,2 s.
- Kasutajale nähtav tekst eesti keeles.
- Kõik commit-sõnumid lõpevad tühja rea ja `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`-ga.

## Review Focus

1. **Brauserist salvestatud lehe kuju** ("Veebileht, täielik" vs "ainult HTML", lisafailide kaust kõrval, Windowsi kodeering) — import ei tohi krahhida; tundmatu fail jäetakse logiga vahele. → Task 1 test (fail ilma canonical URL-ita, mitte-HTML fail kaustas).
2. **Aadress ilma majanumbrita või korteri numbriga** ("Lennuki tn", "Seebi 24a-8") — päring peab olema mõistlik; tühi tänav ei tee päringut. → Task 2 testid.
3. **Haruldane kategooria** (nt ükski kuulutus pole "vajab remonti") — regressioon ei tohi kukkuda singulaarse maatriksi tõttu. → Task 3 test (puuduvate kategooriatega andmed).
4. **Liiga vähe andmeid** (import ainult ühest maakonnast väljaspool Tallinna) — `model.json` peab olema kirjutatud tühja tulemusega ja leht näitab tühja olekut. → Task 4 test.
5. **Geokodeerimise võrguviga keset tööd** — mudel jätkab olemasolevate koordinaatidega, viga ei salvestu "ei leitud"-ina. → Task 2 test.

---

## File Structure

```
tootlus/config.py      + county_slug(name)
tootlus/importer.py    UUS: salvestatud lehtede import
tootlus/geocode.py     UUS: In-ADS geokodeerija + vahemälu
tootlus/model.py       UUS: regressioon, keskpunkt, mudeli tulemused
tootlus/analyze.py     _clean -> clean (avalik)
tootlus/store.py       + listing_attrs()
tootlus/pipeline.py    analyze_only: + geokodeerimine + mudel -> model.json
run.py                 + --import-dir
requirements.txt       + numpy
docs/mudel.html, docs/mudel.js   UUS
docs/index.html, docs/style.css  + navigatsioon
tests/fixtures/saved_sale.html, tests/fixtures/saved_rent.html  UUS
tests/test_importer.py, test_geocode.py, test_model.py  UUS; test_pipeline.py muudetud
README.md              UUS (Task 6)
```

---

### Task 1: Salvestatud lehtede import

**Files:**
- Modify: `tootlus/config.py` (lisa `county_slug`), `run.py`
- Create: `tootlus/importer.py`, `tests/fixtures/saved_sale.html`, `tests/fixtures/saved_rent.html`
- Test: `tests/test_importer.py`

**Interfaces:**
- Consumes: `parser.parse_page`, `Store.start_run/save_listings/finish_run`, `config.COUNTIES`, `config.DEAL_SALE/DEAL_RENT`
- Produces: `config.county_slug(name:str) -> str`; `importer.page_identity(html:str) -> tuple[int, str] | None` (deal_type, maakonna nimi); `importer.import_dir(store, directory:Path, progress=print) -> list[str]` (counties_ok); CLI `python run.py --import-dir <kaust>`.

- [ ] **Step 1: Loo fixture'id**

`tests/fixtures/saved_sale.html`:
```html
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="canonical" href="https://www.kv.ee/korterid-muuk/harjumaa/tallinn" />
<title>Korterite müük Tallinnas - KV.EE</title></head><body>
<article class="default object-type-apartment " data-object-id="1001" data-object-url="/a-1001">
  <div class="description"><div class="h2"><a data-skeleton="object"> <strong>Sammu tn 10-56</strong>, Kristiine City, Kristiine, Tallinn </a></div>
  <p class="object-excerpt"> Korrus 3/7, Korteriomand, ehitusaasta 2005, heas korras </p></div>
  <div class="rooms"> 2 </div><div class="area"> 50&nbsp;m² </div>
  <div class="price"> 150 000 € <small> 3 000 €/m² </small> </div>
</article>
<article class="default object-type-apartment " data-object-id="1002" data-object-url="/a-1002">
  <div class="description"><div class="h2"><a data-skeleton="object"> <strong>Krulli 10-94</strong>, Kalamaja, Põhja-Tallinn, Tallinn </a></div>
  <p class="object-excerpt"> Korrus 1/12, ehitusaasta 2026, uus </p></div>
  <div class="rooms"> 3 </div><div class="area"> 80&nbsp;m² </div>
  <div class="price"> 400 000 € <small> 5 000 €/m² </small> </div>
</article>
</body></html>
```

`tests/fixtures/saved_rent.html`:
```html
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta property="og:url" content="https://www.kv.ee/korterid-uur/harjumaa?start=50" />
<title>Korterite üür Harjumaal - KV.EE</title></head><body>
<article class="default object-type-apartment " data-object-id="2001" data-object-url="/b-2001">
  <div class="description"><div class="h2"><a data-skeleton="object"> <strong>Pikk 1</strong>, Vanalinn, Kesklinn, Tallinn </a></div>
  <p class="object-excerpt"> Korrus 2/4, heas korras </p></div>
  <div class="rooms"> 2 </div><div class="area"> 50&nbsp;m² </div>
  <div class="price"> 750 € <small> 15 €/m² </small> </div>
</article>
</body></html>
```

- [ ] **Step 2: Kirjuta failivad testid `tests/test_importer.py`**

```python
import shutil
from pathlib import Path

from tootlus import config
from tootlus.importer import import_dir, page_identity
from tootlus.store import Store

FIX = Path(__file__).parent / "fixtures"


def test_county_slug():
    assert config.county_slug("Harjumaa") == "harjumaa"
    assert config.county_slug("Ida-Virumaa") == "ida-virumaa"
    assert config.county_slug("Jõgevamaa") == "jogevamaa"
    assert config.county_slug("Lääne-Virumaa") == "laane-virumaa"
    assert config.county_slug("Võrumaa") == "vorumaa"


def test_page_identity_from_canonical_and_og_url():
    assert page_identity((FIX / "saved_sale.html").read_text(encoding="utf-8")) == (1, "Harjumaa")
    assert page_identity((FIX / "saved_rent.html").read_text(encoding="utf-8")) == (2, "Harjumaa")


def test_page_identity_unknown():
    assert page_identity("<html><head></head><body></body></html>") is None
    assert page_identity('<link rel="canonical" href="https://www.kv.ee/majad-muuk/harjumaa">') is None
    assert page_identity('<link rel="canonical" href="https://www.kv.ee/korterid-muuk/marsimaa">') is None


def test_import_dir_creates_run(tmp_path):
    shutil.copy(FIX / "saved_sale.html", tmp_path / "a.html")
    shutil.copy(FIX / "saved_sale.html", tmp_path / "a_duplicate.htm")
    shutil.copy(FIX / "saved_rent.html", tmp_path / "b.html")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / "junk.html").write_text("<html>tühi</html>", encoding="utf-8")
    (tmp_path / "a_files").mkdir()
    messages = []
    s = Store(":memory:")
    ok = import_dir(s, tmp_path, progress=messages.append)
    assert ok == ["Harjumaa"]
    run = s.runs()[0]
    assert run["counties_ok"] == ["Harjumaa"]
    obs = s.observations(run["id"])
    assert sorted((o["deal_type"], o["id"]) for o in obs) == [(1, 1001), (1, 1002), (2, 2001)]
    assert any("junk.html" in m for m in messages)


def test_import_county_without_rent_is_skipped(tmp_path):
    shutil.copy(FIX / "saved_sale.html", tmp_path / "a.html")
    messages = []
    s = Store(":memory:")
    assert import_dir(s, tmp_path, progress=messages.append) == []
    assert s.runs() == []
    assert any("Harjumaa" in m and "üür" in m for m in messages)
```

- [ ] **Step 3: Käivita, veendu et kukuvad läbi**

Run: `python -m pytest tests/test_importer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tootlus.importer'` (ja `county_slug` puudub)

- [ ] **Step 4: Lisa `tootlus/config.py` lõppu**

```python
_ASCII = str.maketrans({"õ": "o", "ä": "a", "ö": "o", "ü": "u", "š": "s", "ž": "z"})


def county_slug(name: str) -> str:
    """kv.ee URL-i maakonna osa, nt "Lääne-Virumaa" -> "laane-virumaa"."""
    return name.lower().translate(_ASCII)
```

- [ ] **Step 5: Kirjuta `tootlus/importer.py`**

```python
"""Brauserist salvestatud kv.ee otsingulehtede import ühe käivitusena."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from . import config
from .parser import parse_page

DEALS = {"korterid-muuk": config.DEAL_SALE, "korterid-uur": config.DEAL_RENT}
DEAL_LABELS = {config.DEAL_SALE: "müük", config.DEAL_RENT: "üür"}
_COUNTY_BY_SLUG = {config.county_slug(name): name for name in config.COUNTIES.values()}


def page_identity(html: str) -> tuple[int, str] | None:
    soup = BeautifulSoup(html, "lxml")
    url = None
    link = soup.find("link", rel="canonical")
    if link and link.get("href"):
        url = link["href"]
    else:
        meta = soup.find("meta", property="og:url")
        if meta and meta.get("content"):
            url = meta["content"]
    if not url:
        return None
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) < 2 or parts[0] not in DEALS or parts[1] not in _COUNTY_BY_SLUG:
        return None
    return DEALS[parts[0]], _COUNTY_BY_SLUG[parts[1]]


def import_dir(store, directory: Path, progress=print) -> list[str]:
    collected: dict[tuple[str, int], dict] = {}
    files = sorted(p for p in Path(directory).iterdir() if p.is_file() and p.suffix.lower() in (".html", ".htm"))
    for path in files:
        html = path.read_text(encoding="utf-8", errors="replace")
        identity = page_identity(html)
        if identity is None:
            progress(f"{path.name}: pole kv.ee korterite otsinguleht, jätan vahele")
            continue
        listings = parse_page(html)
        if not listings:
            progress(f"{path.name}: kuulutusi ei leitud, jätan vahele")
            continue
        deal, county = identity
        bucket = collected.setdefault((county, deal), {})
        for listing in listings:
            bucket[listing.id] = listing
        progress(f"{path.name}: {county} {DEAL_LABELS[deal]}, {len(listings)} kuulutust")

    counties = sorted({county for county, _ in collected})
    ok = []
    for county in counties:
        missing = [DEAL_LABELS[d] for d in (config.DEAL_SALE, config.DEAL_RENT) if (county, d) not in collected]
        if missing:
            progress(f"{county}: puudub {', '.join(missing)}, maakond jäetakse välja")
        else:
            ok.append(county)
    if not ok:
        progress("Import: ühtegi maakonda nii müügi kui üüriga ei leitud, käivitust ei looda")
        return []

    run_id = store.start_run()
    for county in ok:
        for deal in (config.DEAL_SALE, config.DEAL_RENT):
            store.save_listings(run_id, deal, county, list(collected[(county, deal)].values()))
    store.finish_run(run_id, ok, complete=len(ok) == len(config.COUNTIES))
    progress(f"Import valmis: {len(ok)} maakonda ({', '.join(ok)})")
    return ok
```

- [ ] **Step 6: Lisa `run.py`-sse `--import-dir`**

Docstringi lisa rida:
```
    python run.py --import-dir K  impordi kaustast K brauserist salvestatud kv.ee otsingulehed
```
Argumentide juurde:
```python
    parser.add_argument("--import-dir", help="kaust brauserist salvestatud kv.ee otsingulehtedega")
```
ja `try:` ploki sees asenda `if args.analyze_only:` haru nii:
```python
        if args.import_dir:
            from tootlus.importer import import_dir
            import_dir(store, Path(args.import_dir))
            results = pipeline.analyze_only(store)
        elif args.analyze_only:
            results = pipeline.analyze_only(store)
        else:
            results = pipeline.run_once(store, counties=counties)
```
ning lisa üles `from pathlib import Path`.

- [ ] **Step 7: Käivita testid**

Run: `python -m pytest tests/test_importer.py -v` → 5 passed; siis `python -m pytest -q` → kõik läbivad.

- [ ] **Step 8: Commit**

```bash
git add tootlus/config.py tootlus/importer.py run.py tests/test_importer.py tests/fixtures/saved_sale.html tests/fixtures/saved_rent.html
git commit -m "feat: brauserist salvestatud kv.ee lehtede import"
```

---

### Task 1b: Brauseri kogur (Selenium, nähtav Edge)

Kasutaja otsus (2026-10-01): lehed peab koguma programm ise. Selenium juhib nähtavat Edge'i akent: nõustub küpsistega, käib maakonna müügi- ja üürilehed läbi ja salvestab iga lehe HTML-i kausta, mille `importer.import_dir` impordib. **Piir:** Cloudflare'i kontrolli ei lahendata automaatselt ega peideta automatiseerimist (mitte undetected-chromedriver, stealth-pluginaid, CAPTCHA-teenuseid ega `navigator.webdriver` muutmist) — kui kontroll ilmub, logitakse "Lahenda kontroll brauseriaknas" ja oodatakse kuni 5 min, kuni lehel on kuulutused.

**Files:**
- Create: `tootlus/browser.py`
- Modify: `run.py` (`--browser`), `tootlus/server.py` (`serve(..., browser=False)`), `requirements.txt` (`selenium>=4.20`)
- Test: `tests/test_browser.py`

**Interfaces:**
- Consumes: `parser.parse_page`, `config.COUNTIES`, `config.county_slug`, `importer.import_dir`
- Produces: `browser.page_url(deal_type:int, county:str, start:int) -> str`; `browser.ChallengeTimeout(Exception)`; `browser.collect(driver, out_dir:Path, counties:dict[int,str], progress=print, sleep=time.sleep, clock=time.monotonic) -> int` (salvestatud failide arv); `browser.make_driver()` (päris Edge); `browser.collect_and_import(store, counties, progress=print, out_root=ROOT/"data"/"lehed") -> list[str]`.

- [ ] **Step 1: Kirjuta failivad testid `tests/test_browser.py`**

```python
import pytest

from tootlus import browser


def card(i):
    return (f'<article class="default object-type-apartment" data-object-id="{i}" data-object-url="/x-{i}">'
            f'<div class="h2"><a data-skeleton="object"><strong>Tn {i}</strong>, Kesklinn, Tallinn</a></div>'
            f'<div class="rooms">2</div><div class="area">50 m²</div><div class="price">100 000 € <small>2 000 €/m²</small></div></article>')


def page(ids, canonical="https://www.kv.ee/korterid-muuk/hiiumaa"):
    return f'<html><head><link rel="canonical" href="{canonical}"></head><body>{"".join(card(i) for i in ids)}</body></html>'


CHALLENGE = "<html><head><title>Just a moment...</title></head><body>cf challenge</body></html>"


class FakeButton:
    def __init__(self, text, log):
        self.text, self.log = text, log

    def click(self):
        self.log.append(("click", self.text))


class FakeDriver:
    """pages: url -> list of page sources returned on successive reads of page_source."""

    def __init__(self, pages, buttons=()):
        self.pages = pages
        self.current = None
        self.log = []
        self.buttons = [FakeButton(t, self.log) for t in buttons]
        self.reads = {}

    def get(self, url):
        self.log.append(("get", url))
        self.current = url

    @property
    def page_source(self):
        seq = self.pages.get(self.current, ["<html></html>"])
        n = self.reads.get(self.current, 0)
        self.reads[self.current] = n + 1
        return seq[min(n, len(seq) - 1)]

    def find_elements(self, by, value):
        return list(self.buttons)


def test_page_url():
    assert browser.page_url(1, "Lääne-Virumaa", 50) == "https://www.kv.ee/korterid-muuk/laane-virumaa?start=50"
    assert browser.page_url(2, "Harjumaa", 0) == "https://www.kv.ee/korterid-uur/harjumaa?start=0"


def test_collect_pages_until_no_new_ids(tmp_path):
    u = browser.page_url
    pages = {
        u(1, "Hiiumaa", 0): [page(range(1, 51))], u(1, "Hiiumaa", 50): [page(range(51, 61))],
        u(1, "Hiiumaa", 100): [page(range(51, 61))],
        u(2, "Hiiumaa", 0): [page(range(1, 6), "https://www.kv.ee/korterid-uur/hiiumaa")],
        u(2, "Hiiumaa", 50): [page(range(1, 6), "https://www.kv.ee/korterid-uur/hiiumaa")],
    }
    d = FakeDriver(pages, buttons=["Nõustun"])
    n = browser.collect(d, tmp_path, {2: "Hiiumaa"}, progress=lambda m: None, sleep=lambda s: None)
    assert n == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "hiiumaa-muuk-00000.html", "hiiumaa-muuk-00050.html", "hiiumaa-uur-00000.html"]
    assert ("click", "Nõustun") in d.log


def test_waits_for_challenge_then_continues(tmp_path):
    u = browser.page_url
    pages = {u(1, "Hiiumaa", 0): [CHALLENGE, CHALLENGE, page([1])], u(1, "Hiiumaa", 50): [page([1])],
             u(2, "Hiiumaa", 0): [page([2], "https://www.kv.ee/korterid-uur/hiiumaa")],
             u(2, "Hiiumaa", 50): [page([2], "https://www.kv.ee/korterid-uur/hiiumaa")]}
    msgs = []
    n = browser.collect(FakeDriver(pages), tmp_path, {2: "Hiiumaa"}, progress=msgs.append, sleep=lambda s: None)
    assert n == 2
    assert any("kontroll" in m for m in msgs)


def test_challenge_timeout(tmp_path):
    t = iter(range(0, 10000, 30))
    pages = {browser.page_url(1, "Hiiumaa", 0): [CHALLENGE]}
    with pytest.raises(browser.ChallengeTimeout):
        browser.collect(FakeDriver(pages), tmp_path, {2: "Hiiumaa"}, progress=lambda m: None,
                        sleep=lambda s: None, clock=lambda: next(t))


def test_empty_result_page_ends_county_deal(tmp_path):
    pages = {browser.page_url(1, "Hiiumaa", 0): ['<html><body><div class="results"></div><p>Kuulutusi ei leitud</p></body></html>'],
             browser.page_url(2, "Hiiumaa", 0): [page([2], "https://www.kv.ee/korterid-uur/hiiumaa")],
             browser.page_url(2, "Hiiumaa", 50): [page([2], "https://www.kv.ee/korterid-uur/hiiumaa")]}
    n = browser.collect(FakeDriver(pages), tmp_path, {2: "Hiiumaa"}, progress=lambda m: None, sleep=lambda s: None)
    assert n == 1
```

- [ ] **Step 2: Käivita, veendu et kukuvad läbi** — `python -m pytest tests/test_browser.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Lisa `requirements.txt`-i `selenium>=4.20` ja `pip install -r requirements.txt`.**

- [ ] **Step 4: Kirjuta `tootlus/browser.py`**

```python
"""kv.ee otsingulehtede kogumine nähtava Edge'i aknaga (Selenium) ja salvestamine importimiseks.

Cloudflare'i kontrolli ei lahendata automaatselt: kui see ilmub, ootab programm, kuni kasutaja selle
brauseriaknas ära teeb.
"""
from __future__ import annotations

import re
import time
from datetime import date
from pathlib import Path

from . import config
from .parser import parse_page

SITE = "https://www.kv.ee"
DEAL_PATHS = {config.DEAL_SALE: "korterid-muuk", config.DEAL_RENT: "korterid-uur"}
DEAL_LABELS = {config.DEAL_SALE: "müük", config.DEAL_RENT: "üür"}
PAGE_DELAY_S = 2.0
CHALLENGE_TIMEOUT_S = 300
POLL_S = 2.0
_CHALLENGE = re.compile(r"Just a moment|challenge-platform|cf-chl|Checking your browser", re.I)
_CONSENT = re.compile(r"^(nõustun|nõustu|luba kõik|accept all|accept|nõustun kõigiga)$", re.I)


class ChallengeTimeout(Exception):
    """Cloudflare'i kontroll ei lahenenud lubatud aja jooksul."""


def page_url(deal_type: int, county: str, start: int) -> str:
    return f"{SITE}/{DEAL_PATHS[deal_type]}/{config.county_slug(county)}?start={start}"


def _accept_cookies(driver) -> bool:
    for button in driver.find_elements("css selector", "button"):
        try:
            if _CONSENT.match((button.text or "").strip()):
                button.click()
                return True
        except Exception:  # noqa: BLE001 - nupp võis kaduda; proovime järgmist
            continue
    return False


def _wait_for_page(driver, progress, sleep, clock) -> str:
    started = clock()
    warned = False
    while True:
        html = driver.page_source
        if not _CHALLENGE.search(html):
            return html
        if not warned:
            progress("Cloudflare'i kontroll — lahenda see brauseriaknas, kogumine jätkub ise")
            warned = True
        if clock() - started > CHALLENGE_TIMEOUT_S:
            raise ChallengeTimeout("Cloudflare'i kontroll ei lahenenud 5 minutiga")
        sleep(POLL_S)


def collect(driver, out_dir: Path, counties: dict[int, str], progress=print, sleep=time.sleep,
            clock=time.monotonic) -> int:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    consent_done = False
    for county in counties.values():
        for deal in (config.DEAL_SALE, config.DEAL_RENT):
            seen: set[int] = set()
            for page in range(config.MAX_PAGES):
                start = page * config.PAGE_SIZE
                driver.get(page_url(deal, county, start))
                html = _wait_for_page(driver, progress, sleep, clock)
                if not consent_done:
                    consent_done = _accept_cookies(driver)
                    if consent_done:
                        html = driver.page_source
                ids = {l.id for l in parse_page(html)}
                if not ids - seen:
                    break
                seen |= ids
                name = f"{config.county_slug(county)}-{DEAL_PATHS[deal].split('-')[1]}-{start:05d}.html"
                (out_dir / name).write_text(html, encoding="utf-8")
                saved += 1
                progress(f"{county} {DEAL_LABELS[deal]}: leht {page + 1}, {len(seen)} kuulutust")
                sleep(PAGE_DELAY_S)
    return saved


def make_driver():
    from selenium import webdriver
    return webdriver.Edge()


def collect_and_import(store, counties: dict[int, str], progress=print, out_root: Path | None = None) -> list[str]:
    from .importer import import_dir
    from .pipeline import ROOT
    out_dir = Path(out_root or ROOT / "data" / "lehed") / date.today().isoformat()
    driver = make_driver()
    try:
        collect(driver, out_dir, counties, progress=progress)
    finally:
        driver.quit()
    return import_dir(store, out_dir, progress=progress)
```

Märkus: failinimes `korterid-muuk` → `muuk`, `korterid-uur` → `uur`.

- [ ] **Step 5: Käivita testid** — `python -m pytest tests/test_browser.py -v` → 5 passed.

- [ ] **Step 6: CLI ja server**

`run.py`: docstringi rida `python run.py --browser       kogu kv.ee lehed nähtava Edge'i aknaga (Selenium)`; argument `parser.add_argument("--browser", action="store_true")`; `--serve` haru: `serve(args.port, counties, browser=args.browser)`; `try:` plokis enne `elif args.analyze_only` lisa:
```python
        elif args.browser:
            from tootlus.browser import collect_and_import
            collect_and_import(store, counties)
            results = pipeline.analyze_only(store)
```
`tootlus/server.py` `serve(port, counties, browser=False)`: runneris kui `browser`, siis `collect_and_import(store, counties, progress=progress)` + `pipeline.analyze_only(store)` (Task 4 lisab hiljem `progress` parameetri; siis anna see edasi), muidu senine `pipeline.run_once`.

- [ ] **Step 7: Täielik testikomplekt** — `python -m pytest -q` → kõik läbivad. Ära käivita päris `--browser` kogumist selles sammus (see on Task 6).

- [ ] **Step 8: Commit**

```bash
git add requirements.txt tootlus/browser.py run.py tootlus/server.py tests/test_browser.py
git commit -m "feat: kv.ee lehtede kogumine nähtava Edge'i aknaga (Selenium)"
```

---

### Task 2: Geokodeerija (`geocode.py`)

**Files:**
- Create: `tootlus/geocode.py`
- Test: `tests/test_geocode.py`

**Interfaces:**
- Produces: `geocode.Geo(lat:float, lon:float, asum:str|None)` (frozen dataclass); `geocode.street_query(address:str, location:str) -> str|None`; `geocode.Geocoder(conn: sqlite3.Connection, fetch=fetch_json, sleep=time.sleep)` meetoditega `lookup(query:str) -> Geo|None` (ainult vahemälust), `geocode_missing(queries:Iterable[str], progress=print) -> int` (mitu uut päringut tehti); `geocode.fetch_json(url:str) -> dict`.

- [ ] **Step 1: Kirjuta failivad testid `tests/test_geocode.py`**

```python
import sqlite3
import urllib.error

from tootlus.geocode import Geo, Geocoder, street_query

FOUND = {"addresses": [{"viitepunkt_b": "59.404690", "viitepunkt_l": "24.726348", "asum": "Tondi asum"}]}


def test_street_query():
    assert street_query("Sammu tn 10-56, Kristiine City, Kristiine, Tallinn", "Kristiine City, Kristiine, Tallinn") == "Sammu tn 10, Tallinn"
    assert street_query("Seebi 24a-8, Kristiine, Tallinn", "Kristiine, Tallinn") == "Seebi 24a, Tallinn"
    assert street_query("Lennuki tn, Kesklinn, Tallinn", "Kesklinn, Tallinn") == "Lennuki tn, Tallinn"
    assert street_query("Narva", "Narva") is None
    assert street_query("", "") is None


def test_geocode_and_cache():
    calls = []

    def fetch(url):
        calls.append(url)
        return FOUND

    g = Geocoder(sqlite3.connect(":memory:"), fetch=fetch, sleep=lambda s: None)
    assert g.lookup("Sammu tn 10, Tallinn") is None
    assert g.geocode_missing(["Sammu tn 10, Tallinn", "Sammu tn 10, Tallinn"], progress=lambda m: None) == 1
    assert g.lookup("Sammu tn 10, Tallinn") == Geo(59.40469, 24.726348, "Tondi")
    assert "address=Sammu%20tn%2010%2C%20Tallinn" in calls[0]
    assert g.geocode_missing(["Sammu tn 10, Tallinn"], progress=lambda m: None) == 0
    assert len(calls) == 1


def test_not_found_is_cached():
    calls = []
    g = Geocoder(sqlite3.connect(":memory:"), fetch=lambda url: calls.append(url) or {"addresses": []}, sleep=lambda s: None)
    g.geocode_missing(["Olematu 1, Tallinn"], progress=lambda m: None)
    g.geocode_missing(["Olematu 1, Tallinn"], progress=lambda m: None)
    assert g.lookup("Olematu 1, Tallinn") is None
    assert len(calls) == 1


def test_network_error_is_not_cached():
    def boom(url):
        raise urllib.error.URLError("võrk maas")

    conn = sqlite3.connect(":memory:")
    g = Geocoder(conn, fetch=boom, sleep=lambda s: None)
    assert g.geocode_missing(["Sammu tn 10, Tallinn"], progress=lambda m: None) == 1
    g2 = Geocoder(conn, fetch=lambda url: FOUND, sleep=lambda s: None)
    g2.geocode_missing(["Sammu tn 10, Tallinn"], progress=lambda m: None)
    assert g2.lookup("Sammu tn 10, Tallinn") == Geo(59.40469, 24.726348, "Tondi")


def test_missing_asum():
    g = Geocoder(sqlite3.connect(":memory:"),
                 fetch=lambda url: {"addresses": [{"viitepunkt_b": "59.4", "viitepunkt_l": "24.7", "asum": ""}]},
                 sleep=lambda s: None)
    g.geocode_missing(["X 1, Tallinn"], progress=lambda m: None)
    assert g.lookup("X 1, Tallinn") == Geo(59.4, 24.7, None)
```

- [ ] **Step 2: Käivita, veendu et kukuvad läbi**

Run: `python -m pytest tests/test_geocode.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tootlus.geocode'`

- [ ] **Step 3: Kirjuta `tootlus/geocode.py`**

```python
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
                self._store(query, (data or {}).get("addresses") or [])
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
            asum = (first.get("asum") or "").removesuffix(" asum").strip() or None
            self.conn.execute("INSERT OR REPLACE INTO geocodes VALUES (?, ?, ?, ?, 1, ?)", (query, lat, lon, asum, now))
        self.conn.commit()
```

- [ ] **Step 4: Käivita testid**

Run: `python -m pytest tests/test_geocode.py -v` → 5 passed; `python -m pytest -q` → kõik läbivad.

- [ ] **Step 5: Commit**

```bash
git add tootlus/geocode.py tests/test_geocode.py
git commit -m "feat: In-ADS geokodeerija vahemäluga"
```

---

### Task 3: Regressioonimudeli tuum (`model.py` I osa)

**Files:**
- Create: `tootlus/model.py`
- Modify: `requirements.txt` (lisa `numpy>=2.0`)
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes: `analyze.room_group`
- Produces (kõik `tootlus/model.py`):
  - `VABADUSE = (59.4339, 24.7445)`; `KNOTS = (2.0, 5.0, 8.0)`; `EFFECT_DISTANCES = (1, 3, 6)`; `UNDERVALUED = -0.15`; `MIN_SALE = 50`; `MIN_RENT = 30`; `MIN_SUBDISTRICT = 5`
  - `haversine_km(lat1, lon1, lat2, lon2)` (numpy-vektoriseeritud; skalaarid ka)
  - `features(rows:list[dict], dist:np.ndarray) -> np.ndarray` — rea dict võtmed: `rooms, area_m2, build_year, condition, floor`
  - `find_center(rows:list[dict]) -> tuple[float, float]`
  - `fit_run(sale:list[dict], rent:list[dict]) -> dict | None` — rea dict võtmed lisaks: `lat, lon, price, price_per_m2, id, url, address, asum`; tagastab `{"center": {"lat","lon"}, "center_offset_m": int, "effects": {"sale": {"1","3","6"}, "rent": {...}}, "r2": {"sale","rent"}, "n": {"sale","rent"}, "curve": [...], "subdistricts": [...], "listings": [...]}` (vt spec model.json; `listings` = ainult hälve ≤ −15%, sorditud hälbe järgi kasvavalt) või `None` kui alla miinimumi.

- [ ] **Step 1: Kirjuta failivad testid `tests/test_model.py`**

```python
import math

import numpy as np
import pytest

from tootlus import model

CENTER = (59.4370, 24.7450)
KM_LAT = 1 / 111.32
KM_LON = 1 / (111.32 * math.cos(math.radians(59.43)))


def synth(n, base, slope, seed, kind, undervalued_id=None):
    rng = np.random.default_rng(seed)
    rows = []
    conditions = ["heas korras", "uus", "renoveeritud", "keskmises seisukorras", None]
    for i in range(n):
        r_km = rng.uniform(0.2, 9.0)
        ang = rng.uniform(0, 2 * math.pi)
        lat = CENTER[0] + r_km * math.sin(ang) * KM_LAT
        lon = CENTER[1] + r_km * math.cos(ang) * KM_LON
        rooms = int(rng.integers(1, 5))
        area = float(rng.uniform(25, 110))
        d = float(model.haversine_km(lat, lon, *CENTER))
        log_m2 = math.log(base) + slope * d + 0.08 * (rooms == 3) + rng.normal(0, 0.05)
        if undervalued_id is not None and i == 0:
            log_m2 += math.log(0.7)
        m2 = math.exp(log_m2)
        rows.append({
            "id": (undervalued_id if (undervalued_id is not None and i == 0) else seed * 100000 + i),
            "url": f"https://www.kv.ee/x-{i}", "address": f"Tn {i}, Tallinn",
            "lat": lat, "lon": lon, "rooms": rooms, "area_m2": area,
            "price": m2 * area, "price_per_m2": m2,
            "build_year": int(rng.choice([1930, 1970, 2000, 2020])), "condition": conditions[i % 5],
            "floor": int(rng.integers(1, 9)), "asum": f"Asum{int(r_km)}",
        })
    return rows


def test_haversine():
    assert model.haversine_km(59.4339, 24.7445, 59.4339, 24.7445) == pytest.approx(0)
    assert model.haversine_km(59.0, 24.0, 59.1, 24.0) == pytest.approx(11.12, abs=0.02)


def test_finds_center_and_effects():
    sale = synth(1500, 3500, -0.08, seed=1, kind="sale", undervalued_id=777)
    rent = synth(600, 16, -0.05, seed=2, kind="rent")
    res = model.fit_run(sale, rent)
    c = res["center"]
    assert model.haversine_km(c["lat"], c["lon"], *CENTER) * 1000 < 100
    expected_sale = math.exp(-0.08 * 0.1) - 1
    expected_rent = math.exp(-0.05 * 0.1) - 1
    for d in ("1", "3", "6"):
        assert res["effects"]["sale"][d] == pytest.approx(expected_sale, rel=0.10)
        assert res["effects"]["rent"][d] == pytest.approx(expected_rent, rel=0.10)
    assert res["r2"]["sale"] > 0.8
    assert res["n"] == {"sale": 1500, "rent": 600}
    ids = [l["id"] for l in res["listings"]]
    assert ids[0] == 777
    assert all(l["residual"] <= -0.15 for l in res["listings"])
    first = res["listings"][0]
    assert first["residual"] == pytest.approx(-0.3, abs=0.06)
    assert first["yield"] == pytest.approx(first["rent_estimate"] * 12 / first["price"], abs=1e-4)
    expected_offset = model.haversine_km(c["lat"], c["lon"], *model.VABADUSE) * 1000
    assert res["center_offset_m"] == round(expected_offset)


def test_curve_and_subdistricts():
    res = model.fit_run(synth(800, 3500, -0.08, seed=3, kind="sale"), synth(300, 16, -0.05, seed=4, kind="rent"))
    curve = res["curve"]
    assert curve[0]["d"] == 0 and curve[-1]["d"] == 15
    assert len(curve) == 61
    assert curve[0]["sale_m2"] > curve[20]["sale_m2"] > curve[40]["sale_m2"]
    assert curve[0]["rent_m2"] > curve[40]["rent_m2"]
    subs = res["subdistricts"]
    assert subs and all(s["n"] >= 5 for s in subs)
    assert {"name", "lat", "lon", "n", "residual_median"} <= set(subs[0])


def test_rare_categories_do_not_break_fit():
    sale = synth(200, 3500, -0.08, seed=5, kind="sale")
    rent = synth(100, 16, -0.05, seed=6, kind="rent")
    for r in sale + rent:
        r["condition"] = "heas korras"
        r["build_year"] = None
        r["floor"] = None
    res = model.fit_run(sale, rent)
    assert res is not None
    assert all(math.isfinite(v) for v in res["effects"]["sale"].values())


def test_too_few_rows():
    assert model.fit_run(synth(49, 3500, -0.08, seed=7, kind="sale"), synth(100, 16, -0.05, seed=8, kind="rent")) is None
    assert model.fit_run(synth(100, 3500, -0.08, seed=9, kind="sale"), synth(29, 16, -0.05, seed=10, kind="rent")) is None
```

- [ ] **Step 2: Käivita, veendu et kukuvad läbi**

Run: `python -m pytest tests/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tootlus.model'`

- [ ] **Step 3: Lisa `requirements.txt`-i rida `numpy>=2.0`**

- [ ] **Step 4: Kirjuta `tootlus/model.py`**

```python
"""Tallinna hinna-kauguse mudel: keskpunkt, kauguse mõju ja alahinnatud objektid."""
from __future__ import annotations

import math
from statistics import median

import numpy as np

from .analyze import room_group

VABADUSE = (59.4339, 24.7445)
KNOTS = (2.0, 5.0, 8.0)
EFFECT_DISTANCES = (1, 3, 6)
UNDERVALUED = -0.15
MIN_SALE = 50
MIN_RENT = 30
MIN_SUBDISTRICT = 5
LAT_RANGE = (59.35, 59.50)
LON_RANGE = (24.55, 24.95)
TYPICAL = {"rooms": 2, "area_m2": 50.0, "build_year": 2000, "condition": "heas korras", "floor": 3}

ROOM_LEVELS = ("2", "3", "4+")                       # baas "1"
YEAR_LEVELS = ("<1940", "1940-1990", ">2010", "?")   # baas "1991-2010"
CONDITION_GROUPS = {
    "uus": "new", "valmis": "new",
    "renoveeritud": "renovated", "san. remont tehtud": "renovated",
    "heas korras": "good",
    "keskmises seisukorras": "average",
    "vajab san. remonti": "needs_work", "vajab renoveerimist": "needs_work", "alustamata ehitus": "needs_work",
}
CONDITION_LEVELS = ("new", "renovated", "average", "needs_work", "?")  # baas "good"


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, dtype=float)) for v in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def _year_group(year) -> str:
    if year is None:
        return "?"
    if year < 1940:
        return "<1940"
    if year <= 1990:
        return "1940-1990"
    if year <= 2010:
        return "1991-2010"
    return ">2010"


def _distance_columns(d: np.ndarray) -> list[np.ndarray]:
    return [d] + [np.maximum(d - k, 0.0) for k in KNOTS]


def features(rows: list[dict], dist: np.ndarray) -> np.ndarray:
    return _with_distance(_static_columns(rows), dist)


def _with_distance(static: np.ndarray, dist) -> np.ndarray:
    d = np.asarray(dist, dtype=float)
    return np.column_stack([np.ones(len(d))] + _distance_columns(d) + [static])


def _static_columns(rows: list[dict]) -> np.ndarray:
    """Kaugusest sõltumatud veerud — arvutatakse üks kord, keskpunkti otsingus taaskasutatakse."""
    cols = []
    rooms = [room_group(r["rooms"]) for r in rows]
    cols += [np.array([g == level for g in rooms], dtype=float) for level in ROOM_LEVELS]
    cols.append(np.log(np.array([r["area_m2"] for r in rows], dtype=float)))
    years = [_year_group(r.get("build_year")) for r in rows]
    cols += [np.array([y == level for y in years], dtype=float) for level in YEAR_LEVELS]
    conds = [CONDITION_GROUPS.get(r.get("condition"), "?") for r in rows]
    cols += [np.array([c == level for c in conds], dtype=float) for level in CONDITION_LEVELS]
    floors = [r.get("floor") for r in rows]
    cols.append(np.array([f == 1 for f in floors], dtype=float))
    cols.append(np.array([f is None for f in floors], dtype=float))
    return np.column_stack(cols)


def _fit(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float, float]:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    sse = float(resid @ resid)
    sst = float(((y - y.mean()) ** 2).sum())
    return beta, sse, (1 - sse / sst) if sst > 0 else 0.0


def _coords(rows):
    return np.array([r["lat"] for r in rows]), np.array([r["lon"] for r in rows])


def _grid(lo, hi, step):
    return np.arange(lo, hi + step / 2, step)


def find_center(rows: list[dict]) -> tuple[float, float]:
    y = np.log(np.array([r["price_per_m2"] for r in rows], dtype=float))
    lats, lons = _coords(rows)
    static = _static_columns(rows)

    def _sse_at(lat, lon) -> float:
        return _fit(_with_distance(static, haversine_km(lats, lons, lat, lon)), y)[1]

    km_lat = 1 / 111.32
    km_lon = 1 / (111.32 * math.cos(math.radians(sum(LAT_RANGE) / 2)))

    def search(lat_values, lon_values):
        best = (math.inf, None, None)
        for lat in lat_values:
            for lon in lon_values:
                sse = _sse_at(lat, lon)
                if sse < best[0]:
                    best = (sse, float(lat), float(lon))
        return best[1], best[2]

    lat, lon = search(_grid(*LAT_RANGE, 0.25 * km_lat), _grid(*LON_RANGE, 0.25 * km_lon))
    return search(_grid(lat - 0.3 * km_lat, lat + 0.3 * km_lat, 0.05 * km_lat),
                  _grid(lon - 0.3 * km_lon, lon + 0.3 * km_lon, 0.05 * km_lon))


def _slope(beta: np.ndarray, d: float) -> float:
    # beta[1] = kalle 0 km-st; beta[2..4] lisanduvad pärast murdepunkte
    return float(beta[1] + sum(beta[2 + i] for i, k in enumerate(KNOTS) if d > k))


def _effects(beta: np.ndarray) -> dict[str, float]:
    return {str(d): round(math.exp(_slope(beta, d) * 0.1) - 1, 5) for d in EFFECT_DISTANCES}


def _predict_m2(rows, beta, lat, lon) -> np.ndarray:
    lats, lons = _coords(rows)
    return np.exp(features(rows, haversine_km(lats, lons, lat, lon)) @ beta)


def fit_run(sale: list[dict], rent: list[dict]) -> dict | None:
    if len(sale) < MIN_SALE or len(rent) < MIN_RENT:
        return None
    lat, lon = find_center(sale)

    def fit_for(rows):
        lats, lons = _coords(rows)
        X = features(rows, haversine_km(lats, lons, lat, lon))
        y = np.log(np.array([r["price_per_m2"] for r in rows], dtype=float))
        return _fit(X, y)

    beta_s, _, r2_s = fit_for(sale)
    beta_r, _, r2_r = fit_for(rent)

    typical = [dict(TYPICAL) for _ in range(61)]
    dists = np.arange(61) * 0.25
    tx = features(typical, dists)
    curve = [{"d": round(float(d), 2), "sale_m2": round(float(s), 1), "rent_m2": round(float(r), 2)}
             for d, s, r in zip(dists, np.exp(tx @ beta_s), np.exp(tx @ beta_r))]

    pred_sale_m2 = _predict_m2(sale, beta_s, lat, lon)
    pred_rent_m2 = _predict_m2(sale, beta_r, lat, lon)
    scored = []
    for row, ps, pr in zip(sale, pred_sale_m2, pred_rent_m2):
        predicted_price = float(ps) * row["area_m2"]
        rent_est = float(pr) * row["area_m2"]
        scored.append({
            "id": row["id"], "url": row["url"], "address": row["address"],
            "lat": round(row["lat"], 6), "lon": round(row["lon"], 6),
            "rooms": row["rooms"], "area_m2": row["area_m2"], "price": row["price"],
            "predicted_price": round(predicted_price), "residual": round(row["price"] / predicted_price - 1, 4),
            "rent_estimate": round(rent_est, 2), "yield": round(rent_est * 12 / row["price"], 4),
            "subdistrict": row.get("asum"),
        })

    by_asum: dict[str, list[dict]] = {}
    for s in scored:
        if s["subdistrict"]:
            by_asum.setdefault(s["subdistrict"], []).append(s)
    subdistricts = sorted(
        ({"name": name, "lat": round(float(np.mean([x["lat"] for x in xs])), 6),
          "lon": round(float(np.mean([x["lon"] for x in xs])), 6), "n": len(xs),
          "residual_median": round(median(x["residual"] for x in xs), 4)}
         for name, xs in by_asum.items() if len(xs) >= MIN_SUBDISTRICT),
        key=lambda x: x["residual_median"],
    )

    listings = sorted((s for s in scored if s["residual"] <= UNDERVALUED), key=lambda s: s["residual"])
    return {
        "center": {"lat": round(lat, 6), "lon": round(lon, 6)},
        "center_offset_m": round(float(haversine_km(lat, lon, *VABADUSE)) * 1000),
        "effects": {"sale": _effects(beta_s), "rent": _effects(beta_r)},
        "r2": {"sale": round(r2_s, 3), "rent": round(r2_r, 3)},
        "n": {"sale": len(sale), "rent": len(rent)},
        "curve": curve, "subdistricts": subdistricts, "listings": listings,
    }
```

Märkus: `test_finds_center_and_effects` kasutab `res["center_offset_m"] == round(...)`, mis vastab koodi `round(float(...) * 1000)` arvutusele (sama ümardus mõlemal pool, sest testis arvutatakse samast ümardatud keskpunktist — kui ümardatud ja ümardamata keskpunkti erinevus annab 1 m erinevuse, muuda testi `abs=1` võrdluseks ja märgi see raportis).

- [ ] **Step 5: Käivita testid**

Run: `python -m pytest tests/test_model.py -v` (võib võtta kuni ~30 s keskpunkti otsingu tõttu) → 5 passed. Kui `test_finds_center_and_effects` võtab üle 60 s, raporteeri aeg (DONE_WITH_CONCERNS), ära muuda võrgu samme.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt tootlus/model.py tests/test_model.py
git commit -m "feat: hinna-kauguse regressioon ja keskpunkti otsing"
```

---

### Task 4: Mudel andmebaasist, pipeline ja CLI

**Files:**
- Modify: `tootlus/analyze.py` (`_clean` → `clean`), `tootlus/store.py` (`listing_attrs`), `tootlus/model.py` (lisa `queries`, `compute`, `write`), `tootlus/pipeline.py`, `tests/test_pipeline.py`
- Test: `tests/test_model.py` (lisa), `tests/test_store.py` (lisa), `tests/test_pipeline.py` (muuda)

**Interfaces:**
- Consumes: `Store.runs/observations`, `regions.parse`, `geocode.street_query`, `geocode.Geocoder.lookup/geocode_missing`, `model.fit_run`
- Produces: `analyze.clean(rows) -> list[dict]` (endine `_clean`); `Store.listing_attrs() -> dict[tuple[int,int], dict]` võtmega `(id, deal_type)` ja väärtusega `{"floor","build_year","condition"}`; `model.queries(store) -> set[str]`; `model.compute(store, geocoder, generated_at:str|None=None) -> dict` (model.json struktuur, spec §3); `model.write(result:dict, path:Path)`; `pipeline.MODEL_PATH`; `pipeline.analyze_only(store, results_path=RESULTS_PATH, model_path=MODEL_PATH, geocoder=None, progress=print) -> dict`; `pipeline.run_once(..., model_path=MODEL_PATH, geocoder=None)`.

- [ ] **Step 1: Nimeta `analyze._clean` ümber `clean`-iks** (definitsioon ja ainus kasutuskoht `compute`-is). Käivita `python -m pytest tests/test_analyze.py -q` → kõik läbivad.

- [ ] **Step 2: Kirjuta failiv test `tests/test_store.py` lõppu**

```python
def test_listing_attrs():
    s = Store(":memory:")
    r = s.start_run()
    s.save_listings(r, 1, "Harjumaa", [L(1, 100000)])
    s.save_listings(r, 2, "Harjumaa", [L(1, 500)])
    attrs = s.listing_attrs()
    assert attrs[(1, 1)] == {"floor": 1, "build_year": 2000, "condition": "uus"}
    assert set(attrs) == {(1, 1), (1, 2)}
```

- [ ] **Step 3: Lisa `Store`-i meetod**

```python
    def listing_attrs(self) -> dict[tuple[int, int], dict]:
        rows = self.conn.execute("SELECT id, deal_type, floor, build_year, condition FROM listings").fetchall()
        return {(r["id"], r["deal_type"]): {"floor": r["floor"], "build_year": r["build_year"],
                                            "condition": r["condition"]} for r in rows}
```

Run: `python -m pytest tests/test_store.py -q` → kõik läbivad.

- [ ] **Step 4: Kirjuta failivad testid `tests/test_model.py` lõppu**

```python
import json
import sqlite3

from tootlus.geocode import Geocoder
from tootlus.parser import Listing
from tootlus.store import Store


def _store_with(sale_rows, rent_rows, other_city=0):
    s = Store(":memory:")
    r = s.start_run("2026-10-01T00:00:00")
    def to_listing(row, i):
        q = f"Tn {i}"
        return Listing(row["id"], row["url"], f"{q}, Kesklinn, Tallinn", "Kesklinn, Tallinn", row["rooms"],
                       round(row["area_m2"], 1), round(row["price"]), row["floor"], row["build_year"], row["condition"])
    sale = [to_listing(row, i) for i, row in enumerate(sale_rows)]
    rent = [to_listing(row, 10000 + i) for i, row in enumerate(rent_rows)]
    extra = [Listing(900000 + i, "u", f"Tn {i}, Narva", "Narva", 2, 50.0, 30000, 1, 1970, None) for i in range(other_city)]
    s.save_listings(r, 1, "Harjumaa", sale + extra)
    s.save_listings(r, 2, "Harjumaa", rent)
    s.finish_run(r, ["Harjumaa"], True)
    coords = {f"Tn {i}, Tallinn": row for i, row in enumerate(sale_rows)}
    coords.update({f"Tn {10000 + i}, Tallinn": row for i, row in enumerate(rent_rows)})
    def fetch(url):
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(url).query)["address"][0]
        row = coords.get(q)
        if row is None:
            return {"addresses": []}
        return {"addresses": [{"viitepunkt_b": str(row["lat"]), "viitepunkt_l": str(row["lon"]), "asum": row["asum"] + " asum"}]}
    g = Geocoder(s.conn, fetch=fetch, sleep=lambda x: None)
    return s, g


def test_compute_from_store(tmp_path):
    s, g = _store_with(synth(300, 3500, -0.08, seed=11, kind="sale"), synth(120, 16, -0.05, seed=12, kind="rent"), other_city=3)
    qs = model.queries(s)
    assert "Tn 0, Tallinn" in qs and not any("Narva" in q for q in qs)
    g.geocode_missing(qs, progress=lambda m: None)
    res = model.compute(s, g, generated_at="t")
    assert res["generated_at"] == "t"
    assert len(res["runs"]) == 1
    run = res["runs"][0]
    assert run["n"] == {"sale": 300, "rent": 120, "not_geocoded": 0}
    assert set(run) >= {"run_id", "started_at", "center", "center_offset_m", "effects", "r2", "n"}
    assert res["median"]["effects"]["sale"]["3"] == run["effects"]["sale"]["3"]
    assert res["curve"] and res["subdistricts"]
    out = tmp_path / "data" / "model.json"
    model.write(res, out)
    assert json.loads(out.read_text(encoding="utf-8"))["generated_at"] == "t"


def test_compute_too_little_data():
    s, g = _store_with(synth(10, 3500, -0.08, seed=13, kind="sale"), synth(10, 16, -0.05, seed=14, kind="rent"))
    g.geocode_missing(model.queries(s), progress=lambda m: None)
    res = model.compute(s, g)
    assert res["runs"] == [] and res["median"] is None
    assert res["curve"] == [] and res["subdistricts"] == [] and res["listings"] == []


def test_compute_counts_not_geocoded():
    sale = synth(300, 3500, -0.08, seed=15, kind="sale")
    s, g = _store_with(sale, synth(120, 16, -0.05, seed=16, kind="rent"))
    g.geocode_missing([q for q in model.queries(s) if q != "Tn 0, Tallinn"], progress=lambda m: None)
    res = model.compute(s, g)
    assert res["runs"][0]["n"]["not_geocoded"] == 1
    assert res["runs"][0]["n"]["sale"] == 299
```

- [ ] **Step 5: Lisa `tootlus/model.py` lõppu**

```python
import json
from datetime import datetime
from pathlib import Path

from . import analyze, regions
from .geocode import street_query


def _tallinn_rows(store, run_id: int) -> list[dict]:
    rows = analyze.clean(store.observations(run_id))
    return [r for r in rows if regions.parse(r["location"] or "").city == "Tallinn"]


def queries(store) -> set[str]:
    out = set()
    for run in store.runs():
        for r in _tallinn_rows(store, run["id"]):
            q = street_query(r["address"] or "", r["location"] or "")
            if q:
                out.add(q)
    return out


def compute(store, geocoder, generated_at: str | None = None) -> dict:
    attrs = store.listing_attrs()
    run_results = []
    for run in store.runs():
        sale, rent, missing = [], [], 0
        for r in _tallinn_rows(store, run["id"]):
            q = street_query(r["address"] or "", r["location"] or "")
            geo = geocoder.lookup(q) if q else None
            if geo is None:
                missing += 1
                continue
            row = dict(r, lat=geo.lat, lon=geo.lon,
                       asum=geo.asum or regions.parse(r["location"] or "").subdistrict,
                       **attrs.get((r["id"], r["deal_type"]), {}))
            (sale if r["deal_type"] == 1 else rent).append(row)
        fitted = fit_run(sale, rent)
        if fitted is not None:
            fitted["n"]["not_geocoded"] = missing
            run_results.append((run, fitted))

    summaries = [{"run_id": run["id"], "started_at": run["started_at"],
                  **{k: f[k] for k in ("center", "center_offset_m", "effects", "r2", "n")}}
                 for run, f in run_results]
    med = None
    if summaries:
        med = {
            "center": {k: round(median(s["center"][k] for s in summaries), 6) for k in ("lat", "lon")},
            "effects": {deal: {d: round(median(s["effects"][deal][d] for s in summaries), 5)
                               for d in summaries[0]["effects"][deal]} for deal in ("sale", "rent")},
        }
    latest = run_results[-1][1] if run_results else {"curve": [], "subdistricts": [], "listings": []}
    return {
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
        "runs": summaries, "median": med,
        "curve": latest["curve"], "subdistricts": latest["subdistricts"], "listings": latest["listings"],
    }


def write(result: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
```

(Liiguta uued importid faili algusesse teiste importide juurde; `analyze`-st impordi moodul, mitte ainult `room_group`, nt `from . import analyze, regions` ja `room_group = analyze.room_group` või kasuta `analyze.room_group` otse — vali üks ja hoia järjekindlalt.)

Run: `python -m pytest tests/test_model.py -v` → 8 passed.

- [ ] **Step 6: Uuenda `tootlus/pipeline.py`**

```python
from . import analyze, config, geocode, model, scraper

MODEL_PATH = ROOT / "docs" / "data" / "model.json"


def run_once(store, counties=config.COUNTIES, scrape=scraper.scrape_county, progress=print,
             results_path=RESULTS_PATH, model_path=MODEL_PATH, geocoder=None) -> dict:
    ...  # olemasolev kood muutmata, viimane rida:
    return analyze_only(store, results_path, model_path, geocoder, progress)


def analyze_only(store, results_path=RESULTS_PATH, model_path=MODEL_PATH, geocoder=None, progress=print) -> dict:
    results = analyze.compute(store)
    analyze.write_results(results, results_path)
    geocoder = geocoder or geocode.Geocoder(store.conn)
    new = geocoder.geocode_missing(model.queries(store), progress=progress)
    if new:
        progress(f"Geokodeerimine: {new} uut aadressi")
    model.write(model.compute(store, geocoder), model_path)
    return results
```

- [ ] **Step 7: Uuenda `tests/test_pipeline.py`** — mõlemad `run_once` testid peavad andma `model_path=tmp_path / "model.json"` ja süstitud geokodeerija (testid ei tohi võrku minna):

```python
from tootlus.geocode import Geocoder

def no_geo(store):
    return Geocoder(store.conn, fetch=lambda url: {"addresses": []}, sleep=lambda s: None)
```

ja kutsetes `..., model_path=tmp_path / "model.json", geocoder=no_geo(s)`. Lisa test:

```python
def test_analyze_only_writes_model_json(tmp_path):
    s = Store(":memory:")
    pipeline.analyze_only(s, tmp_path / "r.json", tmp_path / "m.json", no_geo(s), progress=lambda m: None)
    data = json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))
    assert data["runs"] == [] and data["median"] is None
```

- [ ] **Step 8: Käivita kogu testikomplekt**

Run: `python -m pytest -q` → kõik läbivad.

- [ ] **Step 9: Commit**

```bash
git add tootlus/analyze.py tootlus/store.py tootlus/model.py tootlus/pipeline.py tests/test_model.py tests/test_store.py tests/test_pipeline.py
git commit -m "feat: kauguse mudel andmebaasist ja model.json pipeline'is"
```

---

### Task 5: Leht "Kaugus keskusest" (`docs/mudel.html`)

**Files:**
- Create: `docs/mudel.html`, `docs/mudel.js`
- Modify: `docs/index.html` (navigatsioon), `docs/style.css` (navigatsioon + mudeli lehe stiilid)

**Interfaces:**
- Consumes: `docs/data/model.json` (Task 4 struktuur).

- [ ] **Step 1: Laadi `impeccable` (shape) ja `dataviz` oskused.** Sisend: sama disainisüsteem nagu `docs/style.css` (tokenid `--bg --surface --ink --muted --line --accent --thin --head-bg`, IBM Plex Sans, tume režiim). Leht: kaart, kaks väikest graafikut (müük €/m² vs km; üür €/m² vs km), kaks tabelit. Diverging värviskaala asumitele (alahinnatud ↔ ülehinnatud) peab töötama heledas ja tumedas režiimis ning olema värvipimedale loetav; dataviz-oskuse värvivalidaatoriga kontrolli. Allolev kood on funktsionaalne alus; disainiotsused muudavad CSS-i/HTML-i struktuuri ja värve, mitte andmeloogikat.

- [ ] **Step 2: Lisa navigatsioon** — `docs/index.html` päisesse `<h1>` kõrvale ja `docs/mudel.html`-i samamoodi:

```html
<nav class="site-nav" aria-label="Lehed">
  <a href="index.html" aria-current="page">Tootlus</a>
  <a href="mudel.html">Kaugus keskusest</a>
</nav>
```
(`aria-current="page"` aktiivsel lehel.)

- [ ] **Step 3: Kirjuta `docs/mudel.html`**

```html
<!doctype html>
<html lang="et">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>Kaugus keskusest</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="top">
    <div>
      <nav class="site-nav" aria-label="Lehed">
        <a href="index.html">Tootlus</a>
        <a href="mudel.html" aria-current="page">Kaugus keskusest</a>
      </nav>
      <h1>Kaugus keskusest</h1>
      <p class="sub" id="meta">Laen mudelit…</p>
    </div>
  </header>

  <main id="content" hidden>
    <section class="stats" id="stats" aria-label="Kauguse mõju"></section>
    <section class="map-wrap"><div id="map" role="region" aria-label="Tallinna kaart"></div>
      <p class="legend" id="legend"></p></section>
    <section class="charts" aria-label="Hind kauguse järgi">
      <figure><figcaption>Müük €/m² (tüüpkorter)</figcaption><svg id="chart-sale" viewBox="0 0 480 220" role="img"></svg></figure>
      <figure><figcaption>Üür €/m² kuus (tüüpkorter)</figcaption><svg id="chart-rent" viewBox="0 0 480 220" role="img"></svg></figure>
    </section>
    <h2>Alahinnatud asumid</h2>
    <div class="table-wrap"><table id="t-sub"><thead></thead><tbody></tbody></table></div>
    <h2>Alahinnatud kuulutused</h2>
    <section class="filters"><label>Toad
      <select id="rooms"><option value="all">Kõik</option><option value="1">1</option><option value="2">2</option>
        <option value="3">3</option><option value="4+">4+</option></select></label></section>
    <div class="table-wrap"><table id="t-list"><thead></thead><tbody></tbody></table></div>
  </main>
  <p class="empty" id="empty" hidden>Mudeli jaoks pole veel piisavalt Tallinna andmeid (vaja vähemalt 50 müügi- ja 30 üürikuulutust koordinaatidega). Käivita <code>python run.py</code> või <code>python run.py --import-dir &lt;kaust&gt;</code>.</p>

  <footer class="foot">
    Mudel: log(€/m²) = kauguse kõver (murdepunktid 2, 5, 8 km) + toad + pind + ehitusaasta + seisukord + korrus,
    eraldi müügile ja üürile. Keskpunkt on punkt, millest kaugus selgitab müügihinda kõige paremini.
    Alahinnatud = hind vähemalt 15% alla mudeli hinnangu. Koordinaadid: Maa- ja Ruumiamet (In-ADS). Andmed: kv.ee.
  </footer>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
  <script src="mudel.js"></script>
</body>
</html>
```

- [ ] **Step 4: Kirjuta `docs/mudel.js`**

```js
"use strict";

const VABADUSE = [59.4339, 24.7445];
const pct = new Intl.NumberFormat("et-EE", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
const pct2 = new Intl.NumberFormat("et-EE", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const eur = new Intl.NumberFormat("et-EE", { maximumFractionDigits: 0 });
const num1 = new Intl.NumberFormat("et-EE", { maximumFractionDigits: 1 });
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https:\/\//.test(u || "") ? u : "#");
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const state = { data: null, rooms: "all", sortSub: { key: "residual_median", dir: 1 }, sortList: { key: "residual", dir: 1 } };

function roomGroup(n) { return n >= 4 ? "4+" : String(n); }

// Diverging: negatiivne hälve (alahinnatud) -> --good, positiivne -> --bad
function divergingColor(v) {
  const t = Math.max(-1, Math.min(1, v / 0.2));
  return t <= 0 ? mix(css("--neutral"), css("--good"), -t) : mix(css("--neutral"), css("--bad"), t);
}
function mix(a, b, t) {
  const pa = hex(a), pb = hex(b);
  return `rgb(${pa.map((x, i) => Math.round(x + (pb[i] - x) * t)).join(",")})`;
}
function hex(h) { const m = h.replace("#", ""); return [0, 2, 4].map((i) => parseInt(m.slice(i, i + 2), 16)); }

function renderStats() {
  const d = state.data, last = d.runs[d.runs.length - 1], med = d.median;
  const eff = (deal, km) => pct2.format(med.effects[deal][km]);
  $("meta").textContent = `Keskpunkt ${eur.format(last.center_offset_m)} m Vabaduse väljakust · ${d.runs.length} ajapunkt${d.runs.length === 1 ? "" : "i"} · ` +
    `${last.n.sale} müügi- ja ${last.n.rent} üürikuulutust` + (last.n.not_geocoded ? ` · ${last.n.not_geocoded} ilma koordinaadita` : "");
  $("stats").innerHTML = ["1", "3", "6"].map((km) => `
    <div class="stat"><span class="stat-k">${km} km kaugusel, +100 m</span>
      <span class="stat-v">müük ${eff("sale", km)}</span><span class="stat-v2">üür ${eff("rent", km)}</span></div>`).join("") +
    `<div class="stat"><span class="stat-k">Mudeli R²</span><span class="stat-v">müük ${num1.format(last.r2.sale)}</span>
      <span class="stat-v2">üür ${num1.format(last.r2.rent)}</span></div>`;
}

function renderMap() {
  const d = state.data, center = d.median.center;
  const map = L.map("map", { scrollWheelZoom: false }).setView([center.lat, center.lon], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  L.circleMarker([center.lat, center.lon], { radius: 9, color: css("--ink"), weight: 3, fillOpacity: 0 })
    .bindTooltip("Andmetest leitud keskpunkt").addTo(map);
  L.circleMarker(VABADUSE, { radius: 6, color: css("--muted"), weight: 2, dashArray: "3", fillOpacity: 0 })
    .bindTooltip("Vabaduse väljak").addTo(map);
  d.subdistricts.forEach((s) => {
    L.circle([s.lat, s.lon], { radius: 120 + Math.sqrt(s.n) * 60, stroke: false, fillColor: divergingColor(s.residual_median), fillOpacity: 0.55 })
      .bindTooltip(`${esc(s.name)}: ${pct.format(s.residual_median)} mudelist (${s.n} kuulutust)`).addTo(map);
  });
  d.listings.forEach((l) => {
    L.circleMarker([l.lat, l.lon], { radius: 4, color: css("--good"), weight: 1, fillOpacity: 0.9 })
      .bindPopup(`<a href="${esc(safeUrl(l.url))}" target="_blank" rel="noopener">${esc(l.address)}</a><br>` +
        `${eur.format(l.price)} € · mudel ${eur.format(l.predicted_price)} € (${pct.format(l.residual)})`).addTo(map);
  });
  $("legend").textContent = "Ring = asum (värv: hind mudeli suhtes, roheline = odavam); täpid = alahinnatud kuulutused; " +
    "paks ring = andmetest leitud keskpunkt, katkendlik = Vabaduse väljak.";
}

function renderChart(svgId, key, fmt) {
  const svg = $(svgId), curve = state.data.curve, W = 480, H = 220, P = { l: 52, r: 12, t: 10, b: 30 };
  const ys = curve.map((c) => c[key]), yMax = Math.max(...ys) * 1.05, yMin = Math.min(...ys) * 0.9;
  const x = (d) => P.l + (d / 15) * (W - P.l - P.r);
  const y = (v) => H - P.b - ((v - yMin) / (yMax - yMin)) * (H - P.t - P.b);
  const path = curve.map((c, i) => `${i ? "L" : "M"}${x(c.d).toFixed(1)},${y(c[key]).toFixed(1)}`).join("");
  const yTicks = [0, 0.5, 1].map((t) => yMin + t * (yMax - yMin));
  svg.setAttribute("aria-label", `${key === "sale_m2" ? "Müügi" : "Üüri"} €/m² langeb ${fmt(ys[0])} pealt ${fmt(ys[ys.length - 1])} peale 0–15 km`);
  svg.innerHTML =
    yTicks.map((v) => `<line x1="${P.l}" x2="${W - P.r}" y1="${y(v)}" y2="${y(v)}" class="grid"/>` +
      `<text x="${P.l - 6}" y="${y(v) + 4}" class="tick" text-anchor="end">${fmt(v)}</text>`).join("") +
    [0, 5, 10, 15].map((d) => `<text x="${x(d)}" y="${H - 8}" class="tick" text-anchor="middle">${d} km</text>`).join("") +
    `<path d="${path}" class="line"/>`;
}

function sortRows(rows, { key, dir }) {
  return rows.sort((a, b) => {
    const p = a[key], q = b[key];
    if (p == null) return 1;
    if (q == null) return -1;
    return (typeof p === "string" ? p.localeCompare(q, "et") : p - q) * dir;
  });
}

const SUB_COLS = [
  { key: "name", label: "Asum", cell: (r) => esc(r.name) },
  { key: "residual_median", label: "Hind mudeli suhtes", num: true, cell: (r) => pct.format(r.residual_median) },
  { key: "n", label: "Kuulutusi", num: true, cell: (r) => r.n },
];
const LIST_COLS = [
  { key: "address", label: "Aadress", cell: (r) => `<a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">${esc(r.address)}</a>` },
  { key: "subdistrict", label: "Asum", cell: (r) => esc(r.subdistrict) },
  { key: "rooms", label: "Toad", num: true, cell: (r) => r.rooms },
  { key: "price", label: "Hind €", num: true, cell: (r) => eur.format(r.price) },
  { key: "predicted_price", label: "Mudel €", num: true, cell: (r) => eur.format(r.predicted_price) },
  { key: "residual", label: "Erinevus", num: true, cell: (r) => pct.format(r.residual) },
  { key: "yield", label: "Tootlus (mudel)", num: true, cell: (r) => pct.format(r.yield) },
];

function renderTable(id, cols, rows, sortState, onSort) {
  const t = $(id);
  t.querySelector("thead").innerHTML = "<tr>" + cols.map((c) => {
    const aria = sortState.key === c.key ? (sortState.dir > 0 ? "ascending" : "descending") : "none";
    return `<th class="${c.num ? "num" : ""}" aria-sort="${aria}"><button type="button" data-sort="${c.key}">${c.label}</button></th>`;
  }).join("") + "</tr>";
  t.querySelector("tbody").innerHTML = rows.map((r) =>
    "<tr>" + cols.map((c) => `<td class="${c.num ? "num" : ""}">${c.cell(r)}</td>`).join("") + "</tr>").join("");
  t.querySelector("thead").onclick = (e) => {
    const key = e.target.closest("button")?.dataset.sort;
    if (!key) return;
    onSort(key);
    $(id).querySelector(`thead [data-sort="${key}"]`)?.focus();
  };
}

function renderTables() {
  const toggle = (s, key) => ({ key, dir: s.key === key ? -s.dir : 1 });
  renderTable("t-sub", SUB_COLS, sortRows([...state.data.subdistricts], state.sortSub), state.sortSub,
    (key) => { state.sortSub = toggle(state.sortSub, key); renderTables(); });
  const list = state.data.listings.filter((l) => state.rooms === "all" || roomGroup(l.rooms) === state.rooms);
  renderTable("t-list", LIST_COLS, sortRows([...list], state.sortList), state.sortList,
    (key) => { state.sortList = toggle(state.sortList, key); renderTables(); });
}

async function load() {
  let data = null;
  try {
    const res = await fetch("data/model.json", { cache: "no-store" });
    if (res.ok) data = await res.json();
  } catch { /* tühi olek allpool */ }
  if (!data || !data.runs || !data.runs.length) {
    $("meta").textContent = "Mudelit pole veel arvutatud.";
    $("empty").hidden = false;
    return;
  }
  state.data = data;
  $("content").hidden = false;
  renderStats();
  renderMap();
  renderChart("chart-sale", "sale_m2", (v) => eur.format(v));
  renderChart("chart-rent", "rent_m2", (v) => num1.format(v));
  renderTables();
}

$("rooms").addEventListener("change", (e) => { state.rooms = e.target.value; renderTables(); });
load();
```

- [ ] **Step 5: Lisa `docs/style.css`-i** (`:root` heledasse ja tumedasse plokki värvid `--good`, `--bad`, `--neutral` hex-kujul — `mudel.js` `hex()` eeldab `#rrggbb`) ja stiilid `.site-nav`, `.stats/.stat*`, `#map` (kõrgus 460 px, mobiilis 340 px), `.legend`, `.charts` (kaks veergu, mobiilis üks), `svg .grid/.tick/.line`. Täpsed väärtused määra impeccable + dataviz oskusega; algväärtused:

```css
:root { --good: #1a7f5a; --bad: #b4532a; --neutral: #e8e6df; }
/* tumedas plokis: --good: #4cc38a; --bad: #e08a5f; --neutral: #3a3e37; */
.site-nav { display: flex; gap: 14px; margin-bottom: 6px; font-size: 14px; }
.site-nav a { color: var(--muted); }
.site-nav a[aria-current="page"] { color: var(--ink); font-weight: 600; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 16px 0; }
.stat { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 10px 12px; display: grid; gap: 2px; }
.stat-k { font-size: 12px; color: var(--muted); } .stat-v { font-weight: 600; } .stat-v2 { color: var(--muted); }
#map { height: 460px; border-radius: var(--radius); border: 1px solid var(--line); }
@media (max-width: 600px) { #map { height: 340px; } }
.legend { font-size: 13px; color: var(--muted); }
.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 16px 0; }
@media (max-width: 700px) { .charts { grid-template-columns: 1fr; } }
.charts figure { margin: 0; background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 8px; }
.charts figcaption { font-size: 13px; color: var(--muted); margin-bottom: 4px; }
svg .grid { stroke: var(--line); } svg .tick { fill: var(--muted); font-size: 11px; }
svg .line { fill: none; stroke: var(--accent); stroke-width: 2.5; }
main h2 { font-size: 18px; margin: 24px 0 8px; }
```

- [ ] **Step 6: Kontrolli brauseris** throwaway näidisandmetega: genereeri `docs/data/model.json` scratchpad'i skriptiga, mis kasutab `tootlus.model.fit_run`-i Task 3 testide `synth()` sarnaste andmetega (+ `runs`/`median` ümbris nagu `model.compute`). Serveeri `python -m http.server 8765 -d docs`; kontrolli headless brauseriga (nt Edge `--headless --screenshot`) desktop + 375 px, hele + tume: kaart laadib, keskpunkt/Vabaduse markerid, asumiringid, popupid, graafikud, tabelite sortimine ja toafilter, tühi olek (kustuta model.json ja laadi uuesti), navigatsioon mõlemal lehel. Kustuta näidisandmed ja `docs/data/`, peata server.

- [ ] **Step 7: impeccable `audit` + `polish`**; paranda leitu.

- [ ] **Step 8: Commit**

```bash
git add docs/mudel.html docs/mudel.js docs/index.html docs/style.css
git commit -m "feat: leht kaugus keskusest (kaart, graafikud, alahinnatud)"
```

---

### Task 6: Päris andmed, README ja kontroll (kasutajaga)

**Files:**
- Create: `README.md`; genereeritud `data/kv.sqlite`, `docs/data/results.json`, `docs/data/model.json`

- [ ] **Step 1: Kontroller küsib kasutajalt andmeid.** Kas `python run.py` töötab kasutaja enda terminalis? Kui ei, palu kasutajal salvestada brauserist (Ctrl+S, "Veebileht, ainult HTML") kv.ee otsingulehed ühte kausta: vähemalt Harjumaa korterite müük ja üür (kõik leheküljed; https://www.kv.ee/korterid-muuk/harjumaa?start=0, 50, 100, … ja https://www.kv.ee/korterid-uur/harjumaa?start=…), soovi korral teised maakonnad.

- [ ] **Step 2: Import / kogumine**

Run: `python run.py --import-dir <kaust>` (või `python run.py`)
Expected: "Import valmis: N maakonda", geokodeerimise edenemine, `Tulemused: ...`; `docs/data/model.json` olemas.

- [ ] **Step 3: Mõistlikkuse kontroll**

```bash
python -c "import json; d=json.load(open('docs/data/model.json',encoding='utf-8')); r=d['runs'][-1]; print(r['center'], r['center_offset_m'], r['effects'], r['r2'], r['n']); print(d['subdistricts'][:5]); print(len(d['listings']))"
```
Expected: keskpunkt Tallinna kesklinna lähedal (< 2 km Vabaduse väljakust); müügi mõju 1 km juures negatiivne (umbes −0,3% … −2% / 100 m); R² müük > 0,4; geokodeerimata < 15%.

- [ ] **Step 4: Kirjuta `README.md`**

````markdown
# Kinnisvara üüritootlus

Kogub kv.ee korterite müügi- ja üürikuulutused, hoiab ajalugu (`data/kv.sqlite`) ja arvutab:
- **Tootlus** (`docs/index.html`): bruto üüritootlus piirkondade kaupa (maakond → linn/vald → linnaosa → asum),
  iga käivitus eraldi ajapunkt, tulemus ajapunktide mediaan.
- **Kaugus keskusest** (`docs/mudel.html`): Tallinna hinnakeskpunkt, hinna muutus iga +100 m kohta,
  alahinnatud asumid ja kuulutused (regressioonimudel).

## Kasutamine

```bash
pip install -r requirements.txt
python run.py                      # kogu kv.ee-st (kui kv.ee lubab), salvesta, arvuta
python run.py --import-dir lehed   # impordi brauserist salvestatud kv.ee otsingulehed
python run.py --analyze-only       # arvuta uuesti olemasolevast andmebaasist
python run.py --serve              # kohalik leht "Käivita uuesti" nupuga
python run.py --publish            # ... ja git commit + push
```

**Salvestatud lehed:** ava brauseris nt `https://www.kv.ee/korterid-muuk/harjumaa` ja
`https://www.kv.ee/korterid-uur/harjumaa`, salvesta iga tulemusleht (Ctrl+S) samasse kausta. Maakond ja
müük/üür loetakse lehe aadressist. Maakond läheb arvesse, kui sellel on nii müügi- kui üürilehti.

Veebileht asub kaustas `docs/` (GitHub Pages: Settings → Pages → Branch `main`, kaust `/docs`).

## Arvutus

- Tootlus = üüri €/m² mediaan × 12 / müügi €/m² mediaan, sama käivituse andmetest; kehtiv ajapunkt vajab
  ≥ 5 müügi- ja ≥ 5 üürikuulutust.
- Kauguse mudel: log(€/m²) = kauguse kõver (2/5/8 km murdepunktid) + toad + pind + ehitusaasta + seisukord +
  korrus; keskpunkt = punkt, millest kaugus selgitab müügihinda kõige paremini. Alahinnatud = ≥ 15% alla mudeli.
- Koordinaadid: Maa- ja Ruumiameti In-ADS. Lävendid: `tootlus/config.py`, `tootlus/model.py`.

## Testid

```bash
python -m pytest
```
````

- [ ] **Step 5: Täielik testikomplekt** — `python -m pytest -q` → kõik läbivad.

- [ ] **Step 6: Commit**

```bash
git add README.md data/kv.sqlite docs/data/results.json docs/data/model.json
git commit -m "Esimesed andmed ja README"
```

- [ ] **Step 7: Push / GitHub Pages** — ainult kasutaja loal (kontroller küsib).
