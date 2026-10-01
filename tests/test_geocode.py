import sqlite3
import urllib.error

from tootlus.geocode import Geo, Geocoder, street_query

FOUND = {"addresses": [{"viitepunkt_b": "59.404690", "viitepunkt_l": "24.726348", "asum": "Tondi asum"}]}


def test_street_query():
    assert street_query("Sammu tn 10-56, Kristiine City, Kristiine, Tallinn", "Kristiine City, Kristiine, Tallinn") == "Sammu tn 10, Tallinn"
    assert street_query("Seebi 24a-8, Kristiine, Tallinn", "Kristiine, Tallinn") == "Seebi 24a, Tallinn"
    assert street_query("Lennuki tn, Kesklinn, Tallinn", "Kesklinn, Tallinn") == "Lennuki tn, Tallinn"
    assert street_query("Narva", "Narva") is None
    assert street_query("", "") is None


def test_geocode_and_cache():
    calls = []

    def fetch(url):
        calls.append(url)
        return FOUND

    g = Geocoder(sqlite3.connect(":memory:"), fetch=fetch, sleep=lambda s: None)
    assert g.lookup("Sammu tn 10, Tallinn") is None
    assert g.geocode_missing(["Sammu tn 10, Tallinn", "Sammu tn 10, Tallinn"], progress=lambda m: None) == 1
    assert g.lookup("Sammu tn 10, Tallinn") == Geo(59.40469, 24.726348, "Tondi")
    assert "address=Sammu%20tn%2010%2C%20Tallinn" in calls[0]
    assert g.geocode_missing(["Sammu tn 10, Tallinn"], progress=lambda m: None) == 0
    assert len(calls) == 1


def test_not_found_is_cached():
    calls = []
    g = Geocoder(sqlite3.connect(":memory:"), fetch=lambda url: calls.append(url) or {"addresses": []}, sleep=lambda s: None)
    g.geocode_missing(["Olematu 1, Tallinn"], progress=lambda m: None)
    g.geocode_missing(["Olematu 1, Tallinn"], progress=lambda m: None)
    assert g.lookup("Olematu 1, Tallinn") is None
    assert len(calls) == 1


def test_network_error_is_not_cached():
    def boom(url):
        raise urllib.error.URLError("võrk maas")

    conn = sqlite3.connect(":memory:")
    g = Geocoder(conn, fetch=boom, sleep=lambda s: None)
    assert g.geocode_missing(["Sammu tn 10, Tallinn"], progress=lambda m: None) == 1
    g2 = Geocoder(conn, fetch=lambda url: FOUND, sleep=lambda s: None)
    g2.geocode_missing(["Sammu tn 10, Tallinn"], progress=lambda m: None)
    assert g2.lookup("Sammu tn 10, Tallinn") == Geo(59.40469, 24.726348, "Tondi")


def test_missing_asum():
    g = Geocoder(sqlite3.connect(":memory:"),
                 fetch=lambda url: {"addresses": [{"viitepunkt_b": "59.4", "viitepunkt_l": "24.7", "asum": ""}]},
                 sleep=lambda s: None)
    g.geocode_missing(["X 1, Tallinn"], progress=lambda m: None)
    assert g.lookup("X 1, Tallinn") == Geo(59.4, 24.7, None)


def test_asum_with_comma_and_suffix():
    g = Geocoder(sqlite3.connect(":memory:"),
                 fetch=lambda url: {"addresses": [{"viitepunkt_b": "59.5", "viitepunkt_l": "24.8", "asum": "Kalamaja asum, Volta kvartal"}]},
                 sleep=lambda s: None)
    g.geocode_missing(["Krulli 10, Tallinn"], progress=lambda m: None)
    assert g.lookup("Krulli 10, Tallinn") == Geo(59.5, 24.8, "Kalamaja")


def test_non_dict_response_treated_as_not_found():
    g = Geocoder(sqlite3.connect(":memory:"),
                 fetch=lambda url: ["not", "a", "dict"],
                 sleep=lambda s: None)
    g.geocode_missing(["Some Address, Tallinn"], progress=lambda m: None)
    assert g.lookup("Some Address, Tallinn") is None


def test_stops_after_5_consecutive_failures_with_one_summary_line():
    calls = []

    def boom(url):
        calls.append(url)
        raise urllib.error.URLError("võrk maas")

    msgs = []
    g = Geocoder(sqlite3.connect(":memory:"), fetch=boom, sleep=lambda s: None)
    g.geocode_missing([f"Tn {i}, Tallinn" for i in range(50)], progress=msgs.append)
    assert len(calls) == 5
    assert len(msgs) == 1
    assert "katkestatud" in msgs[0] and "5 järjestikust viga" in msgs[0] and "võrk maas" in msgs[0]


def test_success_resets_failure_counter():
    calls = []

    def flaky(url):
        calls.append(url)
        if len(calls) % 4 == 0:  # iga 4. päring õnnestub -> kunagi 5 viga järjest
            return FOUND
        raise urllib.error.URLError("võrk maas")

    msgs = []
    g = Geocoder(sqlite3.connect(":memory:"), fetch=flaky, sleep=lambda s: None)
    g.geocode_missing([f"Tn {i}, Tallinn" for i in range(20)], progress=msgs.append)
    assert len(calls) == 20
    assert not any("katkestatud" in m for m in msgs)
    assert not any("viga" in m for m in msgs)
