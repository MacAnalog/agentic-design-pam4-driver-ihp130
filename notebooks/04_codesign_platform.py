# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # PAM-4 driver — layout/schematic co-design through the SpiceXplorer platform
#
# The TCAS-2026 paper's Algorithm 1 (layout-in-the-loop co-design) run **through
# `spicexplorer-optimize` with `sim_engine: layout`** — one trial = gdsfactory build →
# KLayout DRC → LVS → kpex → the block's own `driver_lib` benches on the extracted
# netlist. The agent (`layout-schematic-codesign`) owns the generator `G`
# (`layout/gen_layout.py`) and the knob bounds (`layout/codesign/project_setup.yaml`);
# the platform owns the search. This notebook only READS the committed record
# `layout/codesign/results/<round>/` — nothing here re-runs the optimizer (the rounds
# table in `layout/codesign/README.md` says how each round was launched).
#
# What it shows: per-round trial scatter (score / feasibility / skip rate), which knobs
# moved, the round-by-round scorecard next to the layout of record and the paper's
# table, and the before/after + annotated-parameterized-layout figures.

# %%
import glob
import json
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import Image, display

HERE = os.path.dirname(os.path.abspath("__file__")) if "__file__" not in globals() else os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CD = os.path.join(ROOT, "layout", "codesign")
ROUNDS = sorted(os.path.basename(d) for d in glob.glob(os.path.join(CD, "results", "r*")))
print("rounds on record:", ROUNDS)

# %% [markdown]
# ## 1. The record `R` — every trial of every round
#
# `trials.jsonl` = one line per trial (params, scalars, status, per-stage seconds, the
# feasibility-reward score recomputed with the round's own spec table). Status:
# `ok` = full flow ran, `drc_fail` / `lvs_fail` = skipped by the gate (Alg. 1 line 5),
# `build_fail` = the generator refused the point (its DRC-safety guards).

# %%
rows = []
for r in ROUNDS:
    for line in open(os.path.join(CD, "results", r, "trials.jsonl")):
        d = json.loads(line)
        rows.append(dict(round=r, run=d.get("run"), status=d.get("status"), feasible=d.get("feasible"),
                         score=d.get("score"), secs=d.get("scalars", {}).get("total_secs"),
                         **{k: d.get("scalars", {}).get(k) for k in ("s11", "s22", "msb_gain", "lsb_gain", "bw", "swing", "power", "area_um2")},
                         **{f"p_{k}": v for k, v in d.get("params", {}).items() if isinstance(v, (int, float))}))
T = pd.DataFrame(rows)
summary = (T.groupby("round").agg(trials=("run", "size"), ok=("status", lambda s: (s == "ok").sum()),
                                  drc_skip=("status", lambda s: (s == "drc_fail").sum()),
                                  build_fail=("status", lambda s: (s == "build_fail").sum()),
                                  feasible=("feasible", "sum"), sec_per_trial=("secs", "median")))
summary["skip_rate_%"] = (100 * (summary.drc_skip + summary.build_fail) / summary.trials).round(0)
summary

# %%
fig, axs = plt.subplots(1, len(ROUNDS), figsize=(6 * len(ROUNDS), 4), squeeze=False)
for ax, r in zip(axs[0], ROUNDS):
    t = T[(T["round"] == r) & (T.status == "ok")]
    sc = ax.scatter(t.s11, t.s22, c=np.where(t.feasible, "tab:green", "tab:gray"), s=18)
    ax.axvline(-10, color="k", lw=0.6, ls="--"); ax.axhline(-10, color="k", lw=0.6, ls="--")
    ax.set_xlabel("S11 worst ≤32 GHz (dB)"); ax.set_ylabel("S22 worst ≤50 GHz (dB)")
    ax.set_title(f"{r}: {len(t)} evaluated trials (green = all 8 specs + gates met)")
    ax.invert_xaxis(); ax.invert_yaxis()
