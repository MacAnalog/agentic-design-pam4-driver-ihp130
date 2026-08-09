# Agentic design of a 96 Gb/s PAM-4 driver — IHP SG13G2 (130 nm SiGe BiCMOS)

AI-agent-driven, fully scripted design of an inductorless PAM-4 optical
modulator driver — a block-level replication of *Inac et al., "Inductorless
96 Gb/s PAM-4 Optical Modulators Driver in SiGe:C BiCMOS," EuMIC 2022* on
the open IHP SG13G2 PDK — taken from netlist to DRC/LVS-clean parameterized
layout, kpex extraction, and a layout + electrical co-optimization that
closes **all eight post-layout specs**. The audit trail is three executed
notebooks; every result below reproduces from this repo.

## The layout journey

The first optimization pass scored only S11/BW/gain/power — and its winner
(nx=2, R_C=70 Ω) sailed through those while silently **failing S22
(−8.3 dB) and output swing (2.07 Vpp)**, caught by the full signoff
(notebook 03). An expert RF layout review + a directed probe ladder
produced the fix, and the punchline: **once the layout was repaired, the
electrical optimum returned to the paper's nominal topology** (nx=3,
R_C=50 Ω) — the odd v1 sizing had been compensating layout parasitics.

![before/after layout](layout/before_after.png)

| step | what was learned / changed | effect |
|---|---|---|
| v1 signoff | S22 and swing were never in the objective — R_C=70 bought gain with output mismatch | S22 −8.3 ✗, swing 2.07 ✗ |
| C-budget from extraction | output C, not R_C mismatch, limits S22: ~14 fF/side of bus wiring (kpex charges TM1 37 aF/µm of *edge* to substrate — length is everything) + ~14 fF/side cascode junctions; outp↔outn sidewall counts **double** differentially | fix must be geometric |
| output-network fixes | bus gap 1.8→8 µm, min-width TM1, slim risers/via stacks, ±1.5 µm overhang, compacted row | S22 −8.4 → **−10.14** at R_C=50 |
| input-network fixes | center-fed H-tree R_B (kills the far-MSB-cell ~80 µm stub), Metal4 buses with MSB rows innermost, 3 µm pair gap, Metal2 base drops | msb S11 at nx=3: −8.8 → −9.9 |
| electrical re-tune | tail 15 mA, R_B 48, V_casc 3.35, and **R_E 2.5→3.2 Ω** — series feedback shrinks the effective input C (the HBT model scales with Nx only) | S11 **−10.03** ✓ with gain 8.25 ✓ |
| verify | kpex RC mode ≡ CC mode to 0.01 dB; DRC + LVS clean on all 3 DUTs | point frozen as `gen_layout.FINAL_LAYOUT` |

Open pre-tapeout items from the review (vcasc bypass/stability, EM current
density, ground cage, matching dummies) are tracked in
[layout/LAYOUT_REVIEW.md](layout/LAYOUT_REVIEW.md).

## Results

| metric (post-layout `pam4`, kpex 2.5D) | paper (meas.) | EIC ref (schem) | **this repo (post-layout)** | spec |
|---|---|---|---|---|
| LSB / MSB LF gain | 3.2 / 9.2 dB | 3.10 / 9.07 | **2.27 / 8.25 dB** | ≥ 2.2 / ≥ 8.2 ✅ |
| DAC weight | 6.0 dB | 5.97 | **5.98 dB** | ≥ 5.0 ✅ |
| Bandwidth (worst path) | 51–67 GHz | 68.5 | **58.8 GHz** | ≥ 50 ✅ |
| S11 (≤32 GHz) | < −10 | −10.87 | **−10.03 dB** | ≤ −10 ✅ |
| S22 (≤50 GHz) | < −10 | −14.76 | **−10.14 dB** | ≤ −10 ✅ |
| Max diff swing | 2.1 Vpp | 2.92 | **2.21 Vpp** | ≥ 2.1 ✅ |
| Power | 192 mW | 191 | **179 mW @ 4 V** | ≤ 192 ✅ |
| 48 GBd PAM-4 eye | Fig. 5 | RLM 0.975 | **RLM 0.974, ~0.24 V eyes** | open ✅ |
| Core area | 0.011 mm² | — | **0.0076 mm²** (99.6 × 75.8 µm) | — |

**48 GBaud PAM-4 eye** — nominal schematic vs re-tuned schematic vs
parasitic-extracted layout, same testbench:

![eye diagrams](notebooks/report_figs/eye_48gbd_pam4.png)

**S-parameters** (S21 both paths, S11, S22 — schematic vs post-layout):

![s-parameters](notebooks/report_figs/sparams_s21_s11_s22.png)

**DC transfer + the four PAM-4 DAC levels** (swing/linearity signoff):

![dc transfer](notebooks/report_figs/dc_transfer_dac_levels.png)

**Final pam4 layout** (3 differential cascode cells summing into shared
collector loads; DRC + LVS clean):

![final layout](notebooks/report_figs/pam4_layout_final.png)

