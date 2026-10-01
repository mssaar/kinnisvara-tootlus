"""Kinnisvara üüritootlus — käsurida.

    python run.py                 kogu kv.ee andmed, salvesta, arvuta tulemused
    python run.py --analyze-only  arvuta tulemused olemasolevast andmebaasist
    python run.py --publish       ... ja tee git commit + push
    python run.py --serve         ava kohalik leht "Käivita uuesti" nupuga
    python run.py --counties 1,2  ainult valitud maakonnad (kv.ee ID-d)
"""
from __future__ import annotations

import argparse
import sys

from tootlus import config, pipeline
from tootlus.store import Store


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="kv.ee korterite üüritootlus piirkondade kaupa")
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--counties", help="komaga eraldatud kv.ee maakonna ID-d, nt 1,12")
    args = parser.parse_args(argv)

    counties = config.COUNTIES
    if args.counties:
        counties = {int(c): config.COUNTIES[int(c)] for c in args.counties.split(",")}

    if args.serve:
        from tootlus.server import serve
        serve(args.port, counties)
        return 0

    pipeline.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = Store(str(pipeline.DB_PATH))
    try:
        if args.analyze_only:
            results = pipeline.analyze_only(store)
        else:
            results = pipeline.run_once(store, counties=counties)
    finally:
        store.close()
    print(f"Tulemused: {pipeline.RESULTS_PATH} ({len(results['regions'])} piirkonnarida, "
          f"{len(results['listings'])} kuulutust)")
    if args.publish:
        pipeline.publish(pipeline.ROOT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
