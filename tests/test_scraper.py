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
