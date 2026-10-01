from tootlus.regions import Location, build_district_map, fill_district, is_center, parse


def test_tallinn_full():
    assert parse("Kristiine City, Kristiine, Tallinn") == Location("Tallinn", "Kristiine", "Kristiine City")


def test_tallinn_reversed_order_uses_known_district():
    assert parse("Kesklinn, Kadriorg, Tallinn") == Location("Tallinn", "Kesklinn", "Kadriorg")


def test_tallinn_only_subdistrict():
    assert parse("Kadriorg, Kadriorg, Tallinn") == Location("Tallinn", None, "Kadriorg")


def test_tallinn_district_only():
    assert parse("Kesklinn, Tallinn") == Location("Tallinn", "Kesklinn", None)


def test_junk_is_ignored():
    assert parse("0 € lepingutasu, Pirita, Tallinn") == Location("Tallinn", "Pirita", None)
    assert parse("soe garaaz, panipak, Mustamäe, Tallinn") == Location("Tallinn", "Mustamäe", None)


def test_city_only():
    assert parse("Narva") == Location("Narva", None, None)


def test_empty():
    assert parse("") == Location(None, None, None)


def test_tartu_drops_redundant_linn():
    assert parse("Südalinn, Kesklinn, Tartu linn, Tartu") == Location("Tartu", "Kesklinn", "Südalinn")
    assert parse("Kesklinn, Tartu linn, Tartu") == Location("Tartu", "Kesklinn", None)


def test_town_inside_parish():
    assert parse("Uus-Rapla, Rapla linn, Rapla vald") == Location("Rapla vald", "Rapla linn", "Uus-Rapla")
    assert parse("Hagudi alevik, Rapla vald") == Location("Rapla vald", "Hagudi alevik", None)


def test_duplicate_city_component():
    assert parse("Kohtla-Järve, Järve, Kohtla-Järve") == Location("Kohtla-Järve", "Järve", None)


def test_is_center():
    assert is_center("Harjumaa", Location("Tallinn", "Kesklinn", None))
    assert not is_center("Harjumaa", Location("Saue vald", "Saue linn", None))
    assert is_center("Raplamaa", Location("Rapla vald", "Rapla linn", "Uus-Rapla"))
    assert not is_center("Raplamaa", Location("Rapla vald", "Hagudi alevik", None))
    assert is_center("Tartumaa", Location("Tartu", "Kesklinn", None))
    assert not is_center("Tartumaa", Location("Tartu vald", "Raadi", None))
    assert is_center("Ida-Virumaa", Location("Jõhvi vald", "Jõhvi linn", None))


def test_fill_district_from_other_listings():
    locs = [
        Location("Tallinn", "Kesklinn", "Kadriorg"),
        Location("Tallinn", "Kesklinn", "Kadriorg"),
        Location("Tallinn", "Pirita", "Kadriorg"),
    ]
    m = build_district_map(locs)
    assert fill_district(Location("Tallinn", None, "Kadriorg"), m) == Location("Tallinn", "Kesklinn", "Kadriorg")
    assert fill_district(Location("Tallinn", None, "Tundmatu"), m) == Location("Tallinn", None, "Tundmatu")
    assert fill_district(Location("Tallinn", "Pirita", None), m) == Location("Tallinn", "Pirita", None)