All plots regenerate from `notebooks/03_signoff.py`; the executed
notebooks (committed `.ipynb`) contain every table and figure inline:

| notebook | contents |
|---|---|
| [01_schematic_sizing](notebooks/01_schematic_sizing.ipynb) | DUT schematics, testbenches, nominal sizing, bias/S-param/eye vs the verified reference |
| [02_layout_in_the_loop](notebooks/02_layout_in_the_loop.ipynb) | gdsfactory generation, DRC/LVS, kpex, co-optimization with the **full 8-spec objective** |
| [03_signoff](notebooks/03_signoff.ipynb) | DC/tran/AC/eye on schematic **and** post-layout through the *same* benches; master spec table; `emitter_width=0.07` validity proof |

## Repo map

```
dut/          three DUT subcircuits (lsb / msb / pam4 2-bit DAC)
netlists/     static, directly runnable ngspice decks (+ .spiceinit)
testbenches/  driver_lib.py — netlist-agnostic benches (schematic AND
              post-layout via dut_ref=), run_verify.py, run_eye.py
layout/       gen_layout.py (parameterized generator, FINAL_LAYOUT),
              signoff.py (DRC+LVS, vendored PDK runner), pex_sim.py (kpex),
              optimize_layout.py, LAYOUT_REVIEW.md, before_after.png,
              out/ (final GDS, netlists, PEX, renders)
notebooks/    jupytext .py sources + executed .ipynb + report_figs/
results/      committed characterization plots + metrics YAML
schematics/   xschem schematics (paper Fig. 1 / 2a / 2b)
docs/         REFERENCE.md — detailed methods, measurement conventions,
              JPP-361 ngspice finding, provenance
```

## EDA tool setup

One-time, per machine. Install the tools wherever you like, then record the
paths in an untracked `local.mk` at the repo root — the Makefile injects
them into every flow.

1. **PDK** — clone [IHP-Open-PDK](https://github.com/IHP-GmbH/IHP-Open-PDK);
   `PDK_ROOT` = the directory containing `ihp-sg13g2`.
2. **ngspice 45** on `PATH` — build from
   [ngspice](https://ngspice.sourceforge.io) or use a distro package.
   Version 45+ is required for the full suite: on 44 the self-heating VBIC
   HBT fails `.op/.ac/.dc` (transient benches only — docs/REFERENCE.md).
3. **Python 3.11+** via [uv](https://docs.astral.sh/uv/): `uv sync` creates
   `.venv` from `uv.lock` (includes the `klayout` Python module the DRC/LVS
   runners use — no KLayout app install needed for signoff).
4. **klayout-pex ≥ 0.3.12** (*optional* — parasitic re-extraction only, see
   below): `pip install klayout-pex` in any env, or
   [releases](https://github.com/martinjankoehler/klayout-pex). Its LVS step
   additionally drives a **KLayout ≥ 0.30 executable** built with
   Ruby ≥ 2.6 ([klayout.de](https://www.klayout.de/build.html)). Both are
   found on `PATH` (`kpex`, `klayout`); override with `KPEX` /
   `KPEX_KLAYOUT_EXE` if they live elsewhere.

```make
# local.mk (untracked) — example
PDK_ROOT         = /opt/pdks
KPEX             = /opt/kpex/bin/kpex
KPEX_KLAYOUT_EXE = /opt/klayout/klayout
```

Ad-hoc runs outside `make` work the same way with environment variables:
`export PDK_ROOT=... PDK=ihp-sg13g2 [KPEX=... KPEX_KLAYOUT_EXE=...]`.

## Running it

```sh
make sync        # uv sync — create/update the Python env
make verify eye  # schematic benches + PAM-4 eye (results/*)
make signoff     # layout DRC + LVS on all three DUTs
make nb03        # execute the signoff notebook (jupytext -> .ipynb)
```

`make all` runs everything (incl. notebooks 01/02; 02 is the
layout-in-the-loop optimizer — takes a while, tune with `NB_BUDGET=n`).
Any variable can also be set per-invocation, e.g.
`make signoff PDK_ROOT=/opt/pdks`. The `.ipynb` notebooks are generated
from the paired `.py` files and are not tracked.
A raw one-off deck: `cd netlists && ngspice -b tb_pam4_sparam_msb_1ghz.spice`.

Post-layout results reproduce **without kpex**: the converted PEX netlists
are committed (`layout/out/pex/dut_*_post.spice`) and every bench runs on
them via `run_ac(..., dut_ref=pex_sim.wrap_layout_dut("pam4", <netlist>))`.
The `.spiceinit` (`set ngbehavior=hsa`) is mandatory — without it the HBT
conducts 0 A silently; the Python runners write it automatically.

## Provenance

Port of the EIC-designer `lumped-broadband-driver` verified reference,
reproduced with zero delta on all 8 system metrics
(`results/pam4_results.yaml`). Designed, laid out, verified, and
re-optimized end-to-end by AI agents (Claude), including an independent
multi-agent RF layout review; the executed notebooks are the human-facing
audit trail.
