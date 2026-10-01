"""Projekti konstandid."""

BASE_URL = "https://www.kv.ee/search"
SITE_URL = "https://www.kv.ee"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

DEAL_SALE = 1
DEAL_RENT = 2

PAGE_SIZE = 50
REQUEST_DELAY_S = 1.5
MAX_RETRIES = 3
MAX_PAGES = 300

# kv.ee maakonna ID -> nimi
COUNTIES = {
    1: "Harjumaa", 2: "Hiiumaa", 3: "Ida-Virumaa", 4: "Jõgevamaa", 5: "Järvamaa",
    6: "Läänemaa", 7: "Lääne-Virumaa", 8: "Põlvamaa", 9: "Pärnumaa", 10: "Raplamaa",
    11: "Saaremaa", 12: "Tartumaa", 13: "Valgamaa", 14: "Viljandimaa", 15: "Võrumaa",
}

# Ametlikud maakonnakeskused ("ilma keskuseta" vaate jaoks)
COUNTY_CENTERS = {
    "Harjumaa": "Tallinn", "Hiiumaa": "Kärdla", "Ida-Virumaa": "Jõhvi",
    "Jõgevamaa": "Jõgeva", "Järvamaa": "Paide", "Läänemaa": "Haapsalu",
    "Lääne-Virumaa": "Rakvere", "Põlvamaa": "Põlva", "Pärnumaa": "Pärnu",
    "Raplamaa": "Rapla", "Saaremaa": "Kuressaare", "Tartumaa": "Tartu",
    "Valgamaa": "Valga", "Viljandimaa": "Viljandi", "Võrumaa": "Võru",
}

TALLINN_DISTRICTS = frozenset({
    "Haabersti", "Kesklinn", "Kristiine", "Lasnamäe",
    "Mustamäe", "Nõmme", "Pirita", "Põhja-Tallinn",
})

MIN_SAMPLES = 5
AREA_RANGE = (10.0, 300.0)
SALE_M2_RANGE = (200.0, 15000.0)
RENT_M2_RANGE = (2.0, 60.0)
TOP_LISTINGS = 500
ROOM_GROUPS = ("1", "2", "3", "4+")
