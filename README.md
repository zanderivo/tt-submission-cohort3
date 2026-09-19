# Four-Metric VGA Nearest-Prototype Visualizer

This is a Tiny Tapeout 1x2 Verilog project targeting the **IHP 26b shuttle** and the **IHP SG13G2 130 nm BiCMOS PDK**. Its physical-delivery infrastructure is aligned with [`TinyTapeout/ttihp-verilog-template` revision `6598bef`](https://github.com/TinyTapeout/ttihp-verilog-template/commit/6598bef4d3159f19fe471a2a2225df52e6f5ad25). The devcontainer intentionally uses LibreLane 3.0.5 to match the `ttihp26b` action default.

`tt_um_zanderivo_voronoi` produces a 640x480 TinyVGA display that classifies a 256x240 logical viewport against four movable prototypes. It supports L1, L-infinity, an octagonal L2 approximation, and binary-coordinate Hamming distance, with deterministic lowest-ID ties. See [the generated project documentation](docs/info.md) for the complete behavior and hardware instructions.

## Frozen behavior

| Item | Exact behavior |
|---|---|
| Clock/reset/enable | External 25,175,000 Hz pixel clock; active-low asynchronous reset; `ena` is ignored and never freezes or blanks timing. |
| Raster | 800x525 total; 640x480 active; HSync low at `h=656..751`; VSync low at `v=490..491`; blanking RGB is black. |
| Layout | Viewport `h=0..511,v=0..479`; logical query `(h[8:1],v[8:1])`; sidebar `h=512..639`. |
| Reset prototypes | C0 `(64,60)`, C1 `(192,60)`, C2 `(64,180)`, C3 `(192,180)`. |
| Metrics | `00`: `dx+dy`; `01`: `max(dx,dy)`; `10`: `max(dx,dy)+floor(min(dx,dy)/2)`; `11`: popcount of `{qx^cx,qy^cy}`. |
| Region colors | C0 `(3,1,0)`, C1 `(0,3,0)`, C2 `(0,2,3)`, C3 `(2,0,3)` in 2-bit RGB; ties select the lowest ID. |
| Crosshairs | White where `(dy<=1 && dx<=4) || (dx<=1 && dy<=4)` for any prototype. |
| Controls | Every `ui_in` bit is synchronized through two flip-flops. Mode and training requests latch only at `frame_tick=(799,524)`. |
| Manual update | A synchronized Step rising edge captures one centroid/axis/direction command when the one-entry pending slot is empty. It applies at a frame boundary, moves one logical unit, saturates X to `0..255` and Y to `0..239`, and takes priority over training. Holding Step does not repeat. |
| Training source | 16-bit right-shifting Galois LFSR reset to `16'hACE1`; each frame `next=(current>>1) XOR 16'hB400` iff old bit 0 is 1. Candidate X is `lfsr[7:0]`, Y is `lfsr[15:8]`; Y values 240..255 are rejected. The LFSR advances every frame regardless of enable, validity, or manual priority. |
| Training update | At frame tick, the ending frame's mode, current sample, and current prototypes select the winner. Each winning coordinate moves toward the sample by `abs(sample-centroid)>>3`, with symmetric direction and defensive saturation. |
| Sidebar | Mode rows use `h=528..623` and `v=32..63,80..111,128..159,176..207`; selected is white `(3,3,3)`, inactive is gray `(1,1,1)`. Training block is `h=528..623,v=256..303`, green `(0,3,0)` on or red `(1,0,0)` off. Palette chips are `h=528..547,553..572,578..597,603..622`, `v=336..367`. Sidebar has priority over crosshairs. |

TinyVGA outputs are `uo_out[0]=R1`, `[1]=G1`, `[2]=B1`, `[3]=VSync_n`, `[4]=R0`, `[5]=G0`, `[6]=B0`, and `[7]=HSync_n`. All `uio` pins remain inputs.

## Repository layout

| Path | Purpose |
|---|---|
| `src/project.v` | Verilog-2005-compatible visualizer and distance lanes |
| `src/config.json` | LibreLane 1x2 IHP SG13G2 hardening configuration |
| `test/` | RTL/reference-model and IHP gate-level verification assets |
| `info.yaml` | Tiny Tapeout metadata, source list, clock, and pinout |
| `.github/workflows/` | Test, IHP GDS/precheck/GL/viewer, docs, and FPGA automation |
| `scripts/` | Reproducible Windows setup and local verification |

## Controls

`ui_in[1:0]` requests the metric, `ui_in[2]` requests training, `ui_in[4:3]` selects the manual prototype, `ui_in[5]` selects X/Y, `ui_in[6]` selects decrement/increment, and a rising edge on `ui_in[7]` submits the manual command. Keep the selector bits stable around the Step edge. Displayed mode and training state change only on frame boundaries.

## Prerequisites and setup

Install Git, GitHub CLI, Icarus Verilog/VVP 11 or newer, GTKWave, GNU Make, and Python 3.10 or newer. On Windows, run:

```powershell
pwsh -File .\scripts\setup-windows.ps1
```

On Linux, install the system tools and then run:

```bash
python3 -m pip install -r test/requirements.txt
```

For local IHP hardening or gate-level simulation, use the repository dev container or another environment containing `ihp-sg13g2` under `PDK_ROOT`.

## Local quality gate

From the repository root on Windows:

```powershell
pwsh -File .\scripts\check.ps1
```

Or run the portable equivalent from `test/`:

```bash
python ../scripts/validate_project.py
make clean
make check
```

This sequence validates metadata and module bindings, qualifies the integer model, compiles the Verilog, and runs the RTL behavior suite. Physical IHP hardening, Tiny Tapeout precheck, and routed gate-level simulation are additional conditional checks: they are established only when the `gds` workflow completes successfully for the revision. This repository does not contain routed-results evidence.

## Physical use

Supply the required 25.175 MHz clock and connect a TinyVGA PMOD or equivalent resistor-DAC VGA interface to `uo_out`. Connect a VGA display that accepts conventional 640x480 timing. Use switches for metric/training/selectors and a debounced or deliberate push button for Step; the design detects synchronized rising edges but does not include a mechanical debounce timer.

## GitHub CI/CD

The `test` workflow runs metadata validation, model tests, lint, and RTL simulation on pushes, pull requests, and manual dispatches. The `gds` workflow is configured to preserve the official `ttihp26b` action contract with `pdk: ihp-sg13g2`; physical hardening, precheck, routed gate-level simulation, and viewer generation are accepted only when that workflow succeeds for the committed revision. No routed evidence is included in this checkout. The `docs` and manual FPGA workflows use the same target release.

Before Tiny Tapeout submission, confirm the test, GDS, precheck, gate-level test, and viewer jobs are green for the committed revision. No commit is created by the local implementation workflow.
