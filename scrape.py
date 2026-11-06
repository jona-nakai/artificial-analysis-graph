"""Snapshot every model on artificialanalysis.ai with its Intelligence Index, time per task, cost and other metadata.

Most model pages (/models/<slug>) embed, as plain JSON in their Next.js payload, the full record of every model in
the catalog for their comparison charts (~730 models, incl. deprecated and older ones; on 2026-11-06 that covered
every model page in the sitemap). Pages of the current headline models instead load that list from an encrypted
data file (which this deliberately does not touch) and embed only ~30 models, so the scraper reads the sitemap and
tries model pages until one carries (nearly) the whole catalog, merging records from every page it fetched. The home
page charts are merged in too, since brand-new models can show up there first. (The /leaderboards/models page holds
a ~280-model subset with identical values.)

Only ~110 models have a current Intelligence Index: older models were not scored on the index's current version.

Raw pages go to data/raw/<date>/; the merged table to data/models_<date>.{csv,json}. Stdlib only:

    python3 scrape.py            # fetch today's snapshot
    python3 scrape.py --offline  # re-parse an already-downloaded snapshot for today (or --date YYYY-MM-DD)
"""
import argparse
import csv
import datetime as dt
import json
import re
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://artificialanalysis.ai"
PAGES = {"home": f"{BASE}/", "sitemap": f"{BASE}/sitemap.xml"}
# model pages known to embed the full catalog, tried first; then sitemap model pages in order
CATALOG_PAGES = ["claude-opus-5-high", "claude-3-opus", "gpt-4o"]
MAX_TRIES = 6
REASONING_LEVELS = {"max", "xhigh", "high", "medium", "low", "minimal", "non-reasoning", "reasoning"}
RECORD = r'\{"id":"[0-9a-f-]{36}","slug":"[^"]+","name":"[^"]+","shortName"'

