# PAM-4 driver — parameterized gdsfactory layout (IHP sg13g2)

Programmatic, **optimizer-ready** layouts for the three driver DUTs
(`../dut/dut_{lsb,msb,pam4}.spice`), built with **gdsfactory +
[ihp-gdsfactory]** on the pattern of the platform 5T-OTA lane
(`examples/layout/ihp-sg13g2/5t_ota_gf/`). First HBT layout in the
ecosystem.

| DUT | Cells | Devices | Size (default params) | DRC | LVS |
|---|---|---|---|---|---|
| `lsb` | 1 | 4 HBT + 5 R + 1 C | 43.8 x 60.1 um (2633 um2) | PASS | PASS |
| `msb` | 2 | 8 HBT + 8 R + 2 C | 77.6 x 60.1 um (4665 um2) | PASS | PASS |
| `pam4` | M0\|L0\|M1 | 12 HBT + 12 R + 3 C | 116.2 x 62.9 um (7311 um2) | PASS | PASS |

(defaults = the v1 floorplan; the **layout of record is `gen_layout.FINAL_LAYOUT`
= v4, 102.0 × 69.2 µm / 7055 µm², co-designed through the SpiceXplorer
platform — see the v3/v4 sections at the end and `codesign/README.md`).

Signoff: KLayout DRC (`--no_density`, geometrically clean) + KLayout LVS
("Netlists match") through the PDK's own decks, per DUT.

## Files

```
gen_layout.py       LayoutParams (30 free constants + 5 structural INT options) -> GDS + netlists
                    FINAL_LAYOUT/FINAL_BIASES = v4 (layout of record, co-design round 3);
                    V3_LAYOUT/V3_BIASES = the round-2 point; V2_LAYOUT/V2_BIASES = the 2026-08-09 point
signoff.py          DRC + LVS wrapper (per DUT)      -> out/signoff/
pex_sim.py          kpex 2.5D PEX + pre/post ngspice .op/.ac comparison (KPEX_HALO_UM overrides the tech's 8 um sidewall halo)
optimize_layout.py  nevergrad loop: gen -> DRC/LVS gate -> PEX -> sim (the block-local v1/v2 loop)
codesign/           the same loop run THROUGH spicexplorer-optimize (sim_engine: layout) — Alg. 1 of the paper; rounds, record, figures
compare_layouts.py  before/after on the PDK render: original v1 vs the record (before_after.png, default) or vs v2/v3;
                    codesign/figures.py draws the v3 -> v4 one with changed regions boxed (and before_after_r2.png = v2 -> v3)
render.py           GDS -> PNG (IHP layer colors)
out/                dut_<d>.png, dut_<d>_{lvs,kpex,sim}.spice (at FINAL_LAYOUT = v4),
                    signoff/, pex/ (dut_<d>_post.spice, metrics_v3_*.json / metrics_v4_*.json), pex_report.yaml
                    (GDS is git-ignored — it regenerates byte-for-byte from gen_layout.py; the
                    reviewer copies of the v1/v2/v3/v4 GDS live in ../report/layout/<tier>/)
```

Run (uv env from the repo root; tool locations per the top-level README's
"EDA tool setup" — kpex/KLayout resolve from `PATH` or `KPEX` /
`KPEX_KLAYOUT_EXE`):

```sh
export PDK_ROOT=<dir containing ihp-sg13g2> PDK=ihp-sg13g2
uv run python gen_layout.py --dut all   # generate GDS + netlists
uv run python signoff.py                # DRC + LVS (all PASS)
uv run python pex_sim.py --dut all      # PEX + pre/post metrics
uv run python optimize_layout.py --dut lsb --budget 20
```

## Floorplan (one gain cell)

Mirror-symmetric about the cell axis; signal flows bottom -> top:

```
vcc rail (TopMetal2) ── RCp/RCn (rsil) ── outp/outn buses (TopMetal1)
        cascode row:   Q3 ──────── Q4     (vcasc strap on the B bars)
        c1/c2 nodes:   wide short Metal2 plates (input C bar -> casc E plate)
        input row:     Q1 ── Cdeg (cmim, center) ── Q2
        emitters:      Metal2 straps -> RE (rsil) -> tail bus (port)
        inputs:        B-bar drops (M1) -> input buses (Metal3) -> RB -> vcmb
        substrate:     p-sub guard ring (`sub`) + tap columns between cells
```