plt.tight_layout()

# %% [markdown]
# ## 2. Round-by-round scorecard
#
# The instrument matters: round 1 read the worst in-band S-parameter on the ngspice
# `dec 20` grid, whose last in-band points are 31.62 / 44.67 GHz; from round 2 on the
# hook interpolates the exact 32 / 50 GHz edges (the paper's table and the block's
# `run_verify.py` spot points) and kpex runs with a 20 µm sidewall halo. The layout of
# record re-measured with the round-2 instrument is the honest baseline.

# %%
cards = {}
for r in ROUNDS:
    s = json.load(open(os.path.join(CD, "results", r, "summary.json")))
    cards[f"{r} best"] = s["best"]["scalars"] | {"instrument": s.get("instrument", "")}
base = os.path.join(CD, "results", "baseline_r2_instrument.json")
if os.path.exists(base):
    cards = {"layout of record (r2 instrument)": json.load(open(base))} | cards
SPEC = [("s11", "≤ −10"), ("s22", "≤ −10"), ("msb_gain", "≥ 8.2"), ("lsb_gain", "≥ 2.2"), ("weight", "≥ 5"),
        ("bw", "≥ 50"), ("swing", "≥ 2.1"), ("power", "≤ 192"), ("area_um2", "(paper 11 300)")]
tab = pd.DataFrame({k: {m: round(v.get(m, float("nan")), 2) for m, _ in SPEC} for k, v in cards.items()})
tab.insert(0, "spec", [s for _, s in SPEC])
tab

# %% [markdown]
# ## 3. Which knobs moved (accepted round vs the layout of record)

# %%
last = ROUNDS[-1]
best = json.load(open(os.path.join(CD, "results", last, "summary.json")))["best"]["params"]
import sys
sys.path.insert(0, os.path.join(ROOT, "layout"))
import gen_layout
import dataclasses
p0 = dataclasses.asdict(gen_layout.LayoutParams(**gen_layout.V2_LAYOUT))   # the layout of record before the co-design rounds
moved = {k: (p0.get(k), v) for k, v in best.items() if k in p0 and p0.get(k) != v}
pd.DataFrame(moved, index=["layout of record", f"{last} best"]).T

# %% [markdown]
# ## 4. Figures — the parameterized layout, before/after, and the round strip
#
# All drawn from the GDS by `layout/codesign/figures.py` (annotation positions come from
# the generator's own geometry record, so they cannot drift from the layout).

# %%
for f in ("pam4_layout_annotated.png", "before_after.png", "rounds.png"):
    pth = os.path.join(CD, f)
    if os.path.exists(pth):
        print(f)
        display(Image(pth, width=1000))

# %% [markdown]
# ## 5. v2 → v4 through the block's own benches (independent of the co-design hook)
#
# The committed post-layout netlists (`layout/out/pex/dut_pam4_best_post.spice`
# = v2, `layout/out/pex/dut_pam4_post.spice` = v4 = the layout of record after
# co-design round 3; the round-2 point v3 is tier (d) of `report/layout/`), both kpex CC at the block's
# default halo) run through `driver_lib`'s S-parameter and eye benches exactly as
# notebook 03 does — the sweeps below use `dec 100` so the 32 / 50 GHz band edges
# are on the grid (dotted lines). This is the check that the co-design hook's
# scalars are the same physics as the signoff notebook.

# %%
import random
sys.path.insert(0, os.path.join(ROOT, "testbenches"))
from driver_lib import DriverParams, CellParams, run_ac, run_ac_s22, run_eye
from pex_sim import wrap_layout_dut

def dp_of(bias, re_ohm, cdeg_ff, rc_ohm, rb_ohm):
    return DriverParams(cell=CellParams(nx=3, tail_ma=bias["tail_ma"], re_ohm=re_ohm, cdeg_ff=cdeg_ff,
                                        rc_ohm=rc_ohm, rb_ohm=rb_ohm, vcasc=bias["vcasc"], vcm_in=bias["vcmb"]))

