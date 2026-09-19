## How it works

This project is a 1x1 Tiny Tapeout VGA nearest-prototype visualizer. It uses a 25.175 MHz pixel clock to generate a 640×480 display. Four colored prototypes divide the left 512×480 pixels into nearest-prototype regions on a 64×60 logical grid, so each cell is an 8×8 block of screen pixels. The right 128×480 pixels show the active metric, the training status, and a prototype-color key using geometric blocks only.

Six-bit logical coordinates are a deliberate resolution choice that keeps four parallel distance lanes, the argmin tree, and the prototype state inside one tile. Region boundaries are blocky at 8-pixel granularity as a result.

The input metric selects how distance is measured:

| `ui_in[0]` | Metric |
|---|---|
| `0` | Manhattan / L1 |
| `1` | Chebyshev / L-infinity |

`ui_in[1]` is reserved and ignored. White crosshairs show the prototype positions. Equal distances choose the lower-numbered prototype. The selected metric and training request update at a frame boundary so the displayed frame stays coherent.

## Controls

| Pin | Function |
|---|---|
| `ui_in[0]` | Select the distance metric |
| `ui_in[1]` | Reserved; ignored |
| `ui_in[2]` | Enable online training |
| `ui_in[4:3]` | Select prototype 0–3 |
| `ui_in[5]` | Select axis: `0` X, `1` Y |
| `ui_in[6]` | Select direction: `0` decrement, `1` increment |
| `ui_in[7]` | Step strobe for a manual move |

A rising edge on Step moves the selected coordinate by one logical cell, which is 8 screen pixels, at the next frame boundary. Keep the selector, axis, and direction inputs stable from the Step edge through that frame boundary, since the payload is sampled when the move is applied.

Online training takes one pseudo-random sample per frame from an internal 16-bit LFSR, rejects samples below the viewport, and moves only the nearest prototype a quarter of the way toward the sample on each axis. The update reuses the winning display lane's own delta, so training adds no second distance datapath.

## How to use

1. Connect a TinyVGA-compatible VGA PMOD to `uo_out` and a monitor that supports 640×480.
2. Supply a stable 25.175 MHz clock and release reset.
3. Use `ui_in[0]` to select a metric and observe the region pattern change on the next frame.
4. Select a prototype, axis, and direction; then pulse `ui_in[7]` to move its crosshair.
5. Set `ui_in[2]` high to enable online training.

## External hardware

- TinyVGA-compatible VGA PMOD or resistor-DAC interface
- VGA monitor capable of 640×480
- 25.175 MHz clock source
- Switches or buttons for `ui_in`; use a debounced source for Step

The VGA outputs are `R1,G1,B1,VSync_n,R0,G0,B0,HSync_n` on `uo_out[0:7]`. The bidirectional pins are unused.
