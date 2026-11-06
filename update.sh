#!/usr/bin/env bash
# Daily refresh: scrape today's snapshot, rebuild index.html, commit and push so GitHub Pages republishes.
# Run by the systemd user timer aa-update.timer (~/.config/systemd/user/aa-update.{service,timer}):
#
#   systemctl --user list-timers aa-update.timer   # next/last run
#   systemctl --user start aa-update.service       # run now
#   journalctl --user -u aa-update.service -e      # logs
set -euo pipefail
cd "$(dirname "$0")"
PY=/usr/bin/python3
today=$(date +%F)

$PY scrape.py
snap="data/models_$today.json"

# don't publish a broken page if the site changed shape and the scrape came back (nearly) empty
$PY - "$snap" <<'EOF'
import json, sys
models = json.load(open(sys.argv[1]))["models"]
scored = sum(m.get("intelligence_index") is not None for m in models)
print(f"sanity check: {len(models)} models, {scored} scored")
if len(models) < 300 or scored < 50:
    sys.exit("scrape looks incomplete, not publishing")
EOF

$PY build.py

# raw pages are only needed for --offline re-parsing; keep two weeks
find data/raw -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +

paths=(index.html "$snap" "data/models_$today.csv")
git add -- "${paths[@]}"
if git diff --cached --quiet -- "${paths[@]}"; then
    echo "no changes to publish"
    exit 0
fi
git commit -q -m "Update snapshot $today" -- "${paths[@]}"
git pull -q --rebase --autostash
git push -q
echo "published snapshot $today"
