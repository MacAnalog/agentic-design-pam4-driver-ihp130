#!/usr/bin/env python3
"""Co-design figures: the annotated PARAMETERIZED layout (every optimizer
knob drawn on the render), the before/after of the accepted round, and the
per-round strip (layout of record | round-1 best | round-2 best ...).

All renders are drawn from the GDS with matplotlib in real micrometres
(klayout.db reads the polygons; IHP sg13g2.lyp colours), so annotations are
placed from the generator's own geometry record (`gen_layout.build_dut(...)[2]
["geo"]`) — the figures cannot drift from the layout.

    uv run python figures.py annotated   [--params PARAMS.json] --out pam4_layout_annotated.png
    uv run python figures.py before-after --before P0.json --after P1.json --out before_after.png
    uv run python figures.py rounds --panel "label=PARAMS.json" ... --out rounds.png
(PARAMS.json = LayoutParams dict, e.g. results/<round>/summary.json's best.params;
the FINAL_LAYOUT of the generator is used when --params is omitted.)
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                    # noqa: E402
from matplotlib.patches import PathPatch                           # noqa: E402
from matplotlib.path import Path                                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))                       # layout/
import gen_layout                                                  # noqa: E402

# (layer, datatype) -> (name, colour, alpha, z)  — sg13g2.lyp colours
LAYERS = [
    ((31, 0), "NWell", "#268c6b", 0.10, 0), ((14, 0), "pSD", "#ccb899", 0.35, 1),
    ((1, 0), "Activ", "#00ff00", 0.35, 2), ((5, 0), "GatPoly", "#bf4026", 0.6, 3),
    ((36, 0), "MIM", "#268c6b", 0.5, 4), ((6, 0), "Cont", "#00ffff", 0.6, 5),
    ((8, 0), "Metal1", "#39bfff", 0.55, 6), ((19, 0), "Via1", "#ccccff", 0.9, 7),
    ((10, 0), "Metal2", "#9a9ab8", 0.55, 8), ((29, 0), "Via2", "#ff3736", 0.9, 9),
    ((30, 0), "Metal3", "#d80000", 0.45, 10), ((49, 0), "Via3", "#9ba940", 0.9, 11),
    ((50, 0), "Metal4", "#93e837", 0.5, 12), ((66, 0), "Via4", "#deac5e", 0.9, 13),
    ((67, 0), "Metal5", "#dcd146", 0.5, 14), ((125, 0), "TopVia1", "#c98a2e", 0.9, 15),
    ((126, 0), "TopMetal1", "#ffe6bf", 0.65, 16), ((133, 0), "TopVia2", "#ff8000", 0.9, 17),
    ((134, 0), "TopMetal2", "#ff8000", 0.35, 18),
]


# ---------------------------------------------------------------- rendering
def draw_gds(ax, gds: str, cell: str | None = None, layers=LAYERS) -> tuple:
    """Draw the flattened GDS polygons on `ax` (um coordinates); returns bbox."""
    import klayout.db as kdb
    ly = kdb.Layout()
    ly.read(gds)
    top = ly.cell(cell) if cell else ly.top_cell()
    dbu = ly.dbu
    for (l, d), name, col, alpha, z in layers:
        li = ly.find_layer(l, d)
        if li is None:
            continue
        reg = kdb.Region(top.begin_shapes_rec(ly.layer(l, d)))
        reg.merge()
        for poly in reg.each():
            # hull + holes (the guard ring is a rectangle with a hole)
            verts, codes = [], []
            rings = [list(poly.each_point_hull())] + [list(poly.each_point_hole(i))
                                                       for i in range(poly.holes())]
            for ring in rings:
                pts = [(pt.x * dbu, pt.y * dbu) for pt in ring] + [(ring[0].x * dbu, ring[0].y * dbu)]
                verts += pts
                codes += [Path.MOVETO] + [Path.LINETO] * (len(pts) - 2) + [Path.CLOSEPOLY]
            ax.add_patch(PathPatch(Path(verts, codes), facecolor=col, edgecolor="none",
                                   alpha=alpha, zorder=z))
    b = top.dbbox()
    ax.set_xlim(b.left - 2, b.right + 2)
    ax.set_ylim(b.bottom - 2, b.top + 2)
    ax.set_aspect("equal")
    ax.set_xlabel("x (um)")
    ax.set_ylabel("y (um)")
    return (b.left, b.bottom, b.right, b.top)


def build_to(params: gen_layout.LayoutParams, out_dir: str, dut: str = "pam4"):
    """Build the DUT once, in-process: returns (gds_path, geo dict, records)."""
    import gdsfactory as gf
    gf.clear_cache()
    c, rec, info = gen_layout.build_dut(dut, params)
    c.flatten()
    gds = os.path.join(out_dir, f"dut_{dut}.gds")
    c.write_gds(gds)
    return gds, info["geo"], rec


def load_params(path: str | None) -> gen_layout.LayoutParams:
    if not path:
        return gen_layout.LayoutParams(**gen_layout.FINAL_LAYOUT)
    d = json.load(open(path))
    if "best" in d and "params" in d["best"]:              # a harvest summary.json
        d = d["best"]["params"]
    elif "params" in d:
        d = d["params"]
    keys = {f.name for f in dataclasses.fields(gen_layout.LayoutParams)}
    return gen_layout.LayoutParams(**{k: v for k, v in d.items() if k in keys})


# ---------------------------------------------------------------- annotation
def _dim(ax, x0, y0, x1, y1, text, color="k", off=(0, 0), fs=7, lw=0.9):
    """A dimension line with arrow heads + label."""
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="<->", color=color, lw=lw,
                                shrinkA=0, shrinkB=0), zorder=40)
    ax.text((x0 + x1) / 2 + off[0], (y0 + y1) / 2 + off[1], text, fontsize=fs,
            color=color, ha="center", va="center", zorder=41,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))


def _tag(ax, x, y, text, xt, yt, color="k", fs=7):
    ax.annotate(text, xy=(x, y), xytext=(xt, yt), fontsize=fs, color=color,
                ha="center", va="center", zorder=41,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=color, lw=0.6, alpha=0.9),
                arrowprops=dict(arrowstyle="-", color=color, lw=0.7, shrinkA=0, shrinkB=0))


def annotate_knobs(ax, p: gen_layout.LayoutParams, g: dict, structural: bool = True) -> None:
    """Draw every optimizer knob of project_setup.yaml on the render."""
    K = "#1a1a1a"; E = "#8b0000"; S = "#004d99"          # layout / electrical / structural
    Xs, H, half, dcx = g["Xs"], g["H"], g["half"], g["dev_cx"]
    y0, y1 = g["y0"], g["y1"]
    X0, X1 = Xs[0], Xs[1]
    # --- floorplan spacings ---
    _dim(ax, X0 - half, y0 - 0.5, X0 + half, y0 - 0.5, f"HBT nx={p.nx}", E, off=(0, -1.6))
    _dim(ax, X0 - dcx + half, y1 + H / 2, X0 + dcx - half, y1 + H / 2, f"gap_x {p.gap_x:g}", K)
    _dim(ax, X0 + dcx + half, y0 + H / 2, X1 - dcx - half, y0 + H / 2, f"cell_gap {p.cell_gap:g}", K)
    _dim(ax, X1 + dcx + half + 1.0, y0 + H, X1 + dcx + half + 1.0, y1, f"row_gap {p.row_gap:g}", K, off=(4.5, 0))
    # --- output side ---
    yp, yn = g["y_outP"], g["y_outN"]
    xr = g["bus_x"]["outn"][1] + 1.0
    _dim(ax, xr, yp + p.out_w / 2, xr, yn - p.out_w / 2, f"out_gap {p.out_gap:g}", K, off=(6.5, 0))
    _dim(ax, xr - 2.5, yn - p.out_w / 2, xr - 2.5, yn + p.out_w / 2, f"out_w {p.out_w:g}", K, off=(-6.5, 0.6))
    if p.sub_bus == 0:
        _dim(ax, xr, g["y_sub"] + p.sub_w / 2, xr, yp - p.out_w / 2, f"out_off {p.out_off:g}", K, off=(6.5, 0))
        _dim(ax, xr, y1 + H, xr, g["y_sub"] - p.sub_w / 2, f"sub_off {p.sub_off:g}", K, off=(6.5, 0))
    else:
        _dim(ax, xr, y1 + H, xr, yp - p.out_w / 2, f"out_off {p.out_off:g}", K, off=(6.5, 0))
    _dim(ax, -p.rc_sep / 2, g["y_rc_p1"] + 1.0, p.rc_sep / 2, g["y_rc_p1"] + 1.0, f"rc_sep {p.rc_sep:g}", K, off=(0, 1.6))
    _tag(ax, -p.rc_sep / 2, (g["y_rc_p1"] + g["y_rc_p2"]) / 2, f"R_C rc_ohm={p.rc_ohm:g}\nrc_w {p.rc_w:g}",
         -p.rc_sep / 2 - 12, (g["y_rc_p1"] + g["y_rc_p2"]) / 2 + 1, E)
    ris = [x for x, n in g["risers"] if n == "outp"]
    _tag(ax, ris[-1], (y1 + H + yp) / 2, f"w_out {p.w_out:g}\n(M2 riser)", ris[-1] + 9, (y1 + H + yp) / 2 - 1.5, K)
    _tag(ax, ris[0], yp, f"stack_w {p.stack_w:g}", ris[0] - 6, yp + 4.5, K)
    # --- Cdeg / RE (cell centre) ---
    _tag(ax, X0, g["e_y"], f"Cdeg cdeg_ff={p.cdeg_ff:g}", X0 + 6, y0 - g["dy_re"] - 7.5, E)
    ex = X0 - dcx
    _tag(ax, ex, g["y_re_top"] - g["dy_re"] / 2, f"R_E re_ohm={p.re_ohm:g}\nre_w {p.re_w:g}", ex - 11, g["y_re_top"] - g["dy_re"] / 2, E)
    # --- input side ---
    by = g["bus_y"]
    names = list(by)
    ybs = [by[n] for n in names]
    xl = min(v[0] for v in g["bus_xrange"].values()) - 1.0
    _dim(ax, xl, g["y_tail"] - p.tail_h, xl, ybs[0] + p.in_bus_w / 2, f"in_off {p.in_off:g}", K, off=(-6, 0))
    _dim(ax, xl, ybs[0] - p.in_bus_w / 2, xl, ybs[1] + p.in_bus_w / 2, f"in_bus_gap {p.in_bus_gap:g}", K, off=(-7.5, 0))
    rbx = g["rb_x"]
    n0 = names[0]
    _tag(ax, rbx[n0], (g["y_rb_p1"] + g["y_rb_p2"]) / 2, f"R_B rb_ohm={p.rb_ohm:g}\nrb_w {p.rb_w:g}",
         rbx[n0] - 14, (g["y_rb_p1"] + g["y_rb_p2"]) / 2, E)
    _tag(ax, X1, g["y_tail"] - p.tail_h / 2, "tail_ma / vcasc\n(bench deck_params)", X1, g["y_tail"] - 4.5, E)
    if structural:
        txt = (f"structural knobs: cell_order={p.cell_order} ({'M0|M1|L0' if p.cell_order else 'M0|L0|M1'})  "
               f"bus_trim={p.bus_trim}  out_split={p.out_split}  sub_bus={p.sub_bus}  c_strip={p.c_strip}")
        ax.text(0.5, 1.01, txt, transform=ax.transAxes, ha="center", va="bottom", fontsize=7.5, color=S)


def fig_annotated(params: gen_layout.LayoutParams, out: str, title: str | None = None) -> None:
    with tempfile.TemporaryDirectory() as td:
        gds, geo, _ = build_to(params, td)
        fig, ax = plt.subplots(figsize=(14, 10))
        draw_gds(ax, gds)
        annotate_knobs(ax, params, geo)
        ax.set_title(title or "PAM-4 driver DAC — parameterized layout: black = layout knobs (um), "
                     "red = electrical sizing that draws geometry, blue = structural options",
                     fontsize=9, pad=18)
        legend = [plt.Rectangle((0, 0), 1, 1, fc=c, alpha=a) for _, n, c, a, _ in LAYERS if n in
                  ("Activ", "Metal1", "Metal2", "Metal3", "Metal4", "TopMetal1", "TopMetal2", "MIM")]
        ax.legend(legend, [n for _, n, _, _, _ in LAYERS if n in
                           ("Activ", "Metal1", "Metal2", "Metal3", "Metal4", "TopMetal1", "TopMetal2", "MIM")],
                  loc="lower right", fontsize=7, ncol=4, framealpha=0.9)
        fig.tight_layout()
        fig.savefig(out, dpi=150)
        plt.close(fig)


# ---------------------------------------------------------------- before / after
def _score_text(m: dict | None, wrap: bool = False) -> str:
    if not m:
        return ""
    keys = [("s11", "S11 {:.2f} dB"), ("s22", "S22 {:.2f} dB"), ("msb_gain", "MSB {:.2f} dB"),
            ("lsb_gain", "LSB {:.2f} dB"), ("bw", "BW {:.1f} GHz"), ("swing", "swing {:.2f} Vpp"),
            ("power", "{:.0f} mW"), ("area_um2", "{:.0f} um2")]
    parts = [f.format(m[k]) for k, f in keys if k in m]
    if wrap and len(parts) > 4:
        return "   ".join(parts[:4]) + "\n" + "   ".join(parts[4:])
    return "   ".join(parts)


def _diff_boxes(ax, p0: gen_layout.LayoutParams, p1: gen_layout.LayoutParams, g1: dict) -> None:
    """Outline the regions that changed between two parameter sets."""
    C = "#d62728"
    def box(x0, y0, x1, y1, label):
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=C, lw=1.4, ls="--", zorder=50))
        ax.text(x0, y1 + 0.4, label, color=C, fontsize=7, ha="left", va="bottom", zorder=51,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
    yp, yn = g1["y_outP"], g1["y_outN"]
    if (p0.bus_trim, p0.out_split, p0.out_gap, p0.out_w) != (p1.bus_trim, p1.out_split, p1.out_gap, p1.out_w):
        xs = [v for r in g1["bus_x"].values() for v in r]
        box(min(xs) - 1, yp - 2, max(xs) + 1, yn + 2,
            f"output buses: bus_trim {p0.bus_trim}->{p1.bus_trim}, out_split {p0.out_split}->{p1.out_split}, "
            f"out_gap {p0.out_gap:g}->{p1.out_gap:g}")
    if p0.sub_bus != p1.sub_bus:
        for xg in g1["gap_xs"]:
            box(xg - 1.5, g1["y0"] + g1["H"] / 2, xg + 1.5, g1["ring_top"], f"sub_bus {p0.sub_bus}->{p1.sub_bus}")
    if p0.c_strip != p1.c_strip:
        for X in g1["Xs"]:
            box(X - g1["dev_cx"] - g1["half"], g1["y1"] + g1["H"] - 2.5, X + g1["dev_cx"] + g1["half"],
                g1["y1"] + g1["H"] + 0.5, f"c_strip {p0.c_strip}->{p1.c_strip}")
    if p0.cell_order != p1.cell_order:
        for X, (pre, _, _) in zip(g1["Xs"], g1["cells"]):
            ax.text(X, g1["y0"] - 1.0, pre, color=C, fontsize=9, ha="center", va="top", weight="bold", zorder=51)
    changed = [f.name for f in dataclasses.fields(gen_layout.LayoutParams)
               if getattr(p0, f.name) != getattr(p1, f.name)
               and f.name not in ("bus_trim", "out_split", "sub_bus", "c_strip", "cell_order")]
    if changed:
        txt = "moved knobs: " + ", ".join(f"{k} {getattr(p0, k):g}->{getattr(p1, k):g}" for k in changed)
        ax.text(0.0, -0.08, txt, transform=ax.transAxes, fontsize=7, color=C, ha="left", va="top", wrap=True)


def fig_before_after(p0, p1, out: str, m0: dict | None = None, m1: dict | None = None,
                     labels=("before: layout of record", "after: accepted co-design point")) -> None:
    with tempfile.TemporaryDirectory() as td:
        d0, d1 = os.path.join(td, "a"), os.path.join(td, "b")
        os.makedirs(d0); os.makedirs(d1)
        g0, geo0, _ = build_to(p0, d0)
        g1, geo1, _ = build_to(p1, d1)
        fig, axs = plt.subplots(2, 1, figsize=(14, 15))
        b0 = draw_gds(axs[0], g0)
        b1 = draw_gds(axs[1], g1)
        # same scale: common limits
        xl = (min(b0[0], b1[0]) - 2, max(b0[2], b1[2]) + 2)
        yl = (min(b0[1], b1[1]) - 4, max(b0[3], b1[3]) + 4)
        for ax, lab, m in zip(axs, labels, (m0, m1)):
            ax.set_xlim(*xl); ax.set_ylim(*yl)
            ax.set_title(f"{lab}\n{_score_text(m)}", fontsize=9)
        _diff_boxes(axs[1], p0, p1, geo1)
        fig.tight_layout()
        fig.savefig(out, dpi=140)
        plt.close(fig)


def fig_rounds(panels: list[tuple[str, gen_layout.LayoutParams, dict | None]], out: str) -> None:
    """One column per round: layout render + scorecard line."""
    n = len(panels)
    fig, axs = plt.subplots(1, n, figsize=(7.2 * n, 6.4))
    if n == 1:
        axs = [axs]
    axs = list(axs)
    with tempfile.TemporaryDirectory() as td:
        boxes = []
        for i, (ax, (lab, p, m)) in enumerate(zip(axs, panels)):
            d = os.path.join(td, str(i)); os.makedirs(d)
            gds, geo, _ = build_to(p, d)
            boxes.append(draw_gds(ax, gds))
            ax.set_title(f"{lab}\n{_score_text(m, wrap=True)}", fontsize=8.5)
        xl = (min(b[0] for b in boxes) - 2, max(b[2] for b in boxes) + 2)
        yl = (min(b[1] for b in boxes) - 4, max(b[3] for b in boxes) + 4)
        for ax in axs:
            ax.set_xlim(*xl); ax.set_ylim(*yl)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------- CLI
def _metrics_of(path: str | None) -> dict | None:
    if not path:
        return None
    d = json.load(open(path))
    if "best" in d:
        return d["best"].get("scalars")
    return d.get("scalars", d)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("annotated"); a.add_argument("--params"); a.add_argument("--out", required=True); a.add_argument("--title")
    b = sub.add_parser("before-after"); b.add_argument("--before"); b.add_argument("--after", required=True)
    b.add_argument("--before-metrics"); b.add_argument("--after-metrics"); b.add_argument("--out", required=True)
    b.add_argument("--labels", nargs=2, default=("before: layout of record", "after: accepted co-design point"))
    r = sub.add_parser("rounds"); r.add_argument("--panel", action="append", required=True,
                                                 help="label=PARAMS.json[=METRICS.json]"); r.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "annotated":
        fig_annotated(load_params(args.params), args.out, args.title)
    elif args.cmd == "before-after":
        fig_before_after(load_params(args.before), load_params(args.after), args.out,
                         _metrics_of(args.before_metrics), _metrics_of(args.after_metrics), tuple(args.labels))
    else:
        panels = []
        for spec in args.panel:
            parts = spec.split("=")
            lab, pj = parts[0], (parts[1] or None)
            mj = parts[2] if len(parts) > 2 else (pj if pj and pj.endswith("summary.json") else None)
            panels.append((lab, load_params(pj), _metrics_of(mj)))
        fig_rounds(panels, args.out)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
