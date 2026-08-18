#!/usr/bin/env python3
"""Write the STATIC ngspice decks behind every number of the final results
(report/data/tables.md, paper Table I) so each one can be re-run by hand:

    cd verification/decks/<tier> && ngspice -b ac_msb.spice     # etc.
    python ../../extract.py <tier>                               # -> the numbers

Tiers:  a = schematic (nominal sizing)      b = first-pass layout (v1 floorplan, nominal sizing)
        c = v2 layout of record             d = v3 co-designed (paper column (c) / README v3)

Each layout tier's deck includes the converted kpex post-layout netlist that
`make report` produced (report/layout/<tier>/dut_pam4_post.spice) through the
same adapter subckt the Python benches use (layout/pex_sim.wrap_layout_dut),
with a RELATIVE include so the decks run from their own directory. The
schematic tier inlines the DUT subckt (dut/dut_pam4.spice convention).

The decks are produced by the very testbench builders of testbenches/driver_lib.py
(tb_ac, tb_ac_s22, tb_ac_balance, tb_dc, tb_bias, tb_eye) with the tier's
sizing/bias — nothing is hand-edited. Regenerate:  uv run python verification/dump_decks.py
"""
from __future__ import annotations

import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("layout", "layout/codesign", "testbenches", "report"):
    sys.path.insert(0, os.path.join(ROOT, sub))

import driver_lib as dl                                              # noqa: E402
import pex_sim                                                       # noqa: E402
from build_report import TIERS, dp_of                                # noqa: E402  (imports gen_layout -> gdsfactory, ~10 s)

DECKS = os.path.join(HERE, "decks")
NSYM = 200          # == report/build_report.py --nsym default
BAUD = 48e9

# Portable .spiceinit (same text as netlists/.spiceinit): resolved through $PDK_ROOT/$PDK
SPICEINIT = (
    "* IHP SG13G2 HBT decks — REQUIRED: without ngbehavior=hsa the HBT\n"
    "* conducts 0 current (silently). Export PDK_ROOT and PDK first, e.g.\n"
    "*   export PDK_ROOT=$HOME/local/pdks   PDK=ihp-sg13g2\n"
    "setcs sourcepath = ( $sourcepath $PDK_ROOT/$PDK/libs.tech/ngspice/models )\n"
    "set ngbehavior=hsa\n"
    "* PDK resistors (rsil/rppd in the layout netlists) are OSDI r3_cmc devices\n"
    "osdi $PDK_ROOT/$PDK/libs.tech/ngspice/osdi/r3_cmc.osdi\n"
)


def dut_ref_for(tier: str, deck_dir: str) -> str:
    """The DUT the deck instantiates: schematic subckt text (a) or the post-layout
    adapter with a relative include (b/c/d)."""
    t = TIERS[tier]
    dp = dp_of(t)
    if t["layout"] is None:
        _, sub, _ = dl.dut_subckt("pam4", dp)
        return sub
    post = os.path.join(ROOT, "report", "layout", tier, "dut_pam4_post.spice")
    if not os.path.exists(post):
        raise FileNotFoundError(f"{post} missing — run `make report` first (it writes report/layout/<tier>/)")
    ref = pex_sim.wrap_layout_dut("pam4", post)
    rel = os.path.relpath(post, deck_dir)
    return ref.replace(f'.include "{os.path.abspath(post)}"', f'.include "{rel}"')


def write_sp_twins(d: str, meta: dict) -> None:
    """ac_msb_sp.spice / s22_sp.spice: same bias, same DUT, but the source and
    load resistors are replaced by ngspice `portnum`/`z0` port sources and the
    S-matrix comes from `sp dec 100 ...` (ngspice >= 42). Cross-checks S21, S11,
    S22 (and BW / band-edge reads) against the wrdata decks."""
    vcm = meta["cell"]["vcm_in"]; vcc = meta["vcc"]
    s = open(os.path.join(d, "ac_msb.spice")).read()
    old = (f"Vsmsbp smsbp 0 DC {vcm:g} AC 0.5\nVsmsbn smsbn 0 DC {vcm:g} AC -0.5\n"
           f"Rsmsbp smsbp msbp 50\nRsmsbn smsbn msbn 50\n")
    assert old in s, "ac_msb.spice source block changed — update write_sp_twins"
    s = s.replace(old, f"Vsmsbp msbp 0 DC {vcm:g} AC 1 portnum 1 z0 50\nVsmsbn msbn 0 DC {vcm:g} AC 1 portnum 2 z0 50\n")
    old2 = "Rlp outp vcc 50\nRln outn vcc 50\n"
    assert old2 in s
    s = s.replace(old2, "Vlp outp vcc DC 0 AC 0 portnum 3 z0 50\nVln outn vcc DC 0 AC 0 portnum 4 z0 50\n")
    s = s[:s.index(".control")] + (
        "* independent method: ngspice built-in S-parameter analysis, 4 ports (msbp, msbn, outp, outn), z0 = 50\n"
        ".control\nop\nsp dec 100 1e8 1e11\n"
        "let sdd11 = 0.5*(S_1_1 - S_1_2 - S_2_1 + S_2_2)\nlet sdd21 = 0.5*(S_3_1 - S_3_2 - S_4_1 + S_4_2)\n"
        "let sdd11db = db(sdd11)\nlet sdd21db = db(sdd21)\nwrdata ac_msb_sp.csv sdd21db sdd11db\n.endc\n.GLOBAL GND\n.end\n")
    open(os.path.join(d, "ac_msb_sp.spice"), "w").write(s)
    s = open(os.path.join(d, "s22.spice")).read()
    old = f"Vsop sop 0 DC {vcc:g} AC 0.5\nVson son 0 DC {vcc:g} AC -0.5\nRsop sop outp 50\nRson son outn 50\n"
    assert old in s, "s22.spice source block changed — update write_sp_twins"
    s = s.replace(old, f"Vsop outp vcc DC 0 AC 1 portnum 1 z0 50\nVson outn vcc DC 0 AC 1 portnum 2 z0 50\n")
    s = s[:s.index(".control")] + (
        "* independent method: ngspice built-in S-parameter analysis, 2 ports (outp, outn), z0 = 50\n"
        ".control\nop\nsp dec 100 1e8 1e11\n"
        "let sdd22 = 0.5*(S_1_1 - S_1_2 - S_2_1 + S_2_2)\nlet sdd22db = db(sdd22)\n"
        "wrdata s22_sp.csv sdd22db\n.endc\n.GLOBAL GND\n.end\n")
    open(os.path.join(d, "s22_sp.spice"), "w").write(s)
    meta["decks"]["ac_msb_sp"] = dict(out="ac_msb_sp.csv", cols="f, sdd21_db, f, sdd11_db",
                                      gives=["cross-check: msb_gain, bw_msb, s11_msb, s11_edge (ngspice sp)"])
    meta["decks"]["s22_sp"] = dict(out="s22_sp.csv", cols="f, sdd22_db", gives=["cross-check: s22, s22_edge_ghz (ngspice sp)"])


