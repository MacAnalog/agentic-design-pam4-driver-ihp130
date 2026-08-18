#!/usr/bin/env python3
"""Harvest a co-design run (or several islands of one round) into a compact,
committed record: results/<round>/trials.jsonl (one line per trial: params,
scalars, status, score recomputed with the project's own scorer), best.json,
and the best trial's GDS + PNG render.

    uv run python harvest.py --round r1 runs/r1_s0 runs/r1_s1 ...
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

SPECS = {  # name: (goal, target, range, weight, reward)  — mirrors project_setup.yaml
    "s11": ("min", -10.0, 5.0, 10, True), "s22": ("min", -10.0, 5.0, 10, True),
    "area_um2": ("min", 11300.0, 5000.0, 1, True),
    "msb_gain": ("max", 8.2, 1.0, 5, False), "lsb_gain": ("max", 2.2, 1.0, 5, False),
    "weight": ("max", 5.0, 1.0, 5, False), "bw": ("max", 50.0, 10.0, 5, False),
    "swing": ("max", 2.1, 0.2, 5, False), "power": ("min", 192.0, 20.0, 5, False),
    "ic_ma_per_finger": ("min", 3.0, 1.0, 50, False),
    "drc_pass": ("eq", 1, 1, 100, False), "lvs_match": ("eq", 1, 1, 100, False),
    "pex_ok": ("eq", 1, 1, 100, False),
}
MAX_PENALTY = 1e6


def score(sc: dict) -> tuple[float, bool]:
    """feasibility_reward aggregation of project_setup.yaml's specs."""
    pen, rew = 0.0, 0.0
    for name, (goal, t, rng, w, has_reward) in SPECS.items():
        v = sc.get(name)
        if v is None or v != v:
            pen -= MAX_PENALTY
            continue
        if goal == "min":
            viol = max(0.0, v - t)
        elif goal == "max":
            viol = max(0.0, t - v)
        else:
            viol = abs(v - t)
        if viol > 0:
            pen -= w * viol / rng
        elif has_reward:
            rew += w * abs(v - t) / rng
    return (rew if pen > -1e-9 else pen), pen > -1e-9


def load_runs(dirs: list[str]) -> list[dict]:
    rows = []
    for d in dirs:
        for sj in sorted(glob.glob(os.path.join(d, "**", "summary.json"), recursive=True),
                         key=lambda p: int(os.path.basename(os.path.dirname(p)).split("_")[1])):
            s = json.load(open(sj))
            sc = {k: v for k, v in (s.get("scalars") or {}).items()
                  if not (k.startswith("c_") or k.startswith("ctot_"))}
            row = {"island": os.path.basename(os.path.normpath(d)),
                   "run": os.path.basename(os.path.dirname(sj)),
                   "status": s.get("status"), "error": s.get("error"),
                   "params": s.get("params"), "deck_params": s.get("deck_params"),
                   "scalars": sc,
                   "stage_secs": {k: round(v.get("secs", 0), 1) for k, v in (s.get("stages") or {}).items()},
                   "run_dir": os.path.dirname(sj)}
            row["score"], row["feasible"] = score(sc)
            rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", required=True)
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--instrument", default="", help="how the metrics were measured (recorded in summary.json)")
    a = ap.parse_args()
    rows = load_runs(a.dirs)
    out = os.path.join(a.out, a.round)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "trials.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps({k: v for k, v in r.items() if k != "run_dir"}) + "\n")
    ok = [r for r in rows if r["status"] == "ok"]
    feas = [r for r in rows if r["feasible"]]
    best = max(rows, key=lambda r: r["score"]) if rows else None
    summ = {"round": a.round, "instrument": a.instrument, "n_trials": len(rows), "n_ok": len(ok),
            "n_feasible": len(feas),
            "n_status": {s: sum(1 for r in rows if r["status"] == s)
                         for s in sorted({r["status"] for r in rows})},
            "best": {k: v for k, v in best.items() if k != "run_dir"} if best else None}
    json.dump(summ, open(os.path.join(out, "summary.json"), "w"), indent=1)
    if best:
        rd = best["run_dir"]
        for fn in os.listdir(rd):
            if fn.endswith(".gds") and "nomim" not in fn:
                shutil.copy(os.path.join(rd, fn), os.path.join(out, "best.gds"))
            if fn.endswith("_post.spice"):
                shutil.copy(os.path.join(rd, fn), os.path.join(out, "best_post.spice"))
        try:
            import render
            render.render(os.path.join(out, "best.gds"), os.path.join(out, "best.png"))
        except Exception as e:  # noqa: BLE001
            print("render skipped:", e)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
