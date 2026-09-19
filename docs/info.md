## How it works

This is the development smoke-test design used before implementation of the final application. The top module, `tt_um_smoketest`, contains one 8-bit register. An active-low asynchronous reset on `rst_n` immediately clears the register to `0x00`. On every rising edge of `clk` while reset is inactive, the register increments modulo 256. The current count is continuously presented on `uo_out[7:0]`.

The dedicated inputs, bidirectional inputs, and Tiny Tapeout enable input do not control this smoke-stage behavior. They are consumed by an unused-input reduction expression to keep lint and synthesis clean. All bidirectional output values and output enables are tied low, so every `uio` pin remains an input and is never driven by the tile.

State flow:

1. `rst_n = 0`: enter/reset state and force the count to zero.
2. `rst_n = 1`: on each rising clock edge, transition to `(count + 1) mod 256`.
3. Drive the eight count bits on `uo_out` continuously.

## How to test

### Automated RTL verification

From the repository root on Windows:

```powershell
pwsh -File .\scripts\check.ps1
```

The equivalent portable sequence is `make lint`, `make clean`, then `make` from the `test` directory. The Cocotb test asserts reset, verifies that `uo_out` clears asynchronously, confirms all `uio` drivers are disabled, releases reset on a falling clock edge, and checks output values 1 through 10 on ten consecutive rising edges.

### Physical verification

1. Apply a clock no faster than the documented 50 MHz target to `clk`.
2. Pull `rst_n` low and verify all eight `uo_out` signals are low.
3. Return `rst_n` high.
4. Observe `uo_out[0]` toggling every clock, `uo_out[1]` every two clocks, and each successive bit at half the preceding frequency.
5. Confirm that all `uio` pins remain high-impedance inputs.

For a human-visible test, use a slow external clock or divide/step the clock externally; the normal ASIC clock is too fast to observe directly on LEDs.

## External hardware

No external hardware is required for automated simulation. Physical testing can use a Tiny Tapeout demo board, eight current-limited LEDs or a logic analyzer connected to `uo_out[7:0]`, and an external slow/step clock source if the board does not provide one. No PMOD is required for this smoke-stage counter.
