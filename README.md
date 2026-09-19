# Two-Metric VGA Nearest-Prototype Visualizer

A Tiny Tapeout **1x1** VGA graphics project written in Verilog. It displays four colored nearest-prototype regions at 640×480 and lets the user select the distance metric, move prototypes, or enable simple online training.

- **Author:** zanderivo
- **Top module:** `tt_um_zanderivo_voronoi`
- **Clock:** 25.175 MHz

## How it works

The design generates standard 640×480 VGA timing directly from the pixel clock. The left 512×480 pixels are a 64×60 logical viewport containing four movable prototypes, so each logical cell is an 8×8 block of screen pixels. Every cell is assigned the color of its nearest prototype; white crosshairs mark their current positions.

The 64×60 grid and six-bit prototype coordinates are a deliberate resolution choice: they keep the four parallel distance lanes, the argmin tree, and the prototype registers inside a single Tiny Tapeout tile. Region edges are therefore blocky at 8-pixel granularity.

`ui_in[0]` selects one of two distance metrics:

| Value | Metric |
|---|---|
| `0` | Manhattan / L1 |
| `1` | Chebyshev / L-infinity |

`ui_in[1]` is reserved and ignored. Metric and training changes become active at the next frame boundary.

The right 128×480 pixels are a geometric sidebar with no text. Its left 64-pixel column carries two metric rows (the selected one is white, the other gray) and a training block (green when training, dark red when idle). Its right 64-pixel column carries the four prototype colors stacked top to bottom as a palette key.

## Controls

| Pin | Function |
|---|---|
| `ui_in[0]` | Distance-metric selection |
| `ui_in[1]` | Reserved; ignored |
| `ui_in[2]` | Enable online training |
| `ui_in[4:3]` | Select prototype 0–3 |
| `ui_in[5]` | Axis: `0` X, `1` Y |
| `ui_in[6]` | Direction: `0` decrement, `1` increment |
| `ui_in[7]` | Rising edge submits a one-coordinate manual move |

A manual move is applied at the next frame boundary and shifts the prototype by one logical cell, which is 8 screen pixels. Keep the selector pins stable from the Step edge through the following frame boundary, because the selector, axis, and direction payload is sampled when the move is applied.

Online training draws one pseudo-random sample per frame from an internal 16-bit LFSR, rejects samples outside the viewport, and moves only the nearest prototype toward the sample by a quarter of the remaining distance on each axis. Deltas smaller than four cells round down to zero, so prototypes settle near their cluster centers rather than drifting forever.

## VGA outputs

| Pin | Output |
|---|---|
| `uo_out[0]`, `uo_out[4]` | Red MSB, LSB |
| `uo_out[1]`, `uo_out[5]` | Green MSB, LSB |
| `uo_out[2]`, `uo_out[6]` | Blue MSB, LSB |
| `uo_out[3]` | Active-low VSync |
| `uo_out[7]` | Active-low HSync |

## How to use it

Connect a TinyVGA-compatible VGA PMOD to `uo_out`, a VGA monitor that supports 640×480, and switches or buttons to `ui_in`. Supply a stable 25.175 MHz clock, release reset, select a metric, and use the prototype controls to move a crosshair. Use a debounced button for Step.

See [docs/info.md](docs/info.md) for the short project datasheet.
