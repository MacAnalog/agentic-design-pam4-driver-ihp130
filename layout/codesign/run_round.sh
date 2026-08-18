#!/usr/bin/env bash
# Launch one island of a co-design round through the SpiceXplorer platform.
#   ./run_round.sh <round> <seed> <budget> [algo] [project_setup.yaml]
# Artifacts: runs/<round>_s<seed>/ (per-trial GDS/DRC/LVS/PEX/measure + summary.json)
# Log:       logs/<round>_s<seed>.log
# The platform checkout is the workspace sibling ../../../../spicexplorer-platform
# (override with SPX_PLATFORM); the block's own venv runs generator + benches.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROUND="${1:?round}"; SEED="${2:?seed}"; BUDGET="${3:?budget}"; ALGO="${4:-TwoPointsDE}"
PROJECT="${5:-$HERE/project_setup.yaml}"
PLATFORM="${SPX_PLATFORM:-$HERE/../../../../spicexplorer-platform}"
mkdir -p "$HERE/runs" "$HERE/logs"
cd "$HERE/logs"
exec uv run --project "$PLATFORM" spicexplorer-optimize "$PROJECT" \
    --budget "$BUDGET" --seed "$SEED" --algo "$ALGO" \
    --outdir "$HERE/runs/${ROUND}_s${SEED}" --no-timestamp --quiet \
    > "$HERE/logs/${ROUND}_s${SEED}.log" 2>&1
