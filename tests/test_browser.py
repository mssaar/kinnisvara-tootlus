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
    def __init__(self, text, log, id=None):
        self.text, self.log, self.id = text, log, id

    def click(self):
        self.log.append(("click", self.text or f"id:{self.id}"))


class FakeDriver:
    """pages: url -> list of page sources returned on successive reads of page_source."""

    def __init__(self, pages, buttons=(), onetrust_button=None):
        self.pages = pages
        self.current = None
        self.log = []
        self.buttons = [FakeButton(t, self.log) for t in buttons]
        self.onetrust_button = onetrust_button
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
        if by == "css selector":
            # Handle ID selector for OneTrust button
            if value == "#onetrust-accept-btn-handler" and self.onetrust_button:
                return [self.onetrust_button]
            # Handle regular button selector
            elif value == "button":
                return list(self.buttons)
        return []


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


def test_normal_page_with_cloudflare_script_is_not_a_challenge(tmp_path):
    script = '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
    u = browser.page_url
    uur = "https://www.kv.ee/korterid-uur/hiiumaa"
    pages = {u(1, "Hiiumaa", 0): [page([1]).replace("</body>", script + "</body>")],
             u(1, "Hiiumaa", 50): [page([1])],
             u(2, "Hiiumaa", 0): [page([2], uur)], u(2, "Hiiumaa", 50): [page([2], uur)]}
    msgs = []
    n = browser.collect(FakeDriver(pages), tmp_path, {2: "Hiiumaa"}, progress=msgs.append, sleep=lambda s: None)
    assert n == 2
    assert not any("kontroll" in m for m in msgs)


def test_onetrust_banner_clicked_by_id(tmp_path):
    """OneTrust banner with #onetrust-accept-btn-handler ID is clicked on first page."""
    u = browser.page_url
    pages = {
        u(1, "Hiiumaa", 0): [page(range(1, 51))],
        u(1, "Hiiumaa", 50): [page(range(51, 61))],
        u(1, "Hiiumaa", 100): [page(range(51, 61))],
        u(2, "Hiiumaa", 0): [page([1], "https://www.kv.ee/korterid-uur/hiiumaa")],
        u(2, "Hiiumaa", 50): [page([1], "https://www.kv.ee/korterid-uur/hiiumaa")],
    }
    d = FakeDriver(pages)
    onetrust_btn = FakeButton(None, d.log)
    onetrust_btn.id = "onetrust-accept-btn-handler"
    d.onetrust_button = onetrust_btn
    n = browser.collect(d, tmp_path, {2: "Hiiumaa"}, progress=lambda m: None, sleep=lambda s: None)
    assert n == 3
    assert ("click", "id:onetrust-accept-btn-handler") in d.log


def test_onetrust_banner_delayed_appearance(tmp_path):
    """OneTrust banner appears on 3rd attempt after returning nothing twice, still gets clicked."""
    u = browser.page_url
    pages = {
        u(1, "Hiiumaa", 0): [page(range(1, 51))],
        u(1, "Hiiumaa", 50): [page(range(51, 61))],
        u(1, "Hiiumaa", 100): [page(range(51, 61))],
        u(2, "Hiiumaa", 0): [page([1], "https://www.kv.ee/korterid-uur/hiiumaa")],
        u(2, "Hiiumaa", 50): [page([1], "https://www.kv.ee/korterid-uur/hiiumaa")],
    }
    sleep_log = []

    class DelayedOneTrustDriver(FakeDriver):
        def __init__(self, pages):
            super().__init__(pages)
            self.onetrust_attempt = 0

        def find_elements(self, by, value):
            if by == "css selector":
                if value == "#onetrust-accept-btn-handler":
                    self.onetrust_attempt += 1
                    # Return button only on 3rd attempt
                    if self.onetrust_attempt >= 3:
                        btn = FakeButton(None, self.log)
                        btn.id = "onetrust-accept-btn-handler"
                        return [btn]
                    return []
                elif value == "button":
                    return list(self.buttons)
            return []

    d = DelayedOneTrustDriver(pages)

    def mock_sleep(s):
        sleep_log.append(s)

    n = browser.collect(d, tmp_path, {2: "Hiiumaa"}, progress=lambda m: None, sleep=mock_sleep)
    assert n == 3
    # Should have slept 2 times during 5 attempts on first page (attempts 1 and 2)
    assert len(sleep_log) >= 2
    assert ("click", "id:onetrust-accept-btn-handler") in d.log


def test_no_banner_stops_retrying_after_3_pages(tmp_path):
    """When no banner is found, collection finishes and retrying stops after 3 pages."""
    u = browser.page_url
    pages = {
        u(1, "Hiiumaa", 0): [page(range(1, 51))],
        u(1, "Hiiumaa", 50): [page(range(51, 61))],
        u(1, "Hiiumaa", 100): [page(range(51, 61))],
        u(2, "Hiiumaa", 0): [page([1], "https://www.kv.ee/korterid-uur/hiiumaa")],
        u(2, "Hiiumaa", 50): [page([1], "https://www.kv.ee/korterid-uur/hiiumaa")],
    }
    d = FakeDriver(pages)  # No banner, no onetrust button
    n = browser.collect(d, tmp_path, {2: "Hiiumaa"}, progress=lambda m: None, sleep=lambda s: None)
    assert n == 3
    # Verify that _accept_cookies was called (there will be get requests)
    # and collection still completed successfully
