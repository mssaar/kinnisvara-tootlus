# Kauguse mudel ja salvestatud lehtede import — disain

Kuupäev: 2026-10-01
Staatus: kinnitamisel
Eelnev: `2026-10-01-kinnisvara-tootlus-design.md` (kogumine, ajalugu, tootlus, esileht)

## Eesmärk

1. **Andmed kv.ee-st ka siis, kui automaatne kogumine on blokeeritud.** kv.ee Cloudflare vastab programmi
   päringutele 403. Kasutaja salvestab otsingulehed brauserist; programm impordib need sama ajaloo sisse.
2. **Teine alamleht "Kaugus keskusest"**: samade andmete põhjal leitakse Tallinna hinnakeskpunkt, hinnatakse,
   kui palju muutub müügi- ja üürihind (€/m²) keskpunktist eemaldudes (iga +100 m kohta), ja leitakse
   alahinnatud asumid ning kuulutused.

Edukriteeriumid:
- `python run.py --import-dir <kaust>` loob uue käivituse salvestatud kv.ee otsingulehtedest; tulemused ja
  esileht uuenevad nagu tavalisel kogumisel.
- `docs/mudel.html` näitab kaarti (andmetest leitud keskpunkt + Vabaduse väljak), asumite hälbeid, alahinnatud
  kuulutusi, graafikut €/m² vs kaugus (müük ja üür) ning "+100 m" mõju 1, 3 ja 6 km kaugusel.
- Mudel leiab sünteetilistel andmetel keskpunkti < 100 m täpsusega ja kauguse mõju ±10% täpsusega.

Väljaspool skoopi: Cloudflare'i kontrolli lahendamine või brauseri matkimine; teised linnad peale Tallinna
mudelis; asumite piiride polügoonid.

## 1. Salvestatud lehtede import (`tootlus/importer.py`)

- Sisend: kaust `.html`/`.htm` failidega (brauseri "Salvesta leht"). Alamkaustu ei vaadata.
- Iga faili kohta loetakse `<link rel="canonical">` (varu: `og:url`), nt
  `https://www.kv.ee/korterid-muuk/harjumaa` → tehing **müük** (`korterid-muuk`) või **üür** (`korterid-uur`),
  maakond slugist (`harjumaa` → "Harjumaa"; slugid `config.py`-s maakonna ID kõrval).
- Kuulutused parsitakse olemasoleva `parser.parse_page`-iga; duplikaadid (sama ID, tehing) eemaldatakse.
- Fail, millel puudub tuntud canonical URL või kuulutused, jäetakse vahele ja logitakse.
- Üks import = üks käivitus (`runs`). `counties_ok` = maakonnad, millel on nii müügi- kui üürilehti;
  ainult müügi või ainult üüriga maakond jäetakse välja ja logitakse (sama reegel nagu kogumisel).
- `python run.py --import-dir <kaust>` → import → analüüs → `results.json` (+ mudel, vt allpool).
- Kohaliku serveri "Käivita uuesti" nupp jääb kogumise jaoks; impordi jaoks nuppu ei tehta.

## 2. Geokodeerimine (`tootlus/geocode.py`)

- Allikas: Maa- ja Ruumiameti In-ADS aadressiotsing
  `https://inaadress.maaamet.ee/inaadress/gazetteer?address=<tänav, linn>&results=1`.
  Vastusest: `viitepunkt_b` (laius), `viitepunkt_l` (pikkus), `asum` (nt "Tondi asum" → "Tondi").
- Päringu aadress: kuulutuse tänavaosa (aadress miinus `location`) + ", Tallinn". Korteri number
  (`-56` pärast majanumbrit) eemaldatakse.
- Ainult Tallinna kuulutused (`regions.parse(location).city == "Tallinn"`).
- Vahemälu SQLite tabelis `geocodes(query TEXT PRIMARY KEY, lat REAL, lon REAL, asum TEXT, found INTEGER,
  fetched_at TEXT)`; ka "ei leitud" salvestatakse, et seda uuesti ei küsitaks.
- Päringute vahel 0,2 s; võrguviga → aadress jääb sel korral geokodeerimata (ei salvestata), mudel jätkab.
- HTTP päring `urllib`-iga (In-ADS on avalik riiklik teenus, blokeeringut pole).

## 3. Mudel (`tootlus/model.py`, numpy)

Andmed: ühe käivituse puhastatud Tallinna müügi- ja üürivaatlused (sama puhastus nagu `analyze._clean`),
millel on koordinaadid. Kaugus = haversine-kaugus kilomeetrites.

Regressioon (vähimruutude meetod, eraldi müügile ja üürile):

```
log(€/m²) = b0 + kauguse_kõver(d) + toad[2,3,4+] + log(pind) + ehitusaasta_grupp + seisukord + esimene_korrus
```

- Kauguse kõver: tükati lineaarne, murdepunktid 2, 5, 8 km (`d, max(d-2,0), max(d-5,0), max(d-8,0)`).
- Ehitusaasta grupid: < 1940, 1940–1990, 1991–2010, > 2010, teadmata.
- Seisukord: uus/valmis, renoveeritud/san. remont tehtud, heas korras, keskmine, vajab remonti,
  teadmata (`parser.CONDITIONS` grupeeritult). Korrus: 1. korrus jah/ei/teadmata.