def main() -> None:
    random.seed(7)                                   # == report/build_report.py
    msb = [random.randint(0, 1) for _ in range(NSYM)]
    lsb = [random.randint(0, 1) for _ in range(NSYM)]
    for tier in "abcd":
        t = TIERS[tier]
        dp = dp_of(t)
        d = os.path.join(DECKS, tier)
        os.makedirs(d, exist_ok=True)
        ref = dut_ref_for(tier, d)
        open(os.path.join(d, ".spiceinit"), "w").write(SPICEINIT)
        open(os.path.join(d, "spiceinit.txt"), "w").write("# copy of .spiceinit (ngspice reads the dotfile)\n" + SPICEINIT)
        meta = dict(tier=tier, label=t["label"], vcc=dp.vcc, cell=dp.cell.__dict__, baud_hz=BAUD, nsym=NSYM,
                    decks={})
        # S21/S11, both drive paths  (gain, weight, BW, S11, S11 edge)
        for drv in ("lsb", "msb"):
            deck = dl.tb_ac("pam4", ref, drive=drv, dp=dp, pts_per_dec=100, out_csv=f"ac_{drv}.csv")
            open(os.path.join(d, f"ac_{drv}.spice"), "w").write(deck)
            meta["decks"][f"ac_{drv}"] = dict(out=f"ac_{drv}.csv", cols="f, s21_db, f, s11_db",
                                             gives=[f"{drv}_gain", f"bw_{drv}", f"s11_{drv}", "s11", "s11_edge_ghz", "weight", "bw"])
        # S22
        deck = dl.tb_ac_s22("pam4", ref, dp=dp, pts_per_dec=100, out_csv="s22.csv")
        open(os.path.join(d, "s22.spice"), "w").write(deck)
        meta["decks"]["s22"] = dict(out="s22.csv", cols="f, s22_db", gives=["s22", "s22_edge_ghz"])
        # p/n balance (MSB drive)
        deck = dl.tb_ac_balance("pam4", ref, drive="msb", dp=dp, pts_per_dec=100, out_csv="balance.csv")
        open(os.path.join(d, "balance.spice"), "w").write(deck)
        meta["decks"]["balance"] = dict(out="balance.csv", cols="f, gp_db, f, gn_db, f, php_deg, f, phn_deg, f, cm_db, f, dd_db",
                                        gives=["pn_gain_imb_db", "pn_phase_imb_deg", "cm_leak_dbc"])
        # DC transfer (swing)
        deck = dl.tb_dc("pam4", ref, drive="both", vd_max_mv=900.0, step_mv=15.0, dp=dp, out_csv="dc.csv")
        open(os.path.join(d, "dc.spice"), "w").write(deck)
        meta["decks"]["dc"] = dict(out="dc.csv", cols="vd, vout_diff, vd, i_vcc", gives=["swing"])
        # bias / power
        deck, hold0, t_end = dl.tb_bias("pam4", ref, dp=dp, probes=["v(outp)", "i(Vcc)"], out_csv="bias.csv")
        open(os.path.join(d, "bias.spice"), "w").write(deck)
        meta["decks"]["bias"] = dict(out="bias.csv", cols="t, v(outp), t, i(Vcc)", hold0_ns=hold0, t_end_ns=t_end,
                                     gives=["power", "ic_ma_per_finger"])
        # 48 GBd PAM-4 eye
        deck, t0, t_end = dl.tb_eye(ref, msb_bits=msb, lsb_bits=lsb, dp=dp, baud_hz=BAUD, vswing_mv=200.0, out_csv="eye.csv")
        open(os.path.join(d, "eye.spice"), "w").write(deck)
        meta["decks"]["eye"] = dict(out="eye.csv", cols="t, vout_diff", data_start_ns=t0, t_end_ns=t_end,
                                    gives=["eye_rlm", "eye_min_v", "eye_vpp", "eye_levels_v", "eye_openings_v"])
        # independent-method twins: ngspice's built-in S-parameter analysis (`sp`,
        # port sources with z0=50) instead of the in-deck power-wave algebra;
        # mixed-mode Sdd = 0.5*(S11 - S12 - S21 + S22) over the p/n port pair
        write_sp_twins(d, meta)
        json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1)
        print(f"{tier}: {len(meta['decks'])} decks -> {os.path.relpath(d, ROOT)}")


if __name__ == "__main__":
    main()
