## How it works

`tt_um_zanderivo_voronoi`, the **Four-Metric VGA Nearest-Prototype Visualizer**, drives a TinyVGA display directly from an external 25,175,000 Hz pixel clock. The design renders four nearest-prototype regions, exposes four selectable distance metrics, accepts frame-coherent manual prototype nudges, and can perform one online training opportunity per frame. It is synthesizable Verilog-2005 and uses no memories or SystemVerilog constructs.

### Frozen behavior table

| Function | Exact contract |
|---|---|
| Reset | `rst_n` is active-low and asynchronous. Raster and synchronized controls clear; mode becomes L1; training turns off; prototypes reset to C0 `(64,60)`, C1 `(192,60)`, C2 `(64,180)`, C3 `(192,180)`; pending command clears; LFSR becomes `16'hACE1`. |
| Enable | `ena` is intentionally ignored. Raster, sync, RGB, and state evolution never freeze or blank because of it. |
| Raster | `h=0..799`, `v=0..524`; active video is `h<640 && v<480`. HSync is low exactly at `h=656..751`; VSync is low exactly at `v=490..491`; `frame_tick` is `(799,524)`. RGB is black throughout blanking. |
| Coordinates | Viewport is physical `h=0..511,v=0..479`, mapping to logical `qx=h[8:1], qy=v[8:1]` (256x240 with 2x downsample). Sidebar is `h=512..639`. |
| Mode 00 | L1 distance: `dx+dy`, 9-bit range 0..510. |
| Mode 01 | L-infinity distance: `max(dx,dy)`, zero-extended to 9 bits. |
| Mode 10 | Octagonal L2 approximation: `max(dx,dy)+floor(min(dx,dy)/2)`, 9-bit range 0..382. |
| Mode 11 | Binary-coordinate Hamming distance: popcount of all 16 bits in `{qx^cx,qy^cy}`, zero-extended to 9 bits. |
| Ties | Argmin compares IDs lexicographically after distance; every tie goes to the lowest prototype ID. |
| Palette | C0 `(R,G,B)=(3,1,0)`, C1 `(0,3,0)`, C2 `(0,2,3)`, C3 `(2,0,3)` using two bits per channel. |
| Crosshair | White `(3,3,3)` for any prototype where `(dy<=1 && dx<=4) || (dx<=1 && dy<=4)`. In active video, sidebar has priority, then crosshair, then region color. |
| Synchronization | All eight `ui_in` bits pass through two flip-flops. Synchronized mode and training requests copy to active state only at frame tick. |
| Step queue | A synchronized Step rising edge captures ID, axis, and direction only if the one-entry pending slot is empty. Later edges are ignored until consumption. Holding Step does not repeat. A command already pending applies at frame tick; a rise recognized on frame tick is queued for the following frame boundary. |
| Manual update | Move the selected X or Y by one logical coordinate. X saturates at 0/255; Y saturates at 0/239. A pending manual command suppresses training at that boundary. |
| LFSR | Right-shifting 16-bit Galois sequence. On every frame, `next=(current>>1) XOR 16'hB400` when the old bit 0 is 1, otherwise `next=current>>1`. Seed is `16'hACE1`; `sample_x=lfsr[7:0]`; `sample_y=lfsr[15:8]`; valid iff `sample_y<240`. It advances every frame, including invalid, training-off, and manual-priority frames. |
| Training | At frame tick, when no manual command is pending and ending-frame training is active and the current sample is valid, the ending mode/current sample/current prototypes choose one winner. For each coordinate, magnitude is `abs(sample-centroid)`, step is `magnitude>>3`, and movement is toward the sample. Differences below 8 do not move. The result is visible coherently from the next frame. |
| Sidebar | Mode rows: `h=528..623`, with `v=32..63,80..111,128..159,176..207`; selected row white `(3,3,3)`, inactive rows gray `(1,1,1)`. Training block: `h=528..623,v=256..303`; active green `(0,3,0)`, inactive red `(1,0,0)`. Palette chips: `v=336..367`, with `h=528..547,553..572,578..597,603..622`, colored C0..C3. Other sidebar pixels are black. |

### Interface

| Pins | Meaning |
|---|---|
| `ui_in[1:0]` | Metric request: `00` L1, `01` L-infinity, `10` octagonal L2 approximation, `11` Hamming |
| `ui_in[2]` | Training request |
| `ui_in[4:3]` | Manual prototype ID |
| `ui_in[5]` | Manual axis: 0 X, 1 Y |
| `ui_in[6]` | Manual direction: 0 decrement, 1 increment |
| `ui_in[7]` | Manual Step transaction strobe |
| `uo_out[0:7]` | `R1,G1,B1,VSync_n,R0,G0,B0,HSync_n` respectively |
| `uio_*` | Unused; output values and enables are tied low |

Selectors should be stable before and briefly after Step. The input synchronizers reduce metastability risk, while Step defines the multi-bit transaction boundary.

## How to test

### Automated verification

From the repository root on Windows:

```powershell
pwsh -File .\scripts\check.ps1
```

The portable equivalent from `test/` is:

```bash
python ../scripts/validate_project.py
make clean
make check
```

That sequence includes metadata/module validation, the independent model tests, lint compilation, and the RTL suite. Verification covers exact 800x525 timing and sync intervals, black blanking, 2x viewport mapping, metric/tie corner cases, model-compared scanlines, frame-latched controls, one-entry Step behavior and actual-RTL saturation, manual priority, the exact LFSR sequence, invalid-Y rejection, and symmetric training updates.

### Physical verification

The following is an acceptance procedure, not evidence of a completed routed check. Physical hardening, precheck, and gate-level claims apply only after the corresponding workflow succeeds for the revision; no routed result is stored in this repository.

1. Supply a stable 25.175 MHz pixel clock and release `rst_n`.
2. Connect `uo_out` through a TinyVGA PMOD or equivalent VGA resistor DAC.
3. Confirm a 640x480 image with four colored regions, white crosshairs, and the geometric sidebar.
4. Select each metric on `ui_in[1:0]`; the highlighted mode row and viewport change together at the next frame boundary.
5. Select a prototype, axis, and direction, then pulse Step. Confirm a one-logical-coordinate (two-screen-pixel) move on the next applicable frame.
6. Enable training and confirm the training block turns green and prototypes evolve slowly. Manual Step commands take priority over training.
7. Toggle `ena` and confirm VGA timing and imagery continue uninterrupted.

## External hardware

Use a Tiny Tapeout demo board, a TinyVGA PMOD (or compatible VGA DAC/interface), a VGA monitor accepting 640x480 timing, a 25.175 MHz clock source, and switches/buttons for `ui_in`. Mechanical Step bounce is not filtered in the baseline design, so use a debounced control when deterministic single-step physical operation is required.
