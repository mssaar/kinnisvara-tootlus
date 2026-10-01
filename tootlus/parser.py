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
