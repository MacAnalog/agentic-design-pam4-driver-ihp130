"""device_records() must equal the records build_dut() produces while drawing
(the per-trial netlist writers of the co-design flow rely on it)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "layout"))


@pytest.mark.parametrize("dut", ["lsb", "msb", "pam4"])
def test_records_match_build(dut):
    import gdsfactory as gf
    import gen_layout as g

    for params in (g.LayoutParams(), g.LayoutParams(**g.FINAL_LAYOUT)):
        gf.clear_cache()
        _, rec, _ = g.build_dut(dut, params)
        exp = g.device_records(dut, params)
        for k in ("hbt", "res", "cap"):
            assert sorted(map(str, rec[k])) == sorted(map(str, exp[k])), (dut, k)