# top-level record keys handled explicitly; every other numeric scalar is kept as a benchmark score_<key>
HANDLED = {
    "id", "slug", "name", "shortName", "suffix", "chartDefaultSelected", "chartHighlighted", "releaseDate",
    "knowledgeCutoffDate", "isReasoning", "effort", "release", "deprecated", "isOpenWeights", "openSourceCategorization",
    "parameters", "inferenceParametersActiveBillions", "sizeClass", "contextWindowTokens", "licenseName", "licenseUrl",
    "modelWeightsSourceUrl", "microevalsEnabled", "intelligenceIndex", "capabilities", "omniscience",
    "omniscienceAccuracy", "omniscienceHallucinationRate", "price1mInputTokens", "price1mOutputTokens", "cacheHitPrice",
    "cacheHitDiscountPercent", "cacheWritePrice", "pricePer1k1mpImages", "price1mBlended0To3To1",
    "price1mBlended7To2To1", "price1mBlended0To1To1", "price1mBlended100To1To1", "price1mBlended0To100To1",
    "intelligenceIndexTimePerTask", "intelligenceIndexCost", "intelligenceIndexCostPerTask",
    "canonicalIntelligenceIndexTokenCount", "intelligenceIndexOutputTokensPerTask", "intelligenceIndexEvaluations",
    "briefcaseTotalCost", "headline", "multiTurn", "workloads", "endToEndTime", "performanceDataSource",
    "priceDataSource", "hostModelCount", "creator", "score",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (jadu data-analytics snapshot)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8")


def next_payload(html: str) -> str:
    """Concatenate the self.__next_f.push([1, "..."]) chunks back into the RSC payload text."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    return "".join(json.loads(f'"{c}"') for c in chunks)


def records(payload: str) -> dict[str, dict]:
    """Every model record in the payload, keeping the fullest copy of each (charts embed trimmed copies too)."""
    dec, out = json.JSONDecoder(), {}
    for m in re.finditer(RECORD, payload):
        r = dec.raw_decode(payload, m.start())[0]
        if len(r) > len(out.get(r["slug"], {})):
            out[r["slug"]] = r
    return out


def snake(key: str) -> str:
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", key).lower()


def split_name(name: str) -> tuple[str, str | None]:
    """'GPT-6 Astra (Max)' -> ('GPT-6 Astra', 'Max')."""
    m = re.match(r"^(.*?)\s*\(([^()]*)\)$", name)
    return (m.group(1), m.group(2)) if m else (name, None)


def level_of(r: dict, variant: str | None) -> str | None:
    effort = (r.get("effort") or {}).get("slug")
    if effort:
        return effort.lower()
    if variant:
        first = variant.split(",")[0].strip().lower()
        if first in REASONING_LEVELS:
            return first
    return "non-reasoning" if r.get("isReasoning") is False else None


def row_of(r: dict) -> dict:
    base, variant = split_name(r["name"])
    rel, cre = r.get("release") or {}, r.get("creator") or {}
    cost = (r.get("intelligenceIndexCostPerTask") or {}).get("cost") or {}
    toks = r.get("intelligenceIndexOutputTokensPerTask") or {}
    head = r.get("headline") or {}
    tpt = r.get("intelligenceIndexTimePerTask")
    row = {
        "slug": r["slug"], "name": r["name"], "base_model": rel.get("name") or base, "variant": r.get("suffix") or variant,
        "reasoning_level": level_of(r, variant), "creator": cre.get("name"), "creator_color": cre.get("color"),
        "creator_country": cre.get("country"), "is_reasoning": r.get("isReasoning"),
        "is_open_weights": r.get("isOpenWeights"), "open_source_category": r.get("openSourceCategorization"),
        "license": r.get("licenseName"), "deprecated": r.get("deprecated"), "deprecated_to": rel.get("deprecatedTo"),
        "release_date": r.get("releaseDate"), "knowledge_cutoff": r.get("knowledgeCutoffDate"),
        "parameters_b": r.get("parameters"), "active_parameters_b": r.get("inferenceParametersActiveBillions"),
        "size_class": r.get("sizeClass"), "context_window_tokens": r.get("contextWindowTokens"),
        "intelligence_index": r.get("intelligenceIndex"),
        "omniscience": r.get("omniscience"), "omniscience_accuracy": r.get("omniscienceAccuracy"),
        "hallucination_rate": r.get("omniscienceHallucinationRate"),
        "time_per_task_min": None if tpt is None else tpt / 60,
        "cost_per_task_usd": cost.get("total"), "cost_per_task_input_usd": cost.get("input"),
        "cost_per_task_cache_read_usd": cost.get("cacheRead"), "cost_per_task_cache_write_usd": cost.get("cacheWrite"),
        "cost_per_task_output_usd": cost.get("output"), "cost_per_task_reasoning_usd": cost.get("reasoning"),
        "cost_per_task_answer_usd": cost.get("answer"),
        "output_tokens_per_task": toks.get("output"), "reasoning_tokens_per_task": toks.get("reasoning"),
        "answer_tokens_per_task": toks.get("answer"),
        "price_input_usd_per_1m": r.get("price1mInputTokens"), "price_output_usd_per_1m": r.get("price1mOutputTokens"),
        "price_blended_3to1_usd_per_1m": r.get("price1mBlended0To3To1"),
        "price_cache_hit_usd_per_1m": r.get("cacheHitPrice"), "price_cache_write_usd_per_1m": r.get("cacheWritePrice"),
        "output_speed_tok_s": head.get("outputSpeed"), "ttft_s": head.get("timeToFirstToken"),
        "ttfat_s": head.get("timeToFirstAnswerToken"), "end_to_end_time_s": r.get("endToEndTime"),
        "performance_source": (r.get("performanceDataSource") or {}).get("providerName"),
        "host_model_count": r.get("hostModelCount"),
    }
    # multimodal = accepts at least one input besides text (AA has no "multimodal" label of its own, only these flags)
    ins = [m for m in ("text", "image", "speech", "video") if r.get(f"inputModality{m.title()}")]
    outs = [m for m in ("text", "image", "speech", "video") if r.get(f"outputModality{m.title()}")]
    row["input_modalities"] = ", ".join(ins) or None
    row["output_modalities"] = ", ".join(outs) or None
    row["is_multimodal"] = any(m != "text" for m in ins) if ins else None
    for k, v in (r.get("capabilities") or {}).items():
        row[f"capability_{snake(k)}"] = v
    for k, v in r.items():
        if k.startswith(("inputModality", "outputModality")):
            row[snake(k)] = v
        elif k not in HANDLED and isinstance(v, (int, float)) and not isinstance(v, bool):
            row[f"score_{snake(k)}"] = v
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--offline", action="store_true", help="parse the saved raw pages instead of fetching")
    args = ap.parse_args()

    raw = HERE / "data" / "raw" / args.date
    raw.mkdir(parents=True, exist_ok=True)

    def page(name: str, url: str) -> str:
        path = raw / name
        if not args.offline and not path.exists():
            path.write_text(fetch(url))
            time.sleep(1)  # be polite
        return path.read_text()

    recs = {}
    def merge(found: dict):
        for slug, r in found.items():
            if len(r) > len(recs.get(slug, {})):
                recs[slug] = r

    sitemap = page("sitemap.xml", PAGES["sitemap"])
    site_models = list(dict.fromkeys(re.findall(r"<loc>https://artificialanalysis\.ai/models/([a-z0-9-]+)</loc>", sitemap)))
    merge(records(next_payload(page("home.html", PAGES["home"]))))
    tried = []
    candidates = CATALOG_PAGES + [s for s in site_models if s not in CATALOG_PAGES]
    if args.offline:  # only what is on disk
        candidates = [p.stem.removeprefix("model_") for p in sorted(raw.glob("model_*.html"))]
    for slug in candidates[:MAX_TRIES]:
        try:
            found = records(next_payload(page(f"model_{slug}.html", f"{BASE}/models/{slug}")))
        except Exception as e:  # a page that moved or 404s: try the next one
            print(f"  {slug}: {e}")
            continue
        merge(found)
        tried.append(f"{slug} ({len(found)})")
        if len(found) >= 0.9 * len(site_models):  # this page carries (nearly) the whole catalog
            break
    print("model pages read:", ", ".join(tried), f"| sitemap lists {len(site_models)} model URLs")
    missing = [s for s in site_models if s not in recs]
    if missing:
        print(f"  {len(missing)} sitemap model URLs have no record (often non-model pages):", ", ".join(missing[:12]))

    rows = sorted((row_of(r) for r in recs.values()), key=lambda r: -(r.get("intelligence_index") or -1))
    pages = set(site_models)
    for r in rows:  # link to the model's own AA page when the sitemap has one
        r["aa_url"] = f"{BASE}/models/{r['slug']}" if r["slug"] in pages else None
    out = HERE / "data" / f"models_{args.date}"
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with open(f"{out}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    Path(f"{out}.json").write_text(json.dumps({"snapshot_date": args.date, "source": PAGES, "models": rows}, indent=1))

    scored = [r for r in rows if r.get("intelligence_index") is not None]
    timed = [r for r in scored if r.get("time_per_task_min") is not None]
    print(f"{len(rows)} models, {len(scored)} with an Intelligence Index, {len(timed)} also with time per task, "
          f"{sum(r['intelligence_index'] >= 30 for r in scored)} scoring >= 30 -> {out}.csv")


if __name__ == "__main__":
    main()
