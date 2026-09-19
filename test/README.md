# VGA nearest-prototype verification

This directory verifies `tt_um_zanderivo_voronoi` against the frozen integer contract. It contains two layers:

- `model.py` is the dependency-free integer oracle for VGA timing, viewport downsampling, all four metrics, lowest-ID ties, palette/crosshair rendering, synchronized pending commands, the `0xACE1`/`0xB400` LFSR, manual priority, and symmetric `abs(delta) >> 3` training.
- `test_model.py` qualifies that oracle with directed, randomized, complete-raster, maximal-LFSR-cycle, saturation, synchronization, update-order, and 5,000-boundary tests.
- `test.py` is the Cocotb DUT suite. It checks reset/tie-offs at active, porch, HSync, and VSync positions; real-lane extrema/random metric vectors and top-level tie cases; one exact 420,000-clock frame; model-compared selected scanlines in every mode; visible frame-latched transitions; manual one-shot and priority; accepted/rejected LFSR training; a 5,000-edge actual-RTL/model boundary trace; and actual-RTL saturation for every centroid, axis, and bound. Hierarchy-dependent tests are explicitly RTL-only. Gate coverage uses only tile ports.

The mode/manual/training hierarchy tests are not claimed as gate-compatible. At gate level Cocotb reports them as skipped and executes dedicated port-only behavior in the complete-frame test.

## Frozen interface summary

`ui_in[1:0]` requests L1/Linf/octagonal-L2/Hamming, bit 2 requests training, bits 4:3 select a centroid, bit 5 selects Y, bit 6 selects increment, and bit 7 is Step. TinyVGA RGB occupies `uo_out[2:0]` and `[6:4]`, active-low VSync is bit 3, and active-low HSync is bit 7. `uio_out`/`uio_oe` are zero and `ena` is ignored.

The raster is 800x525 with 640x480 active video, a 512x480 viewport, and `query=(h>>1,v>>1)`. Reset centroids are `(64,60)`, `(192,60)`, `(64,180)`, `(192,180)`. The LFSR transition is `(state >> 1) XOR 16'hB400` iff the old LSB is one; X is the low byte and Y the high byte, valid only for Y below 240.

## Setup and validation

Install the pinned packages:

```sh
python3 -m pip install -r requirements.txt
```

Run the fast, simulator-independent model suite first:

```sh
python -m pytest -q test_model.py
# or: make model
```

Run the complete portable quality gate from `test/`:

```sh
python ../scripts/validate_project.py
make clean
make check
```

The validator checks metadata and project/module bindings; `make check` runs the independent model, lint, and RTL simulation. The full RTL suite includes several frame-boundary waits, but only one test inspects every clock in a frame. Wave dumping is disabled by default so Icarus remains practical.

On Windows the repository wrapper remains available:

```powershell
pwsh -File ..\scripts\check.ps1
```

## Gate-level compact subset

After hardening, copy the final netlist to `gate_level_netlist.v` and use an environment with the IHP SG13G2 PDK at `$PDK_ROOT/ihp-sg13g2`:

```sh
make clean
make GATES=yes
```

At gate level, hierarchy-dependent checks are reported as skipped. Reset/tie-offs and one complete 420,000-clock port-level timing frame still run; three additional boundary-aligned partial frames cover all four modes, one synchronized manual update, and one accepted training update. The checks validate exact sync intervals, black blanking, selected model-compared scanlines, and viewport/sidebar/active/blanking edges using only tile ports—no internal hierarchy, force, or behavioral-only probes. This acceptance applies only when a real post-hardening netlist and matching IHP PDK are supplied.

## Waveforms and focused runs

Enable an FST only when debugging:

```sh
make clean
make WAVES=1
# then: gtkwave tb.fst tb.gtkw
```

Cocotb filters can select a focused test, for example:

```sh
make COCOTB_TEST_FILTER=test_complete_800x525_frame_from_ports
```

Generated `results.xml`, `tb.fst`, and `sim_build/` contents are build artifacts and are not hand-maintained.
