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
            # Käsitle ID valitsijat OneTrust nupu jaoks
            if value == "#onetrust-accept-btn-handler" and self.onetrust_button:
                return [self.onetrust_button]
            # Käsitle tavalist nupu valitsijat
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
    """OneTrust bänner nuppu #onetrust-accept-btn-handler ID-ga klõpsitakse esimesel lehel."""
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
    """OneTrust bänner ilmub 3. katsel pärast kahte tyhjat katset, klõpsitatakse siiski.

    Verifitseerib, et:
    - Nõusolekuuhe magamised on täpselt [1.0, 1.0] (enne kui bänner ilmub 3. katsel)
    - Salvestatud leht uuendatakse pärast klõpsu (pärast klõpsu page_source kasutatakse)
    """
    u = browser.page_url
    pre_click_html = page(range(1, 51))
    post_click_html = page(range(1, 101))  # Erinev sisu pärast klõpsu (100 kirjega)
    pages = {
        u(1, "Hiiumaa", 0): [pre_click_html, post_click_html],  # Tagastatakse 2 korda (enne ja pärast klõpsu)
        u(1, "Hiiumaa", 50): [page(range(101, 111))],  # Erinevad IDd
        u(1, "Hiiumaa", 100): [page(range(101, 111))],  # Sama, kutsub pausi
        u(2, "Hiiumaa", 0): [page([1], "https://www.kv.ee/korterid-uur/hiiumaa")],
        u(2, "Hiiumaa", 50): [page([1], "https://www.kv.ee/korterid-uur/hiiumaa")],
    }
    consent_sleep_log = []

    class DelayedOneTrustDriver(FakeDriver):
        def __init__(self, pages):
            super().__init__(pages)
            self.onetrust_attempt = 0

        def find_elements(self, by, value):
            if by == "css selector":
                if value == "#onetrust-accept-btn-handler":
                    self.onetrust_attempt += 1
                    # Tagasta nupp ainult 3. katsel
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
        if s == 1.0:  # Nõusolekuuhe uurimise uni (mitte PAGE_DELAY_S, mis on 2.0)
            consent_sleep_log.append(s)

    n = browser.collect(d, tmp_path, {2: "Hiiumaa"}, progress=lambda m: None, sleep=mock_sleep)
    assert n >= 3  # Vähemalt 3 lehekülge (2 müük + 1 üür)
    # Nõusolekuuhe magamised peaksid olema täpselt [1.0, 1.0] (enne kui bänner ilmub 3. katsel)
    assert consent_sleep_log == [1.0, 1.0], f"Expected [1.0, 1.0], got {consent_sleep_log}"
    # Bänner peaks klõpsitama
    assert ("click", "id:onetrust-accept-btn-handler") in d.log
    # Verifitseeri salvestatud faili sisaldab pärast klõpsu sisu (rohkem kirjeid pärast klõpsu)
    saved_files = sorted(tmp_path.iterdir())
    # Esimene fail peaks olema müügi leht 100 ID-ga (pärast klõpsu) tänu page_source kutsele pärast klõpsu
    first_file_content = saved_files[0].read_text()
    assert "data-object-id=\"100\"" in first_file_content, "Post-click content not found in saved file"


def test_no_banner_stops_retrying_after_3_pages(tmp_path):
    """Verifitseeri 3-lehekülje katse piiri jõustamine, kui bänner ei ilmu kunagi.

    Koos 4+ leheküljega kogutud ja bännerita:
    - #onetrust-accept-btn-handler otsing juhtub täpselt 3 lehekülje × 5 katse = 15 korda
    - Nõusolekuuhe magamised kokku täpselt 3 × 4 = 12 sekundit (4 und lehekülg kohta, 5. katse ei maga)
    """
    u = browser.page_url
    pages = {
        u(1, "Hiiumaa", 0): [page(range(1, 51))],
        u(1, "Hiiumaa", 50): [page(range(51, 61))],
        u(1, "Hiiumaa", 100): [page(range(51, 61))],
        u(1, "Harjumaa", 0): [page(range(101, 151))],  # 4. leht (ei tohiks uuesti proovida küpsiste bännerit)
        u(2, "Hiiumaa", 0): [page([1], "https://www.kv.ee/korterid-uur/hiiumaa")],
    }

    onetrust_lookup_count = [0]  # Muutuv loendur
    consent_sleep_log = []

    class CountingDriver(FakeDriver):
        def find_elements(self, by, value):
            if by == "css selector":
                if value == "#onetrust-accept-btn-handler":
                    onetrust_lookup_count[0] += 1
                    return []  # Ärgi bänner kunagi leitud
                elif value == "button":
                    return list(self.buttons)
            return []

    d = CountingDriver(pages)

    def mock_sleep(s):
        if s == 1.0:  # Nõusolekuuhe uurimise uni (mitte PAGE_DELAY_S, mis on 2.0)
            consent_sleep_log.append(s)

    n = browser.collect(d, tmp_path, {2: "Hiiumaa", 1: "Harjumaa"}, progress=lambda m: None, sleep=mock_sleep)
    assert n == 4  # 3 Hiiumaa + 1 Harjumaa = 4 salvestatud lehekülge

    # Verifitseeri täpselt 3 lehekülje kalori uuesti proovimised (3 × 5 katset = 15 otsingu)
    assert onetrust_lookup_count[0] == 15, \
        f"Expected 15 lookups (3 pages × 5 attempts), got {onetrust_lookup_count[0]}"

    # Verifitseeri täpselt 12 nõusolekuuhe und (3 lehekülje × 4 und lehekülg kohta, 5. katse ei maga)
    assert len(consent_sleep_log) == 12, \
        f"Expected 12 consent sleeps (3 pages × 4 per page), got {len(consent_sleep_log)}"
    assert consent_sleep_log == [1.0] * 12, \
        f"Kõik nõusolekuuhe magamised peaksid olema 1.0 sekund, saime {consent_sleep_log}"
