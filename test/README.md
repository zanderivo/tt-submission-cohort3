# Tiny Tapeout IHP 26b smoke-test bench

This directory contains the Cocotb harness for `tt_um_smoketest`. It uses Icarus Verilog to compile the RTL and checks asynchronous reset, unused bidirectional pins, and ten consecutive counter increments.

## Setup

Install the exact Python packages listed in `requirements.txt`. On Windows, run `..\scripts\setup-windows.ps1` from PowerShell; on Linux or in the dev container, run:

```sh
python3 -m pip install -r requirements.txt
```

When the final application replaces the smoke tile, update all of these together:

- `RTL_TOP` and `PROJECT_SOURCES` in `Makefile`
- the instantiated DUT in `tb.v`
- the assertions in `test.py`
- `project.top_module` and `project.source_files` in `../info.yaml`

## RTL quality gate

From this directory:

```sh
make lint
make clean
make
```

The simulation writes `results.xml` and the `tb.fst` waveform. On Windows, the repository-level wrapper performs the same checks and rejects failures recorded in the XML:

```powershell
pwsh -File ..\scripts\check.ps1
```

## IHP gate-level simulation

Use an environment with the `ihp-sg13g2` PDK available at `$PDK_ROOT/ihp-sg13g2`. After hardening the project, copy `../runs/wokwi/final/nl/tt_um_smoketest.nl.v` to `gate_level_netlist.v`, then run:

```sh
make clean
make GATES=yes
```

The gate-level target loads the official IHP SG13G2 I/O and standard-cell Verilog models. The testbench follows the IHP template contract and does not add the Sky130-only `VPWR`/`VGND` ports.

## Waveforms

Open the FST waveform with GTKWave:

```sh
gtkwave tb.fst tb.gtkw
```

To generate VCD instead, change the dump filename in `tb.v` to `tb.vcd` and invoke `make FST=`.
