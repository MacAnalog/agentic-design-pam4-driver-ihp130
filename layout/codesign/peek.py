#!/usr/bin/env python3
"""Quick look at the trials of one or more run dirs (status + scorecard + key
knobs), and a leaderboard of the feasible ones under the round's J.

    python3 peek.py runs/r3_s10 runs/r3_s11 ...        # per-trial lines
    python3 peek.py --top 10 runs/r3_s1*               # leaderboard only
"""
import json, glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harvest import score, SPEC_TABLES
import harvest


def r(v, n=2):
    return round(v, n) if isinstance(v, (int, float)) else "-"


def rows(dirs):
    out = []
    for d in dirs:
        for sj in sorted(glob.glob(f"{d}/**/summary.json", recursive=True),
                         key=lambda p: int(os.path.basename(os.path.dirname(p)).split("_")[1])):
            s = json.load(open(sj))
            s["island"] = os.path.basename(os.path.normpath(d))
            s["run"] = os.path.basename(os.path.dirname(sj))
            sc = {k: v for k, v in s["scalars"].items()
                  if not (k.startswith("c_") or k.startswith("ctot_"))}
            s["sc"] = sc
            s["score"], s["feasible"] = score(sc)
            out.append(s)
    return out


def line(s):
    sc, p, dp = s["sc"], s["params"], (s.get("deck_params") or {})
    return (f"{s['island']:>9} {s['run']:>13} {s['status']:<10} "
            f"{'FEAS' if s['feasible'] else '    '} J={r(s['score'],3):>8} | "
            f"s11={r(sc.get('s11'),3)} s22={r(sc.get('s22'),3)} "
            f"gimb={r(sc.get('pn_gain_imb_db'),4)} ph={r(sc.get('pn_phase_imb_deg'),3)} "
            f"cm={r(sc.get('cm_leak_dbc'),2)} "
            f"[lsb {r(sc.get('pn_gain_imb_db_lsb'),4)}/{r(sc.get('pn_phase_imb_deg_lsb'),3)}/"
            f"{r(sc.get('cm_leak_dbc_lsb'),2)}] | g={r(sc.get('lsb_gain'))}/{r(sc.get('msb_gain'),3)} "
            f"bw={r(sc.get('bw'),1)} sw={r(sc.get('swing'),3)} P={r(sc.get('power'),1)} "
            f"A={r(sc.get('area_um2'),0)} | split={p.get('out_split')} inord={p.get('in_order',0)} "
            f"rcgap={r(p.get('rc_gap'),2)} outgap={r(p.get('out_gap'),2)} nx={p.get('nx')} "
            f"tail={r(dp.get('tail_ma'),2)} re={r(p.get('re_ohm'))} rc={r(p.get('rc_ohm'),1)}"
            + (f"  ERR={str(s.get('error'))[:50]}" if s["status"] != "ok" else ""))


def main():
    a = list(sys.argv[1:])
    top = None
    if "--top" in a:
        i = a.index("--top"); top = int(a[i + 1]); del a[i:i + 2]
    if "--specs" in a:
        i = a.index("--specs"); harvest.SPECS = SPEC_TABLES[a[i + 1]]; del a[i:i + 2]
    rs = rows(a)
    if top is None:
        for s in rs:
            print(line(s))
    feas = sorted([s for s in rs if s["feasible"]], key=lambda s: -s["score"])
    print(f"--- {len(rs)} trials, {sum(1 for s in rs if s['status']=='ok')} ok, "
          f"{len(feas)} feasible; top {min(top or 5, len(feas))}:")
    for s in feas[:(top or 5)]:
        print(line(s))


if __name__ == "__main__":
    main()