RF practices baked in: differential mirror symmetry; the Miller-critical
cascode nodes are <3 um long full-width M2 plates; outputs rise straight to
thick TopMetal1 buses and the 48 mA vcc rail is TopMetal2; via *arrays* on
every DC path; each pcell's substrate is ringed and tapped (isolation +
well-defined `sub` reference). All spacings/widths are `LayoutParams`
fields — the optimizer's search space.

Tails are **ports** (`tail`, `tail0/1`, `tlsb0/tmsb0/tmsb1`): the ideal
VCCS tail current source stays in the testbench, exactly like the schematic
DUTs, so layout and schematic characterizations stay comparable.

## Devices (all foundry-recognized, LVS-extracted)

- **npn13G2 Nx=3** via the ihp-gdsfactory *PyCell* wrapper
  (`cells2.npn13G2`) — pass `emitter_width=0.07` (the wrapper's 0.7 um
  default draws an unrecognizable emitter). Two thin Metal1 patch overlays
  per device fix the PyCell's CntB.h1 (M1 enclosure of ContBar) violations.
- **rsil** for RE/RC/RB. Sizing accounts for the **contact-head resistance
  (~4.5 ohm*um per end)**: `l = (R*w - 9)/7`. That forces `re_w >= 4.4 um`
  for the 2.5-ohm RE (default 5.0 -> exactly 2.5 ohm total). Lengths snap
  to 0.01 um (the cell halves them internally; 0.005 offgrid otherwise).
- **cmim** Cdeg: drawn 2.87 um -> extracted/effective w = drawn + 0.72
  (MIM layer) -> 19.9 fF on the cap_cmim model. Bottom plate (Metal5) on
  e1, top plate (TopMetal1) on e2 — single-cap asymmetry noted; both e
  nodes are low-impedance degeneration points.
- Guard ring is hand-drawn (Activ+pSD+Cont+M1); the ihp-gdsfactory
  `guard_ring` cell violates Cnt.b at its corners.

## Generated netlists (device records == drawn geometry, by construction)

- `dut_<d>_lvs.spice` — KLayout-LVS reference: primitive `Q/R/C` cards
  (`Q.. npn13G2 AE=0.063p PE=1.94u M=3`, 2-node `R.. rsil w= l=`,
  `C.. cap_cmim W= L=`).
- `dut_<d>_kpex.spice` — same, but 3-node rsil (kpex's deck models poly
  resistors as 3-terminal).
- `dut_<d>_sim.spice` — ngspice subckt on the PDK models (X-cards).
  Requires `.spiceinit` with `osdi .../r3_cmc.osdi` (rsil is an OSDI
  device) — `driver_lib.spiceinit_lines()` now adds it automatically.

## PEX + post-layout results (defaults, typ corner, kpex 2.5D mode CC)

`pex_sim.py` compares three tiers: the *schematic* golden numbers live in
`../results/`; here **pre** = same devices on PDK R/C models, no wiring;
**post** = + extracted parasitics:

| DUT:path | S21 LF (dB) | f3dB pre -> post (GHz) | S11 worst pre -> post (dB) | P (mW) |
|---|---|---|---|---|
| lsb:in    | 2.94 | >100 -> 96.3 | -16.5 -> -15.2 | 63.6 |
| msb:in    | 8.92 | 69.4 -> 58.4 | -11.0 -> **-9.5** | 127.3 |
| pam4:lsb  | 2.95 | 92.6 -> 66.1 | -16.5 -> -13.8 | 191.0 |
| pam4:msb  | 8.92 | 66.8 -> 51.1 | -11.0 -> **-8.9** | 191.0 |

Takeaways (the case-study motivation): with the *nominal* schematic sizing,
layout parasitics alone push the MSB/PAM4 input reflection **below the
-10 dB spec** and cost the MSB path ~16 GHz of bandwidth — the layout
constants and the electrical sizing have to be co-optimized, which is what
`optimize_layout.py` provides: DRC/LVS hard-gated, real kpex+ngspice in the
loop, objective

    score = w_area*area/area0 + bw_loss/loss0
            + w_s11*max(0, S11_post - spec)      # hinge, dB over -10 dB

