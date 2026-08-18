#!/usr/bin/env python3
"""Turn the wrdata CSVs of verification/decks/<tier>/ into the numbers of the
final results table — with the definition of every number printed next to it.

    cd verification/decks/d && ngspice -b ac_msb.spice && ngspice -b ac_lsb.spice \\
        && ngspice -b s22.spice && ngspice -b balance.spice && ngspice -b dc.spice \\
        && ngspice -b bias.spice && ngspice -b eye.spice
    python ../../extract.py d            # all numbers the CSVs allow
    python ../../extract.py d --json     # machine-readable (what verify.py compares)

Only numpy is needed here (no PDK, no ngspice): the formulas are copied
verbatim from layout/codesign/measure_post.py (S-parameters, balance, swing,
power) and report/build_report.py (eye), so a reviewer can read them in one
place. Missing CSVs are simply reported as "not run".
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
S11_BAND_GHZ, S22_BAND_GHZ, BAL_BAND_GHZ = 32.0, 50.0, 48.0


# ---------------------------------------------------------------- definitions (== measure_post.py)
def band_max(f, s, edge_ghz):
    """worst (max) value over f <= edge, INCLUDING the interpolated band edge"""
    inside = s[f <= edge_ghz]
    at_edge = float(np.interp(edge_ghz, f, s))
    return float(max(inside.max() if inside.size else -1e9, at_edge))


def f3db(f, s21, lf):
    """first frequency where S21 drops 3 dB below its 1 GHz value (interpolated)"""
    thr = lf - 3.0
    for i in range(len(f) - 1):
        if s21[i] >= thr > s21[i + 1]:
            return float(np.interp(thr, [s21[i + 1], s21[i]], [f[i + 1], f[i]]))
    return float(f[-1])


def edge(f, s, level=-10.0):
    """frequency up to which s stays below `level` (first upward crossing, interpolated)"""
    for i in range(len(f)):
        if s[i] > level:
            return 0.0 if i == 0 else float(np.interp(level, [s[i - 1], s[i]], [f[i - 1], f[i]]))
    return float(f[-1])


# ---------------------------------------------------------------- eye (== report/build_report.py)
def _levels_at(phase, vv, T, centre, halfwin=0.08):
    win = (np.abs(((phase - centre) + T) % (2 * T) - T) < halfwin * T)
    samp = np.sort(vv[win])
    if samp.size < 8:
        return None
    cut = np.sort(np.argsort(np.diff(samp))[-3:])
    groups = np.split(samp, cut + 1)
    levels = [float(np.mean(g)) for g in groups]
    eyes = [float(groups[i + 1].min() - groups[i].max()) for i in range(3)]
    return levels, eyes


def eye_metrics(t, v, t0_ns, baud):
    """fold into 2 UI; eye centre = circular mean of the phases whose min opening is
    within 50 % of the maximum; cluster a ±8 % UI window there into 4 levels;
    RLM = 3·min(spacing)/Σ(spacing); openings = gap between neighbouring clusters"""
    T = 1.0 / baud
    t_an0 = t0_ns * 1e-9 + 6 * T
    m = t >= t_an0
    tt, vv = t[m], v[m]
    phase = (tt - t_an0) % (2 * T)
    cs = np.linspace(0, T, 120, endpoint=False)
    ops = np.array([min(r[1]) if (r := _levels_at(phase, vv, T, c)) is not None else -np.inf for c in cs])
    good = ops > 0.5 * ops.max()
    ang = 2 * np.pi * cs[good] / T
    centre = float((np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()) % (2 * np.pi)) / (2 * np.pi) * T)
    levels, eyes = _levels_at(phase, vv, T, centre)
    amps = np.diff(levels)
    return dict(eye_levels_v=levels, eye_openings_v=eyes, eye_min_v=float(min(eyes)),
                eye_vpp=float(vv.max() - vv.min()), eye_rlm=float(3 * amps.min() / amps.sum()))


# ---------------------------------------------------------------- extraction
def load(d, name):
    p = os.path.join(d, name)
    return np.loadtxt(p) if os.path.exists(p) else None


def extract(tier: str, deck_dir: str | None = None, verbose: bool = True) -> dict:
    d = deck_dir or os.path.join(HERE, "decks", tier)
    meta = json.load(open(os.path.join(d, "meta.json")))
    out: dict = {}
    say = (lambda *a: print(*a)) if verbose else (lambda *a: None)
    say(f"== tier {tier}: {meta['label']}   (decks: {os.path.relpath(d)})")
    ac = {}
    for drv in ("lsb", "msb"):
        a = load(d, f"ac_{drv}.csv")
        if a is None:
            say(f"   ac_{drv}.csv: not run"); continue
        f, s21, s11 = a[:, 0] / 1e9, a[:, 1], a[:, 3]
        lf = float(s21[np.argmin(np.abs(f - 1.0))])
        ac[drv] = dict(gain=lf, bw=f3db(f, s21, lf), s11=band_max(f, s11, S11_BAND_GHZ), s11_edge=edge(f, s11))
        out[f"{drv}_gain"] = lf; out[f"bw_{drv}"] = ac[drv]["bw"]; out[f"s11_{drv}"] = ac[drv]["s11"]
        say(f"   {drv}_gain = S21({drv} drive) at 1 GHz              = {lf:8.3f} dB")
        say(f"   bw_{drv}   = f where S21 = gain-3 dB (interp.)      = {ac[drv]['bw']:8.2f} GHz")
        say(f"   s11_{drv}  = max S11 over f<=32 GHz incl. edge      = {ac[drv]['s11']:8.3f} dB   (edge {ac[drv]['s11_edge']:.2f} GHz)")
    if len(ac) == 2:
        out["weight"] = ac["msb"]["gain"] - ac["lsb"]["gain"]
        out["bw"] = min(ac["lsb"]["bw"], ac["msb"]["bw"])
        out["s11"] = max(ac["lsb"]["s11"], ac["msb"]["s11"])
        out["s11_edge_ghz"] = min(ac["lsb"]["s11_edge"], ac["msb"]["s11_edge"])
        say(f"   weight    = msb_gain - lsb_gain                    = {out['weight']:8.3f} dB")
        say(f"   bw        = min(bw_lsb, bw_msb)                    = {out['bw']:8.2f} GHz")
        say(f"   s11       = max(s11_lsb, s11_msb)                  = {out['s11']:8.3f} dB")
        say(f"   s11_edge  = min over paths of the -10 dB crossing  = {out['s11_edge_ghz']:8.2f} GHz")
    a = load(d, "s22.csv")
    if a is None:
        say("   s22.csv: not run")
    else:
        f, s22 = a[:, 0] / 1e9, a[:, 1]
        out["s22"] = band_max(f, s22, S22_BAND_GHZ); out["s22_edge_ghz"] = edge(f, s22)
        say(f"   s22       = max S22 over f<=50 GHz incl. edge      = {out['s22']:8.3f} dB")
        say(f"   s22_edge  = -10 dB crossing (interp.)              = {out['s22_edge_ghz']:8.2f} GHz")
    a = load(d, "balance.csv")
    if a is None:
        say("   balance.csv: not run")
    else:
        f = a[:, 0] / 1e9
        gp, gn, php, phn, cm, dd = a[:, 1], a[:, 3], a[:, 5], a[:, 7], a[:, 9], a[:, 11]
        gimb, pimb, cml = gp - gn, (php - phn) % 360.0 - 180.0, cm - dd
        inb = f <= BAL_BAND_GHZ
        out["pn_gain_imb_db"] = float(np.abs(gimb[inb]).max())
        out["pn_phase_imb_deg"] = float(np.abs(pimb[inb]).max())
        out["cm_leak_dbc"] = band_max(f, cml, BAL_BAND_GHZ)
        say(f"   pn_gain_imb  = max |dB(Vp)-dB(Vn)|, f<=48 GHz     = {out['pn_gain_imb_db']:8.3f} dB")
        say(f"   pn_phase_imb = max |(ph(Vp)-ph(Vn)) mod 360 - 180| = {out['pn_phase_imb_deg']:8.3f} deg")
        say(f"   cm_leak      = max dB|Vp+Vn| - dB|Vp-Vn|, <=48 GHz = {out['cm_leak_dbc']:8.2f} dBc")
    a = load(d, "dc.csv")
    if a is None:
        say("   dc.csv: not run")
    else:
        vo = a[:, 1]
        out["swing"] = float(vo.max() - vo.min())
        say(f"   swing     = max - min of Vout,diff over the .dc    = {out['swing']:8.3f} Vpp")
    a = load(d, "bias.csv")
    if a is None:
        say("   bias.csv: not run")
    else:
        hold0 = meta["decks"]["bias"]["hold0_ns"]
        icc = float(np.mean(np.abs(a[a[:, 0] >= hold0 * 1e-9, 3])))
        out["power"] = icc * meta["vcc"] * 1e3
        out["ic_ma_per_finger"] = meta["cell"]["tail_ma"] / 2.0 / meta["cell"]["nx"]
        say(f"   power     = mean|I(Vcc)| for t>={hold0:g} ns x {meta['vcc']:g} V  = {out['power']:8.2f} mW")
        say(f"   ic/finger = tail_ma/2/nx = {meta['cell']['tail_ma']:g}/2/{meta['cell']['nx']}      = {out['ic_ma_per_finger']:8.3f} mA")
    # independent-method cross-checks (ngspice built-in `sp` analysis, mixed-mode Sdd)
    a = load(d, "ac_msb_sp.csv")
    if a is not None:
        f, s21, s11 = a[:, 0] / 1e9, a[:, 1], a[:, 3]
        lf = float(s21[np.argmin(np.abs(f - 1.0))])
        out["sp_msb_gain"] = lf; out["sp_bw_msb"] = f3db(f, s21, lf)
        out["sp_s11_msb"] = band_max(f, s11, S11_BAND_GHZ); out["sp_s11_edge_msb"] = edge(f, s11)
        say(f"   [sp] msb_gain / bw_msb / s11_msb / edge (ngspice sp Sdd21, Sdd11) = "
            f"{lf:.3f} dB / {out['sp_bw_msb']:.2f} GHz / {out['sp_s11_msb']:.3f} dB / {out['sp_s11_edge_msb']:.2f} GHz")
    a = load(d, "s22_sp.csv")
    if a is not None:
        f, s22 = a[:, 0] / 1e9, a[:, 1]
        out["sp_s22"] = band_max(f, s22, S22_BAND_GHZ); out["sp_s22_edge_ghz"] = edge(f, s22)
        say(f"   [sp] s22 / edge (ngspice sp Sdd22)                = {out['sp_s22']:.3f} dB / {out['sp_s22_edge_ghz']:.2f} GHz")
    a = load(d, "eye.csv")
    if a is None:
        say("   eye.csv: not run")
    else:
        e = eye_metrics(a[:, 0], a[:, 1], meta["decks"]["eye"]["data_start_ns"], meta["baud_hz"])
        out.update(e)
        say(f"   eye levels = {['%.3f' % x for x in e['eye_levels_v']]} V; openings = {['%.3f' % x for x in e['eye_openings_v']]} V")
        say(f"   eye_min_v = {e['eye_min_v']:.3f} V   eye_rlm = {e['eye_rlm']:.3f}   eye_vpp = {e['eye_vpp']:.3f} V")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tier", choices=list("abcd"))
    ap.add_argument("--dir", help="deck directory (default verification/decks/<tier>)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = extract(a.tier, a.dir, verbose=not a.json)
    if a.json:
        json.dump(out, sys.stdout, indent=1)
        print()


if __name__ == "__main__":
    main()
