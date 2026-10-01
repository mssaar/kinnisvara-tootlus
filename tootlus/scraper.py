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
