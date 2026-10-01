# Kinnisvara üüritootlus

Kogub kv.ee korterite müügi- ja üürikuulutused, hoiab ajalugu (`data/kv.sqlite`) ja arvutab:
- **Tootlus** (`docs/index.html`): bruto üüritootlus piirkondade kaupa (maakond → linn/vald → linnaosa → asum),
  iga käivitus eraldi ajapunkt, tulemus ajapunktide mediaan.
- **Kaugus keskusest** (`docs/mudel.html`): Tallinna hinnakeskpunkt, hinna muutus iga +100 m kohta,
  alahinnatud asumid ja kuulutused (regressioonimudel).

## Kasutamine

```bash
pip install -r requirements.txt
python run.py                      # kogu kv.ee-st (kui kv.ee lubab), salvesta, arvuta
python run.py --browser            # kogu brauseriga (vt märkused allpool)
python run.py --import-dir lehed   # impordi brauserist salvestatud kv.ee otsingulehed
python run.py --analyze-only       # arvuta uuesti olemasolevast andmebaasist
python run.py --serve              # kohalik leht "Käivita uuesti" nupuga
python run.py --publish            # ... ja git commit + push
```

**Salvestatud lehed:** ava brauseris nt `https://www.kv.ee/korterid-muuk/harjumaa` ja
`https://www.kv.ee/korterid-uur/harjumaa`, salvesta iga tulemusleht (Ctrl+S) samasse kausta. Maakond ja
müük/üür loetakse lehe aadressist. Maakond läheb arvesse, kui sellel on nii müügi- kui üürilehti.

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
- kv.ee andmed kogutakse brauseriga (`python run.py --browser`). Kui aknas ilmub Cloudflare'i kontroll,
  klõpsa seda ise. Toorlehed (`data/lehed/`) ei lähe gitti.

## Testid

```bash
python -m pytest
```