with the resistor *widths* (`re_w`/`rc_w`/`rb_w`) in the search space —
their lengths always re-derive from the PDK rsil model (R = 7*l/w + 9/w,
contact heads included), so every candidate holds the resistance target
while trading resistor area and parasitics. The real rsil/cmim models also
shave ~0.16 dB of LF gain vs the ideal-R schematic (silicided-poly heads,
cap tolerance) — visible in the `pre` column vs `../results/`.

## Known workarounds / tool gaps

- **kpex cannot extract the MIM cap** (its ihp tech tables have
  `cmim_top = <TODO>` -> KeyError). `pex_sim.py` strips the MIM/Vmim/MemCap
  layers from a GDS copy (plates keep coupling as plain metal), removes the
  C cards from the kpex schematic, and re-inserts the intentional
  `cap_cmim` devices into the converted netlist (cell-wise, via the RE
  resistor terminals). Validated for mode CC.
- kpex's LVS step needs a KLayout executable built with Ruby >= 2.6 —
  resolved from `PATH` or `KPEX_KLAYOUT_EXE` (top-level README,
  "EDA tool setup").
- ihp-gdsfactory bugs found here: `cells.npn13G2` duplicate ports for
  Nx>1; `cells2` PyCell rsil crashes (KeyError 'EXTBlock');
  `emitter_width` default 0.7 should be 0.07; `guard_ring` corner Cnt.b.
- EM note: via arrays are sized for DRC, not signoff-grade EM; the RC
  path (24 mA) gets stack_w=2.0 arrays — widen `stack_w`/`rc_w` for a
  tapeout-grade rail budget.

[ihp-gdsfactory]: https://github.com/gdsfactory/ihp

## 2026-08-09 (v2): full-spec resize + RF layout fixes — ALL 8 SPECS PASS

The first signoff (notebook 03) caught the v1 optimum (nx=2, R_C=70)
failing **S22** (−8.3 dB) and **max swing** (2.07 Vpp) — both absent from
the v1 objective. An expert RF layout review (routing / placement / metals /
process variation / symmetry / reflection) plus a directed probe ladder
produced the v2 configuration, now baked in as `gen_layout.FINAL_LAYOUT` +
`FINAL_BIASES`:

