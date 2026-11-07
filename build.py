"""Build index.html: explorer_template.html with a model snapshot inlined, so the file is fully standalone
(no server, no network) and can be sent to anyone.

Only models scored on the current Intelligence Index (v5) are included, since older models were never re-run on it;
the full catalog stays in data/models_<date>.csv. Pass --all to embed every model anyway.

    python3 build.py                    # newest data/models_<date>.json
    python3 build.py --date 2026-11-06  # a specific snapshot
    python3 build.py --all              # every model, not just the v5-scored ones
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--out", default=str(HERE / "index.html"))
    ap.add_argument("--all", action="store_true", help="include models without a current Intelligence Index")
    args = ap.parse_args()

    snaps = sorted((HERE / "data").glob("models_*.json"))
    src = HERE / "data" / f"models_{args.date}.json" if args.date else snaps[-1]
    snap = json.loads(src.read_text())
    total = len(snap["models"])
    if not args.all:
        snap["models"] = [m for m in snap["models"] if m.get("intelligence_index") is not None]
    snap["catalog_size"], snap["v5_only"] = total, not args.all
    if not snap.get("intelligence_index_version"):  # snapshots from before the scraper recorded it: read the saved pages
        from scrape import index_version
        snap["intelligence_index_version"] = index_version(HERE / "data" / "raw" / snap["snapshot_date"])
    snap["models"] = [{k: v for k, v in m.items() if v is not None} for m in snap["models"]]  # nulls just bloat it
    # inline as a JSON <script> block; escape "</" so no value can close the tag
    blob = json.dumps(snap, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    html = (HERE / "explorer_template.html").read_text().replace("/*__DATA__*/", blob, 1)
    Path(args.out).write_text(html)
    print(f"{src.name} -> {args.out} ({len(html) / 1024:.0f} KB, {len(snap['models'])} of {total} models)")


if __name__ == "__main__":
    main()
