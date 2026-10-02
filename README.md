# Kinnisvara üüritootlus

Kogub kv.ee korterite müügi- ja üürikuulutused, hoiab ajalugu (`data/kv.sqlite`) ja arvutab:
- **Tootlus** (`docs/index.html`): bruto üüritootlus piirkondade kaupa (maakond → linn/vald → linnaosa → asum),
  iga käivitus eraldi ajapunkt, tulemus ajapunktide mediaan.
- **Kaugus keskusest** (`docs/mudel.html`): Tallinna hinnakeskpunkt, hinna muutus iga +100 m kohta,
  alahinnatud asumid ja kuulutused (regressioonimudel).

## Kasutamine

```bash
pip install -r requirements.txt
python run.py                      # kogu kv.ee lehed Edge'i aknaga, salvesta, arvuta (vaikimisi)
python run.py --counties 1,12      # ainult valitud maakonnad (kv.ee ID-d, vt tootlus/config.py)
python run.py --curl               # kogu otse ilma brauserita (kv.ee Cloudflare blokeerib selle sageli)
python run.py --import-dir lehed   # impordi brauserist käsitsi salvestatud kv.ee otsingulehed
python run.py --analyze-only       # arvuta uuesti olemasolevast andmebaasist
python run.py --backfill-dir lehed # täienda olemasolevate kuulutuste korruseandmeid salvestatud lehtedelt
python run.py --serve              # kohalik leht "Käivita uuesti" nupuga (http://127.0.0.1:8000/)
python run.py --serve --port 8080  # ... teisel pordil
python run.py --publish            # ... ja git commit + push
```

**Brauserikogumine (vaikimisi):** avaneb nähtav Edge'i aken (Selenium), mis käib läbi iga maakonna müügi- ja
üürilehed. Kui aknas ilmub Cloudflare'i kontroll, klõpsa see ise läbi — kogumine ootab kuni 5 minutit ja
jätkub siis ise. Lehed salvestatakse iga käivituse jaoks eraldi kausta `data/lehed/<kuupäev_kellaaeg>/` ja
imporditakse lõpuks ühe ajapunktina. `--serve` nupp kasutab sama kogumist (`--serve --curl` otsekogumist).

**Kui kogumine katkeb** (aken suleti, Cloudflare'i kontroll jäi lahendamata, võrk kadus): lõpuni kogutud
maakonnad (mõlemad, müük ja üür) imporditakse automaatselt, pooleli jäänud maakond jäetakse välja. Ülejäänud
maakondade jaoks käivita kogumine hiljem uuesti, nt `python run.py --counties 9,12`. Kui ühtegi maakonda ei
kogutud, lõpetab `run.py` veateatega (väljumiskood 1) ega muuda tulemusi.

**Käsitsi salvestatud lehed:** ava brauseris nt `https://www.kv.ee/korterid-muuk/harjumaa` ja
`https://www.kv.ee/korterid-uur/harjumaa`, salvesta iga tulemusleht (Ctrl+S) samasse kausta ja käivita
`python run.py --import-dir <kaust>`. Maakond ja müük/üür loetakse lehe aadressist. Maakond läheb arvesse, kui
sellel on nii müügi- kui üürilehti.

**Vanade andmete täiendamine:** `--backfill-dir <kaust>` loeb salvestatud lehed uuesti ja uuendab juba
andmebaasis olevate kuulutuste korrust, maja korruste arvu, ehitusaastat ja seisukorda (uut ajapunkti ega hindu ei
lisata). Seejärel `python run.py --analyze-only`. Vanem `data/kv.sqlite` saab korruste arvu veeru avamisel ise juurde.

**Ajahinnang:** `--serve` salvestab iga eduka käivituse kestuse faili `data/viimane_kaivitus.json` (gitist väljas) ja
näitab nupu all hinnangulist aega; esimesel korral 20–30 min.

Veebileht asub kaustas `docs/` (GitHub Pages: Settings → Pages → Branch `main`, kaust `/docs`).

## Arvutus

- Tootlus = üüri €/m² mediaan × 12 / müügi €/m² mediaan, sama käivituse andmetest; kehtiv ajapunkt vajab
  ≥ 5 müügi- ja ≥ 5 üürikuulutust.
- Kauguse mudel: log(€/m²) = kauguse kõver (2/5/8 km murdepunktid) + toad + pind + ehitusaasta + seisukord +
  korrus; keskpunkt = punkt, millest kaugus selgitab müügihinda kõige paremini. Alahinnatud = ≥ 15% alla mudeli.
- Koordinaadid: Maa- ja Ruumiameti In-ADS. Lävendid: `tootlus/config.py`, `tootlus/model.py`.

## Märkused andmete kohta

- Kõige "alahinnatum" kuulutus võib olla osa korterist, tuba või erijuhtum (nt vale hind). Kontrolli
  kv.ee-s üle enne kui selle põhjal tegutsed.
- Tootlus on bruto: kulusid (haldus, maks, tühiperioodid, remont) ei arvestata.
- Parimate kuulutuste oodatav üür tuleb kõige täpsemalt tasemelt, kus on ≥ 5 üürikuulutust (asum → linnaosa →
  linn → maakond v.a keskus → maakond). Maakonna keskmise üüriga kuulutused on vaikimisi peidus, sest
  maakonna mediaan võib küla korteri üüri tugevalt üle hinnata.
- Toorlehed (`data/lehed/`) ei lähe gitti.

## Testid

```bash
python -m pytest
```
