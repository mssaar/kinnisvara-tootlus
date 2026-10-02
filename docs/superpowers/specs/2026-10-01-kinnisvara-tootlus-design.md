# Kinnisvara üüritootlus — disain

Kuupäev: 2026-10-01
Staatus: kinnitamisel

## Eesmärk

Leida Eesti piirkonnad (nii täpselt kui võimalik), kus korterite **bruto üüritootlus** on keskmiselt kõige parem,
kasutades kv.ee müügi- ja üürikuulutusi. Programmi käivitatakse korduvalt (nt kord kuus / aastas); iga käivitus on
eraldi ajapunkt ning lõplik järjestus on **ajapunktide tootluste mediaan**.

Edukriteeriumid:
- `python run.py` kogub kõik kv.ee korterite müügi- ja üürikuulutused, salvestab ajaloo ja uuendab tulemused.
- Veebileht (GitHub Pages) näitab piirkondade järjestust tootluse mediaani järgi tasemetel maakond / linn-vald /
  linnaosa / asum, tubade arvu filtriga, ja parimaid konkreetseid müügikuulutusi.
- Uue käivituse üürid matchitakse ainult sama käivituse müügihindadega, mitte vanadega.
- Korduv kuulutus ei kirjuta vana infot üle — iga käivituse hind jääb alles.

Väljaspool skoopi: majad/krundid/äripinnad, netotootlus (maksud, remondifond, vakantsus), teised portaalid,
pilves (GitHub Actions) kogumine.

## Andmeallikas

kv.ee otsingutulemuste lehed (tavaline HTTP GET, 50 kuulutust lehel, lehekülgede vahetus `start=` parameetriga).
Kogutakse maakondade kaupa, et maakond oleks alati teada: korterite müük (`deal_type=1`) ja üür (`deal_type=2`).
Iga kuulutuse kaardilt (`<article data-object-id=…>`) loetakse:

| väli | allikas |
|---|---|
| id | `data-object-id` |
| url | `data-object-url` |
| aadress | `.h2` lingi tekst, nt "Sammu tn 10-56, Kristiine City, Kristiine, Tallinn" |
| toad | `.rooms` |
| pind m² | `.area` |
| hind € | `.price` (müük: koguhind; üür: kuuüür) |
| korrus, ehitusaasta, seisukord | `.object-excerpt` esimene lõik (parsitakse parima võimaluse piires, puudumine on lubatud) |

Viisakus: päringute vahel 1–2 s paus, brauserilaadne User-Agent, korduskatse (max 3) võrguvea korral.
Detaillehti ei avata. Kui ühe maakonna kogumine ebaõnnestub, logitakse viga ja käivitus märgitakse
mittetäielikuks; analüüs arvestab ainult edukalt kogutud maakondi selle käivituse kohta.

## Piirkonnad

Aadress jagatakse komade järgi; tänavaosa visatakse ära, ülejäänud komponendid tõlgendatakse paremalt vasakule:
**maakond** (otsingust) → **linn/vald** → **linnaosa** (Tallinnas, Tartus jt kus olemas) → **asum/küla**.
Puuduv tase jääb tühjaks (kuulutus osaleb ainult kõrgemate tasemete arvutuses).

**Maakond ilma keskuseta**: maakonna tasemel arvutatakse lisaks iga maakonna variant ilma maakonnakeskuseta,
nt "Harjumaa (v.a Tallinn)". Keskused on `tootlus/config.py` nimekirjas (ametlikud maakonnakeskused):
Harju–Tallinn, Tartu–Tartu, Pärnu–Pärnu, Saare–Kuressaare, Lääne–Haapsalu, Lääne-Viru–Rakvere, Järva–Paide,
Viljandi–Viljandi, Võru–Võru, Valga–Valga, Põlva–Põlva, Rapla–Rapla, Jõgeva–Jõgeva, Hiiu–Kärdla, Ida-Viru–Jõhvi.

Toarühmad: 1, 2, 3, 4+ (ja "kõik").

## Arhitektuur

```
tootlus/
  config.py     maakonnad + nende kv.ee ID-d, maakonnakeskused, lävendid
  scraper.py    kv.ee lehtede pärimine ja parsimine -> Listing objektid
  regions.py    aadress -> (maakond, linn, linnaosa, asum)
  store.py      SQLite: runs / listings / observations
  analyze.py    tootluse arvutus -> results.json
  server.py     kohalik veebiserver "Käivita uuesti" nupuga
run.py          CLI
data/kv.sqlite  ajalugu (commititakse repo)
docs/           GitHub Pages: index.html, app.js, style.css, data/results.json
tests/          pytest + salvestatud HTML näidised
```

Ainult standardteek + `requests` + `beautifulsoup4` (parsimiseks). Testideks `pytest`.

### Andmemudel (SQLite)

- `runs(id, started_at, finished_at, complete, counties_ok)`
- `listings(id, deal_type, url, address, location, county, rooms, area_m2, floor, build_year,
  condition, first_seen_run, last_seen_run)` — primaarvõti `(id, deal_type)`. `location` on aadressi osa pärast
  tänavat (nt "Kristiine City, Kristiine, Tallinn"). Kui kuulutus tuleb uuesti, uuendatakse `last_seen_run` ja
  püsiinfo; hind, pind ja toad lähevad alati uude vaatlusritta, nii et vana info säilib.
