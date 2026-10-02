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
