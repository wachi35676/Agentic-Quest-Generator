#!/usr/bin/env bash
# End-to-end batch runner. Headless Godot drives N sessions per profile,
# then the Python harness aggregates metrics. No human input needed.
#
#   bash tools/eval/run_all.sh           # default N=15 per profile
#   N=2 bash tools/eval/run_all.sh       # quick smoke test (8 sessions)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GODOT="${GODOT:-/c/Users/wasif/Downloads/Godot_v4.6.2-stable_win64.exe/Godot_v4.6.2-stable_win64_console.exe}"
N="${N:-15}"
PROFILES=("aggressive" "cautious" "explorer" "completionist")

if [[ ! -x "$GODOT" && ! -f "$GODOT" ]]; then
    echo "ERROR: Godot not found at $GODOT (override with GODOT=...)" >&2
    exit 2
fi

cd "$ROOT"

# Where Godot's user:// resolves to on Windows.
USER_DIR="${APPDATA:-$HOME/.local/share}/Godot/app_userdata/Agentic Quest Generator"
EVAL_DIR="$USER_DIR/eval"

# Fresh slate so we don't aggregate over stale jsonls.
mkdir -p "$EVAL_DIR" tools/eval/sessions tools/eval/results
rm -f "$EVAL_DIR"/*.jsonl 2>/dev/null || true
rm -f tools/eval/sessions/*.jsonl 2>/dev/null || true

total=$(( N * ${#PROFILES[@]} ))
i=0
for profile in "${PROFILES[@]}"; do
    for run in $(seq 1 "$N"); do
        i=$(( i + 1 ))
        echo "[$i/$total] profile=$profile run=$run"
        AGQ_EVAL=1 AGQ_PROFILE="$profile" \
            "$GODOT" --headless --path . res://scenes/EvalSession.tscn \
            >/tmp/eval_run.log 2>&1 || {
                echo "  session crashed (exit $?), continuing"
            }
        # Brief sleep so the file handle flushes and the next session
        # gets a unique timestamp-based id.
        sleep 1
    done
done

# Copy artifacts into the repo so results travel with the project.
cp -f "$EVAL_DIR"/*.jsonl tools/eval/sessions/ 2>/dev/null || true
cp -f "$EVAL_DIR"/entities.json tools/eval/ 2>/dev/null || true

echo
echo "Aggregating metrics..."
python tools/eval/runner.py \
    --in tools/eval/sessions \
    --out tools/eval/results \
    --entities tools/eval/entities.json

echo
echo "Done. See tools/eval/results/{results.json, results.csv, summary.json, summary_per_profile.json, headline.json}"