V2 = gen_layout.V2_LAYOUT; V4 = gen_layout.FINAL_LAYOUT
VARIANTS = {
    "v2 (layout of record)": (dp_of(gen_layout.V2_BIASES, V2["re_ohm"], V2["cdeg_ff"], V2["rc_ohm"], V2["rb_ohm"]),
                              wrap_layout_dut("pam4", os.path.join(ROOT, "layout/out/pex/dut_pam4_best_post.spice")), "tab:gray"),
    "v4 (co-design accepted)": (dp_of(gen_layout.FINAL_BIASES, V4["re_ohm"], V4["cdeg_ff"], V4["rc_ohm"], V4["rb_ohm"]),
                                wrap_layout_dut("pam4", os.path.join(ROOT, "layout/out/pex/dut_pam4_post.spice")), "tab:red"),
}

def band_max(f, s, edge):
    m = f <= edge
    v = float(s[m].max())
    if f.max() > edge and not np.isclose(f[m][-1], edge):
        v = max(v, float(np.interp(edge, f, s)))
    return v

AC = {}
for lab, (dp, ref, _) in VARIANTS.items():
    a = {}
    for drv in ("lsb", "msb"):
        r = run_ac("pam4", drive=drv, dp=dp, dut_ref=ref, pts_per_dec=100, timeout_s=900); assert r["ok"], r.get("log", "")[-1500:]
        f, s21, s11 = r["f_ghz"], r["s21_db"], r["s11_db"]
        lf = float(s21[np.argmin(np.abs(f - 1.0))]); thr = lf - 3.0
        f3 = float(f[-1])
        for i in range(len(f) - 1):
            if s21[i] >= thr > s21[i + 1]:
                f3 = float(np.interp(thr, [s21[i + 1], s21[i]], [f[i + 1], f[i]])); break
        a[drv] = dict(f=f, s21=s21, s11=s11, lf=lf, f3db=f3, s11w=band_max(f, s11, 32.0))
    r22 = run_ac_s22("pam4", dp=dp, dut_ref=ref, pts_per_dec=100, timeout_s=900); assert r22["ok"], r22.get("log", "")[-1500:]
    a["s22"] = dict(f=r22["f_ghz"], s22=r22["s22_db"], s22w=band_max(r22["f_ghz"], r22["s22_db"], 50.0))
    AC[lab] = a

fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.8))
for lab, (dp, ref, col) in VARIANTS.items():
    a = AC[lab]
    axes[0].semilogx(a["msb"]["f"], a["msb"]["s21"], color=col, label=lab)
    axes[0].semilogx(a["lsb"]["f"], a["lsb"]["s21"], color=col, ls="--", alpha=0.7)
    axes[1].semilogx(a["msb"]["f"], a["msb"]["s11"], color=col, label=lab)
    axes[2].semilogx(a["s22"]["f"], a["s22"]["s22"], color=col, label=lab)
axes[0].set_title("S21 (solid MSB, dashed LSB)"); axes[0].set_ylabel("dB"); axes[0].set_ylim(-5, 12)
axes[1].set_title("S11 (MSB drive)"); axes[1].axhline(-10, color="k", lw=0.8); axes[1].axvline(32, color="k", lw=0.6, ls=":")
axes[1].set_xlim(1, 100); axes[1].set_ylim(-25, -5)
axes[2].set_title("S22"); axes[2].axhline(-10, color="k", lw=0.8); axes[2].axvline(50, color="k", lw=0.6, ls=":")
axes[2].set_xlim(1, 100); axes[2].set_ylim(-25, -5)
for ax in axes:
    ax.set_xlabel("f [GHz]"); ax.legend(fontsize=7); ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "report_figs", "sparams_v2_v4_post_layout.png"), dpi=130)