- Ehitusaasta, seisukord ja korrus pole praegu `observations`-tabelis — mudel võtab need `listings`-tabelist
  (viimane teadaolev väärtus); see on piisav, sest need ei muutu.

**Keskpunkt**: võrguotsing Tallinna piirides (lat 59.35–59.50, lon 24.55–24.95): esmalt 250 m sammuga,
siis 50 m sammuga parima punkti ümber ±300 m. Kriteerium: müügimudeli jääkide ruutude summa (väiksem parem).
Üürimudel kasutab sama keskpunkti.

**Väljundid käivituse kohta:**
- keskpunkt (lat, lon), kaugus Vabaduse väljakust (59.4339, 24.7445) meetrites;
- "+100 m" mõju müügile ja üürile 1, 3, 6 km kaugusel: `exp(kalle(d) × 0.1) − 1` (protsent);
- kõver: ennustatud €/m² "tüüpkorterile" (2 tuba, 50 m², 1991–2010, heas korras, mitte 1. korrus)
  kaugustel 0–15 km 0,25 km sammuga, müük ja üür;
- iga müügikuulutuse hälve = `tegelik / ennustatud − 1`; ennustatud kuuüür = üürimudeli €/m² × pind;
  mudelipõhine tootlus = ennustatud üür × 12 / hind;
- **alahinnatud kuulutus**: hälve ≤ −15%;
- **asumid** (In-ADS asum): kuulutuste keskmine koordinaat, müügihälvete mediaan, kuulutuste arv;
  arvestatakse asumid, kus ≥ 5 müügikuulutust;
- mudeli kvaliteet: R², vaatluste arv (müük/üür), geokodeerimata kuulutuste arv.

**Mitu käivitust**: mudel arvutatakse iga käivituse kohta eraldi (sama põhimõte nagu tootlusel — uue
käivituse üür/hinnad ei segune vanadega). Lehel: viimase käivituse kaart/tabelid; "+100 m" mõjud ja
keskpunkt ka kõigi käivituste mediaanina. Käivitus, kus Tallinna müügivaatlusi < 50 või üürivaatlusi < 30,
jäetakse mudelist välja.

Väljund: `docs/data/model.json`:
```
{"generated_at", "runs": [{"run_id", "started_at", "center": {"lat","lon"}, "center_offset_m",
   "effects": {"sale": {"1": x, "3": x, "6": x}, "rent": {...}}, "r2": {"sale","rent"},
   "n": {"sale","rent","not_geocoded"}}],
 "median": {"center": {...}, "effects": {...}},
 "curve": [{"d", "sale_m2", "rent_m2"}],
 "subdistricts": [{"name", "lat", "lon", "n", "residual_median"}],
 "listings": [{"id","url","address","lat","lon","rooms","area_m2","price","predicted_price",
               "residual","rent_estimate","yield","subdistrict"}]}   // ainult hälve <= -15%, sorditud
```

## 4. Leht `docs/mudel.html`

- Navigatsioon mõlemal lehel: "Tootlus" (index.html) ja "Kaugus keskusest" (mudel.html).
- Päis: keskpunkt ("x m Vabaduse väljakust"), "+100 m → müük −X%, üür −Y%" (1, 3, 6 km), R², vaatluste arv.
- Kaart (Leaflet 1.9 cdnjs-ist, OpenStreetMapi aluskaart): keskpunkt + Vabaduse väljak markeritena;
  asumid ringidena (suurus ~ kuulutuste arv, värv ~ hälbe mediaan, diverging skaala roheline=alahinnatud);
  alahinnatud kuulutused täppidena (popup: aadress, hind, hälve, link kv.ee-sse).
- Graafik (inline SVG, ilma teegita): €/m² vs kaugus, müük ja üür (kaks y-telge või kaks väikest graafikut).
- Tabelid: alahinnatud asumid (sorditav), alahinnatud kuulutused (sorditav, toafilter).
- Kui `model.json` puudub või mudel pole arvutatav: selge tühi olek ("Andmeid pole veel / liiga vähe Tallinna
  kuulutusi").
- Disain impeccable-oskusega, sama stiil ja tokenid nagu esilehel; dataviz-oskus graafiku ja värviskaala jaoks.

## 5. Pipeline

`pipeline.analyze_only` → `analyze.compute` + `geocode` (puuduvad aadressid) + `model.compute` →
`results.json` + `model.json`. Geokodeerimine käib ka `--analyze-only` korral (ainult puuduvad).

## Testid

- importer: fixture'id müügi- ja üürilehega (canonical URL), tundmatu fail vahele, maakond ilma üürita välja.
- geocode: salvestatud In-ADS JSON vastus (ilma võrguta, süstitud fetch), vahemälu tabamus, "ei leitud",
  võrguviga ei salvesta, korteri numbri eemaldus.
- model: sünteetilised andmed teadaoleva keskpunkti ja kauguse mõjuga (+ müra) → keskpunkt < 100 m,
  mõju ±10%; alahinnatud kuulutus tuvastatakse; käivitus alla miinimumi jäetakse välja; käivituste mediaan.
- pipeline: analyze_only kirjutab ka model.json (süstitud geocoder).
