"""Kinnisvara üüritootlus — käsurida.

    python run.py                 kogu kv.ee lehed nähtava Edge'i aknaga (Selenium), salvesta, arvuta
    python run.py --curl          kogu kv.ee otse ilma brauserita (kv.ee võib selle blokeerida)
    python run.py --analyze-only  arvuta tulemused olemasolevast andmebaasist
    python run.py --publish       ... ja tee git commit + push
    python run.py --import-dir K  impordi kaustast K brauserist salvestatud kv.ee otsingulehed
    python run.py --backfill-dir K  täienda kaustast K olemasolevate kuulutuste korruseandmeid (ei arvuta)
    python run.py --serve         ava kohalik leht "Käivita uuesti" nupuga
    python run.py --counties 1,2  ainult valitud maakonnad (kv.ee ID-d)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tootlus import config, pipeline
from tootlus.store import Store


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="kv.ee korterite üüritootlus piirkondade kaupa")
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--import-dir", help="kaust brauserist salvestatud kv.ee otsingulehtedega")
    parser.add_argument("--backfill-dir", help="kaust salvestatud lehtedega, millest täiendada kuulutuste andmeid")
    parser.add_argument("--curl", action="store_true", help="kogu otse ilma brauserita (võib olla blokeeritud)")
    parser.add_argument("--browser", action="store_true", help=argparse.SUPPRESS)  # vana lipp, nüüd vaikimisi
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--counties", help="komaga eraldatud kv.ee maakonna ID-d, nt 1,12")
    args = parser.parse_args(argv)

    counties = config.COUNTIES
    if args.counties:
        counties = {int(c): config.COUNTIES[int(c)] for c in args.counties.split(",")}

    if args.serve:
        from tootlus.server import serve
        serve(args.port, counties, curl=args.curl)
        return 0

    pipeline.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = Store(str(pipeline.DB_PATH))
    if args.backfill_dir:
        from tootlus import importer
        try:
            n = importer.backfill_dir(store, Path(args.backfill_dir))
        finally:
            store.close()
        print(f"Täiendatud {n} kuulutust. Tulemuste uuendamiseks: python run.py --analyze-only")
        return 0
    try:
        ok = None  # None: kogumist ei toimunud (ainult analüüs)
        if args.import_dir:
            from tootlus.importer import import_dir
            ok = import_dir(store, Path(args.import_dir))
        elif args.analyze_only:
            pass
        elif args.curl:
            ok = pipeline.collect_curl(store, counties)
        else:
            from tootlus import browser
            ok = browser.collect_and_import(store, counties)
        if ok is not None and not ok:
            print(f"VIGA: {pipeline.NO_COUNTIES_MSG}, tulemusi ei uuendatud.", file=sys.stderr)
            return 1
        results = pipeline.analyze_only(store)
    finally:
        store.close()
    print(f"Tulemused: {pipeline.RESULTS_PATH} ({len(results['regions'])} piirkonnarida, "
          f"{len(results['listings'])} kuulutust)")
    if args.publish:
        pipeline.publish(pipeline.ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