pd.DataFrame({lab: {
    "LSB gain [dB]": round(a["lsb"]["lf"], 2), "MSB gain [dB]": round(a["msb"]["lf"], 2),
    "DAC weight [dB]": round(a["msb"]["lf"] - a["lsb"]["lf"], 2),
    "BW LSB / MSB [GHz]": f'{a["lsb"]["f3db"]:.1f} / {a["msb"]["f3db"]:.1f}',
    "S11 worst ≤32 GHz [dB]": round(a["msb"]["s11w"], 2), "S22 worst ≤50 GHz [dB]": round(a["s22"]["s22w"], 2),
} for lab, a in AC.items()}).T

# %% [markdown]
# ### 48 GBaud PAM-4 eye, v4 post-layout (same stimulus as notebook 03 / `run_eye.py`)

# %%
BAUD, NSYM = 48e9, 120
random.seed(7)
msb_bits = [random.randint(0, 1) for _ in range(NSYM)]
lsb_bits = [random.randint(0, 1) for _ in range(NSYM)]

def eye_metrics(t, v, t0_ns, baud):
    T = 1.0 / baud; t_an0 = t0_ns * 1e-9 + 6 * T
    m = t >= t_an0; tt, vv = t[m], v[m]
    phase = (tt - t_an0) % (2 * T)
    win = (phase > T - 0.08 * T) & (phase < T + 0.08 * T)
    samp = np.sort(vv[win]); cut = np.sort(np.argsort(np.diff(samp))[-3:])
    groups = np.split(samp, cut + 1); levels = [float(np.mean(g)) for g in groups]
    eyes = [float(groups[i + 1].min() - groups[i].max()) for i in range(3)]; amps = np.diff(levels)
    return phase, vv, {"vout_pp_v": round(float(vv.max() - vv.min()), 3),
                       "eye_openings_v": [round(e, 3) for e in eyes], "rlm": round(float(3 * amps.min() / amps.sum()), 3)}

lab = "v4 (co-design accepted)"; dp, ref, col = VARIANTS[lab]
t, v, t0, baud, log = run_eye(msb_bits=msb_bits, lsb_bits=lsb_bits, dp=dp, dut_ref=ref, baud_hz=BAUD, vswing_mv=200.0, timeout_s=5400)
assert t is not None, log[-2000:]
phase, vv, met = eye_metrics(t, v, t0, baud)
fig, ax = plt.subplots(figsize=(5, 3.8))
ax.plot(phase * 1e12, vv, ",", color=col, alpha=0.3)
ax.set_title(f"{lab}: PAM-4 eye @ 48 GBaud (RLM {met['rlm']:.3f})", fontsize=10)
ax.set_xlabel("t within 2 UI [ps]"); ax.set_ylabel("V_out differential [V]"); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(os.path.join(HERE, "report_figs", "eye_48gbd_pam4_v4.png"), dpi=130)
met

# %% [markdown]
# ## 6. Take-aways
#
# * The co-design loop is reproducible from two YAML files (`flow.yaml`,
#   `project_setup.yaml`) + the generator; the LLM agent's contribution is the generator
#   options and bounds between rounds — every round's "fix G" event is a commit of
#   `gen_layout.py` and a row of the rounds table.
# * The first thing the loop taught us was about the **instrument**, not the layout:
#   the pre-existing scorecard never sampled the band edges, and the extractor's default
#   sidewall halo put a fake step in the S22 landscape exactly where the optimizer went.
# * The structural options that the round-1 review turned into knobs (`bus_trim`,
#   `sub_bus`, `cell_order`, `c_strip`, `out_split`) are what moved the design from
#   failing both reflection specs (honest baseline) to meeting them; the electrical
#   knobs then trade the remaining BW/power margin. The S22 floor of this floorplan is
#   the cascode junction C (nx=3 at 2.5 mA/finger against the 3 mA model-card limit).
