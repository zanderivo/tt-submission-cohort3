[![gds](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/gds.yaml/badge.svg)](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/gds.yaml)
[![test](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/test.yaml/badge.svg)](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/test.yaml)
[![docs](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/docs.yaml/badge.svg)](https://github.com/zanderivo/tt-submission-cohort3/actions/workflows/docs.yaml)

# Tiny Tapeout IHP 26b Verilog ASIC Development Baseline

This repository is a Tiny Tapeout 1x1 Verilog project targeting the **IHP 26b shuttle** and the **IHP SG13G2 130 nm BiCMOS PDK**. Its physical-delivery infrastructure is aligned with [`TinyTapeout/ttihp-verilog-template` revision `6598bef`](https://github.com/TinyTapeout/ttihp-verilog-template/commit/6598bef4d3159f19fe471a2a2225df52e6f5ad25). The devcontainer intentionally uses LibreLane 3.0.5 to match the current `ttihp26b` action default.

It currently contains the mandatory **smoke-test tile**, not the final application: `tt_um_smoketest` is an asynchronously reset 8-bit registered counter used to qualify the local and GitHub RTL-to-GDS pipeline.

See [the generated project documentation](docs/info.md) for operation and hardware testing details.

## Repository layout

| Path | Purpose |
|---|---|
| `src/project.v` | Synthesizable Tiny Tapeout top module |
| `src/config.json` | LibreLane 1x1 IHP SG13G2 hardening configuration |
| `test/tb.v` | Cocotb-compatible RTL and IHP gate-level wrapper |
| `test/test.py` | Self-checking ten-cycle smoke test |
| `test/Makefile` | Icarus simulation, lint, and IHP gate-level targets |
| `info.yaml` | Tiny Tapeout metadata, source list, and pinout |
| `.github/workflows/` | Test, IHP GDS/precheck/GL/viewer, docs, and FPGA automation |
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

For local IHP hardening or gate-level simulation, use the repository dev container or another environment containing the `ihp-sg13g2` PDK under `PDK_ROOT`.

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

Expected result: the metadata, cross-file module bindings, and IHP 26b target bindings validate, and one Cocotb test passes with the counter producing values 1 through 10 on consecutive rising clock edges. The waveform is written to `test/tb.fst` and can be opened with `gtkwave test/tb.fst test/tb.gtkw`.

This local gate validates metadata and RTL. Physical IHP hardening, Tiny Tapeout precheck, and the generated gate-level netlist are validated by the `gds` workflow.

## GitHub CI/CD

The `test` workflow runs lint and RTL simulation on pushes, pull requests, and manual dispatches. The `gds` workflow uses the official `ttihp26b` action contract with `pdk: ihp-sg13g2` and runs LibreLane GDS hardening, precheck, IHP gate-level simulation, and viewer generation. The `docs` and manual FPGA workflows also use the `ttihp26b` action release.

After authenticating GitHub CLI:

```powershell
gh workflow run test.yaml --repo zanderivo/tt-submission-cohort3 --ref main
gh run list --repo zanderivo/tt-submission-cohort3 --limit 10
gh run watch --repo zanderivo/tt-submission-cohort3
```

Do not trigger a final GDS delivery from uncommitted local files. Once an intentional commit is pushed, run or inspect `gds.yaml` in the same way. Before submission through the Tiny Tapeout portal, confirm the GDS, precheck, gate-level test, and viewer jobs are green for the committed revision.

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
