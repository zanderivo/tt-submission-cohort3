[![gds](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/gds.yaml/badge.svg)](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/gds.yaml)
[![test](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/test.yaml/badge.svg)](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/test.yaml)
[![docs](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/docs.yaml/badge.svg)](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/docs.yaml)

# Tiny Tapeout Verilog ASIC Development Baseline

This repository is a Tiny Tapeout 1x1 Sky130 Verilog project based on `TinyTapeout/ttsky-verilog-template`. It currently contains the mandatory **smoke-test tile**, not the final application: `tt_um_smoketest` is an asynchronously reset 8-bit registered counter used to qualify the local and GitHub RTL-to-GDS pipeline.

See [the generated project documentation](docs/info.md) for operation and hardware testing details.

## Repository layout

| Path | Purpose |
|---|---|
| `src/project.v` | Synthesizable Tiny Tapeout top module |
| `src/config.json` | LibreLane 1x1 Sky130 hardening configuration |
| `test/tb.v` | Cocotb-compatible RTL and gate-level wrapper |
| `test/test.py` | Self-checking ten-cycle smoke test |
| `test/Makefile` | Icarus simulation, lint, and gate-level targets |
| `info.yaml` | Tiny Tapeout metadata, source list, and pinout |
| `.github/workflows/` | Test, GDS/precheck/GL/viewer, docs, and FPGA automation |
| `scripts/` | Reproducible Windows setup and local verification |

## Prerequisites

- Git and GitHub CLI
- Icarus Verilog/VVP 11 or newer
- GTKWave
- GNU Make
- Python 3.10 or newer with the pinned packages in `test/requirements.txt`

### Windows setup

Open PowerShell in the repository root and run:

```powershell
pwsh -File .\scripts\setup-windows.ps1
```

The script installs pinned packages with WinGet, updates the user PATH, and installs the Python dependencies. Open a new terminal afterward. Authentication is intentionally interactive:

```powershell
gh auth login
```

### Linux setup

Install Icarus Verilog, GTKWave, GNU Make, Python 3.10+, and GitHub CLI with your system package manager, then run:

```bash
python3 -m pip install -r test/requirements.txt
```

## Local quality gate

On Windows, run the complete check from the repository root:

```powershell
pwsh -File .\scripts\check.ps1
```

Or run the portable commands directly:

```bash
cd test
make lint
make clean
make
```

Expected result: metadata/top-module bindings validate and one Cocotb test passes, with the counter producing values 1 through 10 on consecutive rising clock edges. The waveform is written to `test/tb.fst` and can be opened with `gtkwave test/tb.fst test/tb.gtkw`.

## GitHub CI/CD

The `test` workflow runs lint and RTL simulation on pushes, pull requests, and manual dispatches. The `gds` workflow runs the four Tiny Tapeout delivery jobs: LibreLane GDS hardening, precheck, gate-level simulation, and viewer generation.

After authenticating GitHub CLI:

```powershell
gh workflow run test.yaml --repo zanderivo/tt-submission-cohort3 --ref main
gh run list --repo zanderivo/tt-submission-cohort3 --limit 10
gh run watch --repo zanderivo/tt-submission-cohort3
```

Do not trigger a final GDS delivery from uncommitted local files. Once an intentional commit is pushed, run or inspect `gds.yaml` in the same way.

## Final-application handoff checklist

Before replacing the smoke tile:

1. Choose the application behavior and unique top name `tt_um_zanderivo_<project_name>`.
2. Preserve the Tiny Tapeout interface and assign every output.
3. Update `RTL_TOP` in `test/Makefile`, the DUT in `test/tb.v`, and `top_module` in `info.yaml` together.
4. Replace the smoke assertions with comprehensive application tests.
5. Update `info.yaml`, this README, and `docs/info.md` with the final clock and pinout.
6. Keep multi-bit hardware multipliers, inferred latches, and large inferred memories out of the design.
7. Pass local lint/simulation, then confirm `test`, `gds`, `precheck`, `gl_test`, and `viewer` are green before submission.

No final application RTL has been started in this baseline.
