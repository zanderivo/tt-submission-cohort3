# Two-Metric VGA Nearest-Prototype Visualizer

A Tiny Tapeout **1x1** VGA graphics project written in Verilog. It displays four colored nearest-prototype regions at 640×480 and lets the user select the distance metric, move prototypes, or enable simple online training.

- **Author:** zanderivo
- **Top module:** `tt_um_zanderivo_voronoi`
- **Clock:** 25.175 MHz

## How it works

The design generates standard 640×480 VGA timing directly from the pixel clock. The left side of the screen is a 256×240 logical viewport containing four movable prototypes. Each pixel is assigned the color of its nearest prototype; white crosshairs mark their current positions.

`ui_in[0]` selects one of two distance metrics:

| Value | Metric |
|---|---|
| `0` | Manhattan / L1 |
| `1` | Chebyshev / L-infinity |

`ui_in[1]` is reserved and ignored. The right side of the display shows the selected metric, training status, and prototype-color key. Metric and training changes become active at the next frame boundary.

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

A manual move is applied at the next frame boundary. Keep the selector pins stable while pulsing Step. Online training periodically moves the nearest prototype toward an internally generated sample.

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
