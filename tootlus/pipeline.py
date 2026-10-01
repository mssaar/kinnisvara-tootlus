"""Üks täiskäivitus: kogumine -> salvestus -> analüüs."""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

from . import analyze, config, geocode, model, scraper

ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = ROOT / "docs" / "data" / "results.json"
MODEL_PATH = ROOT / "docs" / "data" / "model.json"
DB_PATH = ROOT / "data" / "kv.sqlite"

DEAL_LABELS = {config.DEAL_SALE: "müük", config.DEAL_RENT: "üür"}


def run_once(store, counties=config.COUNTIES, scrape=scraper.scrape_county, progress=print,
             results_path=RESULTS_PATH, model_path=MODEL_PATH, geocoder=None) -> dict:
    run_id = store.start_run()
    ok: list[str] = []
    for county_id, name in counties.items():
        collected = {}
        try:
            for deal in (config.DEAL_SALE, config.DEAL_RENT):
                label = f"{name} {DEAL_LABELS[deal]}"
                progress(f"{label}: alustan")
                collected[deal] = scrape(
                    deal, county_id,
                    on_page=lambda page, total, label=label: progress(f"{label}: leht {page}, {total} kuulutust"),
                )
        except (scraper.FetchError, scraper.ParseError) as exc:
            progress(f"{name}: VIGA, maakond jäetakse sellest käivitusest välja ({exc})")
            continue
        for deal, items in collected.items():
            store.save_listings(run_id, deal, name, items)
        ok.append(name)
    store.finish_run(run_id, ok, complete=len(ok) == len(counties))
    progress(f"Kogumine valmis: {len(ok)}/{len(counties)} maakonda")
    return analyze_only(store, results_path, model_path, geocoder, progress)


def analyze_only(store, results_path=RESULTS_PATH, model_path=MODEL_PATH, geocoder=None, progress=print) -> dict:
    results = analyze.compute(store)
    analyze.write_results(results, results_path)
    geocoder = geocoder or geocode.Geocoder(store.conn)
    new = geocoder.geocode_missing(model.queries(store), progress=progress)
    if new:
        progress(f"Geokodeerimine: {new} uut aadressi")
    model.write(model.compute(store, geocoder), model_path)
    return results


def publish(repo_root: Path, run=subprocess.run) -> None:
    run(["git", "add", "data", "docs/data"], cwd=repo_root, check=True)
    run(["git", "commit", "-m", f"Andmete uuendus {date.today().isoformat()}"], cwd=repo_root, check=True)
    run(["git", "push"], cwd=repo_root, check=True)
