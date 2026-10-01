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


def _accept_cookies(driver, sleep=time.sleep, attempts=5) -> bool:
    for attempt in range(attempts):
        # Try to find OneTrust banner button by ID first
        try:
            buttons = driver.find_elements("css selector", "#onetrust-accept-btn-handler")
            if buttons:
                buttons[0].click()
                return True
        except Exception:  # noqa: BLE001 - nupp võis kaduda; proovime järgmist
            pass

        # Fall back to text-based button matching
        for button in driver.find_elements("css selector", "button"):
            try:
                if _CONSENT.match((button.text or "").strip()):
                    button.click()
                    return True
            except Exception:  # noqa: BLE001 - nupp võis kaduda; proovime järgmist
                continue

        # If this wasn't the last attempt, sleep before retrying
        if attempt < attempts - 1:
            sleep(1.0)

    return False


def _wait_for_page(driver, progress, sleep, clock) -> str:
    started = clock()
    warned = False
    while True:
        html = driver.page_source
        if not _CHALLENGE.search(html) or parse_page(html):
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
    consent_retry_pages = 0  # Track pages where we try to accept cookies
    for county in counties.values():
        for deal in (config.DEAL_SALE, config.DEAL_RENT):
            seen: set[int] = set()
            for page in range(config.MAX_PAGES):
                start = page * config.PAGE_SIZE
                driver.get(page_url(deal, county, start))
                html = _wait_for_page(driver, progress, sleep, clock)
                if not consent_done and consent_retry_pages < 3:
                    consent_done = _accept_cookies(driver, sleep=sleep)
                    consent_retry_pages += 1
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
