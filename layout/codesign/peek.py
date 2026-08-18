#!/usr/bin/env python3
"""Quick look at the trials of one or more run dirs (status + scorecard + key knobs)."""
import json, glob, os, sys
def r(v, n=2):
    return round(v, n) if isinstance(v, (int, float)) else "-"
for d in sys.argv[1:]:
    print("==", d)
    for sj in sorted(glob.glob(f"{d}/**/summary.json", recursive=True),
                     key=lambda p: int(os.path.basename(os.path.dirname(p)).split("_")[1])):
        s = json.load(open(sj)); sc = s["scalars"]; p = s["params"]; dp = s.get("deck_params") or {}
        print(f"{os.path.basename(os.path.dirname(sj)):>14} {s['status']:<12} "
              f"s11={r(sc.get('s11'))} s22={r(sc.get('s22'))} g={r(sc.get('lsb_gain'))}/{r(sc.get('msb_gain'))} "
              f"bw={r(sc.get('bw'),1)} sw={r(sc.get('swing'),3)} P={r(sc.get('power'),1)} A={r(sc.get('area_um2'),0)} | "
              f"nx={p.get('nx')} tail={r(dp.get('tail_ma'),1)} rc={r(p.get('rc_ohm'),1)} rb={r(p.get('rb_ohm'),1)} "
              f"re={r(p.get('re_ohm'))} cdeg={r(p.get('cdeg_ff'),1)} vc={r(dp.get('vcasc'))} outgap={r(p.get('out_gap'),1)} "
              f"outoff={r(p.get('out_off'),1)} rcsep={r(p.get('rc_sep'),1)} rew={r(p.get('re_w'),1)}"
              + (f"  ERR={str(s.get('error'))[:60]}" if s['status'] != 'ok' else ""))
