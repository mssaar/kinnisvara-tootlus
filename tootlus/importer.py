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
