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
