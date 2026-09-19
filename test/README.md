# Verification

The tests verify the four-metric VGA nearest-prototype design.

- `model.py` is the Python reference model for timing, metrics, prototype updates, and training.
- `test_model.py` checks the reference model.
- `test.py` uses Cocotb to test the RTL and VGA outputs.

Run the local checks from the repository root on Windows:

```powershell
pwsh -File .\scripts\check.ps1
```

Or run from this directory:

```sh
python ../scripts/validate_project.py
make clean
make check
```

The design uses an 800×525 VGA raster with a 640×480 active area. `ui_in[1:0]` selects L1, L-infinity, octagonal-L2, or Hamming distance; the remaining controls select and move prototypes or enable training.