- `observations(run_id, listing_id, deal_type, price, area_m2, rooms, price_per_m2)` — üks rida iga kuulutuse kohta
  igas käivituses.

Piirkonnad (linn/linnaosa/asum) arvutatakse analüüsi ajal `location` väljast (`regions.py`), mitte ei salvestata —
nii saab aadressi tõlgendust hiljem parandada ja kogu ajalugu arvutatakse uuesti.
Aadressides esineb kasutaja sisestatud prügi ("0 € lepingutasu") ja ebaühtlast järjekorda; Tallinna linnaosad
tuvastatakse teadaoleva nimekirja järgi ning puuduv linnaosa tuletatakse asumi järgi teistest kuulutustest.

### Arvutus (`analyze.py`)

1. **Puhastus** käivituse kaupa: välja jäävad puuduva hinna/pinnaga kuulutused, pind < 10 või > 300 m²,
   müügi €/m² väljaspool 200–15 000, üüri €/m² väljaspool 2–60 (lävendid `config.py`-s).
2. **Ajapunkti tootlus**: iga (käivitus, tase, piirkond, toarühm) kohta
   `müük_m2 = mediaan(müügi €/m²)`, `üür_m2 = mediaan(üüri €/m²)`,
   `tootlus = üür_m2 × 12 / müük_m2`. Kehtiv ainult kui müügi- ja üürikuulutusi on kumbagi ≥ 5.
3. **Lõplik tootlus** = kehtivate ajapunktide tootluste mediaan. Lisaks: viimase käivituse tootlus,
   kehtivate käivituste arv, viimase käivituse kuulutuste arvud ja €/m² mediaanid.
   Piirkond, millel pole ühtegi kehtivat ajapunkti, kuvatakse halli reana "vähe andmeid" (viimase käivituse
   arvudega).
4. **Parimad kuulutused** (ainult viimane käivitus): iga müügikuulutuse oodatav kuuüür =
   pind × üüri €/m² mediaan kõige täpsemalt tasemelt, kus sama toarühma üürikuulutusi on ≥ 5
   (asum → linnaosa → linn → maakond); `tootlus = oodatav üür × 12 / hind`. Kuvatakse ka, mis tasemelt üür võeti.

Väljund `docs/data/results.json`: `generated_at`, `runs` (käivituste nimekiri), `regions` (read tasemega
`county | county_ex_center | city | district | subdistrict`, toarühm, näitajad), `listings` (top 500 müügikuulutust).

## Kasutamine

- `python run.py` — kogu → salvesta → analüüsi.
- `python run.py --analyze-only` — ainult arvutus olemasolevast andmebaasist.
- `python run.py --publish` — lisaks `git add data docs/data && git commit && git push`.
- `python run.py --serve` — avab `http://localhost:8000` sama UI-ga, kus on lisaks nupp **"Käivita uuesti"**;
  nupp käivitab kogumise taustal ja näitab edenemist (maakond / lehekülg). GitHub Pages'il nuppu ei kuvata,
  selle asemel on märge viimase uuenduse ajaga.

## UI (`docs/`)

Staatiline leht, laeb `data/results.json`. Disain impeccable-oskusega.
- **Piirkonnad**: taseme valik (maakond / linn-vald / linnaosa / asum), lüliti "ilma maakonnakeskuseta"
  (maakonna tasemel), toarühma filter, otsing piirkonna nimele, ülemtaseme filter (nt ainult Tallinna linnaosad).
  Sorditav tabel: piirkond, ülemtase, tootluse mediaan, viimane tootlus, müügi €/m², üüri €/m², kuulutuste arv
  (müük/üür), kehtivate ajapunktide arv. Vähe andmetega read hallid ja vaikimisi tabeli lõpus.
- **Parimad kuulutused**: aadress (link kv.ee-sse), toad, m², hind, oodatav üür, tootlus, üüri allikatase;
  samad filtrid.
- Päises: viimase uuenduse aeg ja käivituste arv.

## Veakäsitlus

- Võrguvead: korduskatse, siis maakond märgitakse ebaõnnestunuks; ülejäänud kogumine jätkub.
- Parsimisvead üksikul kaardil: kaart jäetakse vahele, loendur logitakse. Kui lehelt ei leita ühtegi kaarti,
  kuigi lehel peaks neid olema, katkestatakse selle maakonna kogumine (tõenäoliselt muutunud HTML).
- Käivitus, milles kõik maakonnad ebaõnnestusid, analüüsi ei mõjuta.

## Testimine

pytest, ilma võrguta:
- parser salvestatud kv.ee HTML-näidistel (müük + üür, sh puuduvate väljadega kaart);
- aadressi jagamine tasemeteks (Tallinn linnaosa+asumiga, väikelinn, küla+vald);
- store: korduv kuulutus → uus vaatlus, vana säilib; püsiinfo uuendus;
- analyze: mediaanid, lävend 5, ajapunktide mediaan, uue käivituse üür ei segune vana hinnaga,
  "ilma keskuseta" variant, parimate kuulutuste tagasilangemine tasemete kaupa.
