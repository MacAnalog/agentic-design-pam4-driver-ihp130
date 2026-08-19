#!/usr/bin/env python3
"""Post-layout MEASURE hook of the PAM-4 driver co-design flow.

`spicexplorer.backends.layout` (``sim_engine: layout``) runs this module in
the repo's own venv after build -> DRC -> LVS -> kpex, handing it ONE JSON
request on stdin (``spicexplorer_layout.measure_protocol``):

    params      the candidate LayoutParams (electrical sizing knobs included:
                nx, re/rc/rb_ohm, cdeg_ff — they draw geometry)
    deck_params bench-only knobs: tail_ma, vcasc (the tail current source and
                the cascode bias live in the testbench, as in the schematic DUTs)
    pex_netlist the raw kpex netlist of this trial's GDS

and returns the block's full post-layout scorecard as flat scalars — the
SAME eight signoff metrics notebook 03 reports, measured by the SAME
`driver_lib` benches on the converted extracted netlist:

    lsb_gain, msb_gain (dB @1 GHz)   weight (dB)   bw (GHz, worst path)
    s11 (dB, worst path, <=32 GHz)   s11_edge_ghz (-10 dB crossing)
    s22 (dB, <=50 GHz)               s22_edge_ghz
    swing (Vpp diff)                 power (mW @ 4 V)
    pn_gain_imb_db / pn_phase_imb_deg / cm_leak_dbc (MSB path p/n balance
    up to 48 GHz: |gain| and |phase| imbalance, diff->CM conversion)
    plus s11_lsb / s11_msb / bw_lsb / bw_msb, ic_ma_per_finger (model-card
    validity: I_C < 3 mA per emitter finger) and n_parasitics.

Hand-run:  echo '{"pex_netlist": ".../x_k25d_pex_netlist.spice", "work_dir":
".", "params": {...}, "deck_params": {"tail_ma": 15}}' | python measure_post.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))                  # layout/
sys.path.insert(0, os.path.join(HERE, "..", "..", "testbenches"))
import driver_lib as dl  # noqa: E402
import gen_layout  # noqa: E402
import pex_sim  # noqa: E402

DUT = gen_layout.CODESIGN_DUT
DEFAULT_BIAS = {"tail_ma": 15.0, "vcasc": 3.35, "vcc": 4.0}
S11_BAND_GHZ, S22_BAND_GHZ = 32.0, 50.0
BAL_BAND_GHZ = 48.0    # p/n balance audited up to the symbol rate
AC_PTS_PER_DEC = 100     # r2: 20 -> 100 (grid 10^(k/20) skips 32 & 50 GHz)


def _band_max(f: np.ndarray, s: np.ndarray, edge_ghz: float) -> float:
    """Worst (max) value over the band, INCLUDING the exact band edge by
    interpolation. r1's `s[f <= edge].max()` on the ngspice `dec 20` grid
    never sampled 32 / 50 GHz (last points 31.62 / 44.67 GHz) and read S22
    ~0.9 dB too good (rf-layout-reviewer, 2026-08-18) — the block's own
    run_verify.py spot points (2/10/20/32/40/50 GHz) are the reference."""
    inside = s[f <= edge_ghz]
    at_edge = float(np.interp(edge_ghz, f, s))
    return float(max(inside.max() if inside.size else -1e9, at_edge))


def _f3db(f: np.ndarray, s21: np.ndarray, lf: float) -> float:
    thr = lf - 3.0
    for i in range(len(f) - 1):
        if s21[i] >= thr > s21[i + 1]:
            return float(np.interp(thr, [s21[i + 1], s21[i]], [f[i + 1], f[i]]))
    return float(f[-1])


def _edge(f: np.ndarray, s: np.ndarray, level: float = -10.0) -> float:
    """Frequency up to which s stays below `level`: the first upward crossing,
    interpolated between grid points (grid-independent)."""
    for i in range(len(f)):
        if s[i] > level:
            if i == 0:
                return 0.0
            return float(np.interp(level, [s[i - 1], s[i]], [f[i - 1], f[i]]))
    return float(f[-1])


def measure(req: dict) -> dict[str, float]:
    params = dict(req["params"])
    deck = dict(DEFAULT_BIAS, **(req.get("deck_params") or {}))
    work = req["work_dir"]
    p = gen_layout.LayoutParams(**params)
    # kpex raw netlist -> ngspice-runnable subckt (Q/R/C -> PDK X-cards,
    # intentional MIM caps re-inserted between the RE emitter nets)
    post = os.path.join(work, f"dut_{DUT}_post.spice")
    pex_sim.convert_pex_netlist(req["pex_netlist"], post,
                                cap=pex_sim.cap_reinsert_args(p))
    ref = pex_sim.wrap_layout_dut(DUT, post)
    dp = dl.DriverParams(vcc=float(deck["vcc"]), cell=dl.CellParams(
        nx=int(p.nx), tail_ma=float(deck["tail_ma"]), re_ohm=float(p.re_ohm),
        cdeg_ff=float(p.cdeg_ff), rc_ohm=float(p.rc_ohm),
        rb_ohm=float(p.rb_ohm), vcasc=float(deck["vcasc"])))
    m: dict[str, float] = {}
    ac = {}
    for drv in (("lsb", "msb") if DUT == "pam4" else ("in",)):
        r = dl.run_ac(DUT, drive=drv, dp=dp, dut_ref=ref, timeout_s=900,
                      pts_per_dec=AC_PTS_PER_DEC)
        if not r["ok"]:
            raise RuntimeError(f"AC {drv} failed: {r.get('log', '')[-1500:]}")
        f, s21, s11 = r["f_ghz"], r["s21_db"], r["s11_db"]
        lf = float(s21[np.argmin(np.abs(f - 1.0))])
        ac[drv] = dict(gain=lf, bw=_f3db(f, s21, lf),
                       s11=_band_max(f, s11, S11_BAND_GHZ),
                       s11_edge=_edge(f, s11))
    if DUT == "pam4":
        m["lsb_gain"], m["msb_gain"] = ac["lsb"]["gain"], ac["msb"]["gain"]
        m["weight"] = ac["msb"]["gain"] - ac["lsb"]["gain"]
    else:
        m["msb_gain"] = ac["in"]["gain"]
    m["bw"] = min(v["bw"] for v in ac.values())
    m["s11"] = max(v["s11"] for v in ac.values())
    m["s11_edge_ghz"] = min(v["s11_edge"] for v in ac.values())
    for drv, v in ac.items():
        m[f"s11_{drv}"], m[f"bw_{drv}"] = v["s11"], v["bw"]
    r22 = dl.run_ac_s22(DUT, dp=dp, dut_ref=ref, timeout_s=900,
                        pts_per_dec=AC_PTS_PER_DEC)
    if not r22["ok"]:
        raise RuntimeError(f"S22 failed: {r22.get('log', '')[-1500:]}")
    f22, s22 = r22["f_ghz"], r22["s22_db"]
    m["s22"] = _band_max(f22, s22, S22_BAND_GHZ)
    m["s22_edge_ghz"] = _edge(f22, s22)
    # p/n balance (matching audit, added after r2): worst |gain imbalance|,
    # |phase imbalance| and diff->CM conversion of the MSB path up to the
    # symbol rate (48 GBd) — a layout asymmetry (per-net bus extents, one
    # output on another metal) is scored here, not hidden in the differential S21.
    # r3: the MSB-path numbers stay the SCORED ones (`pn_*` / `cm_leak_dbc`);
    # the LSB path is measured too and reported unscored (`*_lsb`) so a round
    # that buys MSB balance by giving back LSB balance is visible in R.
    for drv in (("msb", "lsb") if DUT == "pam4" else ("in",)):
        rb = dl.run_ac_balance(DUT, drive=drv, dp=dp, dut_ref=ref,
                               timeout_s=900, pts_per_dec=AC_PTS_PER_DEC)
        if not rb["ok"]:
            raise RuntimeError(f"balance {drv} failed: {rb.get('log', '')[-1500:]}")
        fb = rb["f_ghz"]
        inb = fb <= BAL_BAND_GHZ
        sfx = "" if drv in ("msb", "in") else f"_{drv}"
        m[f"pn_gain_imb_db{sfx}"] = float(np.abs(rb["gain_imb_db"][inb]).max())
        m[f"pn_phase_imb_deg{sfx}"] = float(np.abs(rb["phase_imb_deg"][inb]).max())
        m[f"cm_leak_dbc{sfx}"] = _band_max(fb, rb["cm_leak_dbc"], BAL_BAND_GHZ)
    d = dl.run_dc(DUT, drive="both", vd_max_mv=900.0, step_mv=15.0, dp=dp,
                  dut_ref=ref, timeout_s=900)
    if not d["ok"]:
        raise RuntimeError(f"DC failed: {d.get('log', '')[-1500:]}")
    m["swing"] = float(d["vout_diff_v"].max() - d["vout_diff_v"].min())
    deck_txt, hold0, _ = dl.tb_bias(DUT, ref, dp=dp,
                                    probes=["v(outp)", "i(Vcc)"])
    out, log = dl.run_deck(deck_txt, ["bias.csv"], timeout_s=600)
    data = out["bias.csv"]
    if data is None:
        raise RuntimeError(f"bias failed: {log[-1500:]}")
    icc = float(np.mean(np.abs(data[data[:, 0] >= hold0 * 1e-9, 3])))
    m["power"] = icc * float(deck["vcc"]) * 1e3
    m["ic_ma_per_finger"] = float(deck["tail_ma"]) / 2.0 / int(p.nx)
    m["n_parasitics"] = float(sum(1 for l in open(post)
                                  if l[:1] in ("C", "R")))
    return {k: float(v) for k, v in m.items()}


if __name__ == "__main__":
    from spicexplorer_layout.measure_protocol import serve
    raise SystemExit(serve(measure))