* **Electrical (back to the paper's nominal topology):** nx=3,
  tail 15 mA/cell, R_C=50 Ω, R_B=48 Ω, R_E=3.2 Ω (w=4.5), C_deg=16 fF,
  V_casc=3.35 V. R_E↑ is the S11 closer: series feedback shrinks the
  effective input C (the model card scales with Nx only — see notebook 03
  §0b for why `emitter_width=0.07` is exactly the modeled device).
* **Input network:** `input_feed="center"` (H-tree: R_B columns on the
  centreline, symmetric branches — halves the input line per branch,
  zeroes M0/M1 skew), `in_bus_layer="Metal4"`, `in_bus_gap=3.0`,
  `in_off=2.2`, `drop_layer="Metal2"` (base drops descend on M2 with the
  M1→M2 via below the bar). msb S11 at nx=3: −8.8 → −10.03 dB.
* **Output network:** `out_gap=8.0` (differential sidewall C counts double),
  `out_w=1.64` (TM1 min), `w_out=1.5`, `rc_sep=4.0`, `stack_w=1.7`
  (stack() now clamps pads per-via, e.g. TopVia2 → 1.9), bus overhang
  ±1.5 µm, row compaction `gap_x=6.0` / `cell_gap=5.0`.
  S22 at R_C=50: −8.4 → −10.14 dB. kpex C-budget: the summing-bus network
  carried ~14 fF/side (kpex charges TM1 37.4 aF/µm of *edge* to substrate
  unconditionally, so length is what matters) + ~14 fF/side of cascode
  junction C that no layout removes.
* **Extraction cross-check:** kpex RC mode (2134 R cards) reproduces every
  CC metric to 0.01 dB (needs `.options rshunt=1e10` — the split nets
  leave floating R-islands).
* **Signoff:** DRC + LVS PASS on all 3 DUTs; pam4 99.6 × 75.8 µm
  (7552 µm²). Post-layout (kpex CC, wrapped driver_lib benches):
  LSB/MSB gain 2.27/8.25 dB, weight 5.98 dB, BW 58.8 GHz, S11 −10.03 dB,
  S22 −10.14 dB, swing 2.21 Vpp, power 179 mW — all specs met.

**Pre-tapeout flags from the layout review (open):** vcasc rail bypass
(≥1 pF/cell cmim) + 20–50 Ω odd-mode series R per cell (six cascodes share
a thin M1 rail — stability); EM/current-density pass on via stacks and the
TM1 bus (single TopVia2 on 20+ mA paths); ground cage (via-stacked ring
≥3 µm, tap fence ≤5 µm pitch, stitched sub rail); HBT/rsil/cmim dummies at
row ends (interdigitation is not available for the fixed HBT PyCells —
translation-symmetric placement is kept deliberately); R_E is ~2/3
contact-head resistance at w=4.5 (split into parallel units for matching);
group-delay variation + extracted-rail stability (K-factor, odd-mode)
before tapeout; 2-row floorplan held in reserve (halves the summing bus →
~+1.5 dB more S22 margin) if larger margins are required.

Before/after figure of the v2 optimization: `before_after_v2.png`
(regenerate with `compare_layouts.py --after v2`; `before_after.png` is the
original v1 → v3 comparison, `--after v3`).

## 2026-08-18 (v3): layout/schematic co-design through the SpiceXplorer platform — ALL 8 SPECS PASS, honestly measured

Two things were wrong with the v2 scorecard above, both found by running the
paper's co-design loop (`codesign/`, Algorithm 1) *through the platform* and
having the rf-layout-reviewer read the record:

* **the instrument** — "S11 −10.03 / S22 −10.14" were the worst points of the
  ngspice `dec 20` grid, whose last in-band samples are 31.62 / 44.67 GHz;
  at the actual band edges (32 / 50 GHz, interpolated — what the paper's
  table and `run_verify.py` report) v2 reads **S11 −9.94 / S22 −9.24 dB and
  fails both reflection specs**;
* **the extractor's halo** — kpex drops couplings beyond the tech's 8 µm
  sidewall halo, and `out_gap` sat exactly on it (`KPEX_HALO_UM=20` /
  `pex.halo_um` in the platform now; the record then reads −9.98 / −9.36).

Two co-design rounds (280 platform trials, 4 islands each; per-round record
in `codesign/results/`) turned the round-1 review into five *structural*
generator options — `bus_trim` (per-net output bus extents), `sub_bus`
(taps to the ring on Metal1, no Metal3 bus under the risers), `cell_order`
(M0|M1|L0), `c_strip` (cascode-collector tab away from the PyCell's Metal2
emitter plate), `out_split` (outn on TopMetal2) — exposed as INT knobs so the
search decides. Accepted point = `FINAL_LAYOUT` (r2 island s3 `run_38`;
tail 15.93 mA, vcasc 3.31 V, R_C 46.5 Ω, R_E 3.24 Ω, C_deg 18.45 fF,
out_gap 6.37, all five structural options on):

| | v2 (record) | **v3** | spec |
|---|---|---|---|
| S11 @32 GHz / −10 dB edge | −9.94 dB / 31.7 GHz | **−10.05 dB / 32.2 GHz** (halo 20: −10.07) | ≤ −10 / ≥ 32 |
| S22 @50 GHz / −10 dB edge | −9.24 dB / 45.5 GHz | **−10.72 dB / 54.7 GHz** (halo 20: −10.78) | ≤ −10 / ≥ 50 |
| gain LSB / MSB, weight | 2.27 / 8.25, 5.98 dB | 2.23 / 8.21, 5.97 dB | ≥ 2.2 / ≥ 8.2, ≥ 5 |
| BW MSB / LSB | 58.8 / 78.9 GHz | 61.1 / 82.4 GHz | ≥ 50 |
| swing / power | 2.21 Vpp / 179.1 mW | 2.26 Vpp / 190.2 mW | ≥ 2.1 / ≤ 192 |
| core area | 99.6 × 75.8 = 7552 µm² | **97.6 × 70.5 = 6880 µm²** | (paper 11 300) |

DRC + LVS PASS on all three DUTs; kpex RC mode (1861 wiring R) reproduces the
CC scorecard exactly. Margins are thin by construction (S11 is
device-limited at ≈ −11.4 dB with zero wiring; the S22 floor is the cascode
junction C at −14.5 dB) — the full budget, the ceiling analysis, the rounds
table and the figures (`codesign/pam4_layout_annotated.png`,
`codesign/before_after.png` = v2 → v3 boxed, `codesign/rounds.png`) are in
`codesign/README.md`; `before_after.png` here is original v1 → v3 on the PDK
render; notebook 04 reads the record.

## 2026-08-18 (v4): co-design round 3 — p/n balance made an objective

Round 3 of the platform loop (`codesign/`, 520 trials over 14 islands) took the
owner's brief — *better p/n symmetry first, then reflection, then power, then
area* — and turned the r2 matching audit into knobs: the symmetric/mirrored
`out_split` variants, a p/n-swapped input row order (`in_order`), and the
continuous `rc_gap` (outn bus ↔ RC body **and** the TopMetal2 vcc rail, where
the extraction found 2.34 fF against outp's 0.26 fF). The p/n balance of the
MSB *and* LSB paths is measured by the hook and **rewarded** by `J`.

Accepted point = `FINAL_LAYOUT` (r3 island s23 `run_30`; tail 15.4977 mA,
vcasc 3.2151 V, R_C 47.86 Ω, R_E 3.54 Ω, C_deg 20.95 fF, out_gap 4.81,
rc_gap 2.48 — the structural options unchanged from v3):

| | v3 | **v4** | spec |
|---|---|---|---|
| S11 @32 GHz / −10 dB edge (halo 20 CC) | −10.070 dB / 32.30 GHz | **−10.073 dB / 32.32 GHz** | ≤ −10 / ≥ 32 |
| S22 @50 GHz / −10 dB edge (halo 20 CC) | −10.790 dB / 55.16 GHz | **−10.812 dB / 55.30 GHz** | ≤ −10 / ≥ 50 |
| p/n \|gain\| / phase / diff→CM ≤ 48 GHz | 0.043 dB / 0.88° / −41.9 dBc | **0.035 dB / 0.64° / −44.5 dBc** | (r3 objective) |
| gain LSB / MSB, weight | 2.232 / 8.205, 5.972 dB | 2.269 / 8.244, 5.975 dB | ≥ 2.2 / ≥ 8.2, ≥ 5 |
| BW MSB / LSB | 61.2 / 82.7 GHz | 61.4 / 83.0 GHz | ≥ 50 |
| swing / power | 2.258 Vpp / 190.19 mW | 2.237 Vpp / **185.05 mW** | ≥ 2.1 / ≤ 192 |
| core area | 97.6 × 70.5 = 6880 µm² | 102.0 × 69.2 = 7055 µm² | (paper 11 300) |

DRC + LVS PASS on all three DUTs; RC mode (1382 wiring R) reproduces the CC
scorecard to four decimals. The two *symmetric* metal options and the input-row
swap were measured and are **nulls** — the balance came from the per-net C
budget (output-net asymmetry 2.01 → 1.46 fF) and the electrical point. The
round's ceiling (every larger balance gain costs 0.1–0.5 dB of S22; only 6 of
520 trials hold both reflections at the v3 level) and the halo-8 vs halo-20
instrument note are in `codesign/README.md`.

**Reviewer evidence.** `../report/` (rebuilt by `make report`) regenerates
v1 (original floorplan, nominal sizing), v2 and v3 from `gen_layout.py`,
re-runs DRC / LVS / kpex on each, re-simulates every bench (S11/S21/S22 at
`dec 100`, p/n balance, DC transfer, 48 GBd eyes) alongside the schematic,
and keeps the GDS + LVS/kpex/post-layout netlists + signoff logs per tier
next to the tables and KLayout renders. The p/n matching audit (v2 0.03 dB / 0.5° / −46.5 dBc, v3 0.053 dB / 1.18° /
−39.4 dBc, **v4 0.047 dB / 0.99° / −40.8 dBc** — all halo 8; at halo 20 v4
reads 0.035 dB / 0.64° / −44.5 dBc) is in `codesign/README.md`.
