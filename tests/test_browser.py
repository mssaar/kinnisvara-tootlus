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
