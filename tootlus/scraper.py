"""kv.ee otsingutulemuste pärimine maakonna kaupa."""
from __future__ import annotations

import subprocess
import time

from . import config
from .parser import Listing, parse_page


class FetchError(Exception):
    """Lehte ei õnnestunud alla laadida."""


class ParseError(Exception):
    """Lehelt ei leitud oodatud kuulutusi (tõenäoliselt muutunud HTML)."""


def search_url(deal_type: int, county_id: int, start: int) -> str:
    return f"{config.BASE_URL}?deal_type={deal_type}&county={county_id}&start={start}"


def http_get(url: str, run=subprocess.run, sleep=time.sleep) -> str:
    cmd = [
        "curl", "-sS", "-L", "--compressed", "--max-time", "30",
        "-A", config.USER_AGENT, "-H", "Accept-Language: et-EE,et;q=0.9",
        "-w", "\n%{http_code}", url,
    ]
    last_error = ""
    for attempt in range(config.MAX_RETRIES):
        try:
            result = run(cmd, capture_output=True)
            if result.returncode != 0:
                last_error = f"curl exit {result.returncode}: {result.stderr.decode('utf-8', errors='replace').strip()}"
            else:
                body, _, status = result.stdout.rpartition(b"\n")
                if status.strip() == b"200":
                    return body.decode("utf-8", errors="replace")
                last_error = f"HTTP {status.strip().decode('ascii', errors='replace')}"
        except OSError as exc:
            last_error = f"curl ei käivitu: {exc}"
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
