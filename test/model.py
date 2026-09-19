"""Integer-only reference model for the VGA nearest-prototype tile.

The functions in this module intentionally mirror the frozen hardware widths and
frame-boundary ordering.  They have no Cocotb dependency, so pytest can qualify
the oracle before RTL is available.
"""

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

H_ACTIVE = 640
H_VIEWPORT = 512
H_FRONT = 16
H_SYNC = 96
H_TOTAL = 800
V_ACTIVE = 480
V_FRONT = 10
V_SYNC = 2
V_TOTAL = 525
FRAME_CLOCKS = H_TOTAL * V_TOTAL

MODE_L1 = 0
MODE_LINF = 1
MODE_L2_APPROX = 2
MODE_HAMMING = 3
MODE_NAMES = ("L1", "Linf", "L2 approximation", "Hamming")

INITIAL_CENTROIDS = ((64, 60), (192, 60), (64, 180), (192, 180))
PALETTE = ((3, 1, 0), (0, 3, 0), (0, 2, 3), (2, 0, 3))
WHITE = (3, 3, 3)
DIM = (1, 1, 1)
TRAINING_OFF = (1, 0, 0)
BLACK = (0, 0, 0)

LFSR_SEED = 0xACE1
LFSR_TAP_MASK = 0xB400

RGB_PIN_MASK = 0x77

Centroid = Tuple[int, int]
Color = Tuple[int, int, int]


def _u8(value: int) -> int:
    if not 0 <= value <= 0xFF:
        raise ValueError(f"coordinate {value} does not fit in 8 bits")
    return value


def raster_next(h: int, v: int) -> Tuple[int, int]:
    """Return the counter state after one pixel clock."""
    if not 0 <= h < H_TOTAL or not 0 <= v < V_TOTAL:
        raise ValueError("raster coordinate outside the 800x525 timing domain")
    if h == H_TOTAL - 1:
        return 0, 0 if v == V_TOTAL - 1 else v + 1
    return h + 1, v


def display_on(h: int, v: int) -> bool:
    return 0 <= h < H_ACTIVE and 0 <= v < V_ACTIVE


def viewport_on(h: int, v: int) -> bool:
    return 0 <= h < H_VIEWPORT and 0 <= v < V_ACTIVE


def sidebar_on(h: int, v: int) -> bool:
    return H_VIEWPORT <= h < H_ACTIVE and 0 <= v < V_ACTIVE


def hsync(h: int) -> int:
    return int(not (H_ACTIVE + H_FRONT <= h < H_ACTIVE + H_FRONT + H_SYNC))


def vsync(v: int) -> int:
    return int(not (V_ACTIVE + V_FRONT <= v < V_ACTIVE + V_FRONT + V_SYNC))


def frame_tick(h: int, v: int) -> bool:
    return h == H_TOTAL - 1 and v == V_TOTAL - 1


def logical_coordinate(h: int, v: int) -> Tuple[int, int]:
    if not viewport_on(h, v):
        raise ValueError("physical coordinate is outside the 512x480 viewport")
    return (h >> 1) & 0xFF, (v >> 1) & 0xFF


def deltas(query: Centroid, centroid: Centroid) -> Tuple[int, int]:
    qx, qy = map(_u8, query)
    cx, cy = map(_u8, centroid)
    return abs(qx - cx), abs(qy - cy)


def distance(query: Centroid, centroid: Centroid, mode: int) -> int:
    """Return the zero-extended 9-bit metric result."""
    dx, dy = deltas(query, centroid)
    if mode == MODE_L1:
        result = dx + dy
    elif mode == MODE_LINF:
        result = max(dx, dy)
    elif mode == MODE_L2_APPROX:
        result = max(dx, dy) + (min(dx, dy) >> 1)
    elif mode == MODE_HAMMING:
        result = ((query[0] ^ centroid[0]) & 0xFF).bit_count()
        result += ((query[1] ^ centroid[1]) & 0xFF).bit_count()
    else:
        raise ValueError(f"invalid metric mode {mode}")
    if not 0 <= result <= 0x1FF:
        raise AssertionError("metric result escaped its 9-bit lane")
    return result


def distances(
    query: Centroid,
    centroids: Sequence[Centroid] = INITIAL_CENTROIDS,
    mode: int = MODE_L1,
) -> Tuple[int, ...]:
    if len(centroids) != 4:
        raise ValueError("the design has exactly four centroids")
    return tuple(distance(query, centroid, mode) for centroid in centroids)


def argmin_lowest(values: Sequence[int]) -> int:
    """Return the minimum index; Python's first-min rule is the RTL tie rule."""
    if len(values) != 4:
        raise ValueError("argmin requires exactly four lanes")
    if any(not 0 <= value <= 0x1FF for value in values):
        raise ValueError("distance lane outside 9-bit range")
    return min(range(4), key=lambda index: values[index])


def classify(
    query: Centroid,
    centroids: Sequence[Centroid] = INITIAL_CENTROIDS,
    mode: int = MODE_L1,
) -> int:
    return argmin_lowest(distances(query, centroids, mode))


def is_crosshair(
    query: Centroid,
    centroids: Sequence[Centroid] = INITIAL_CENTROIDS,
) -> bool:
    for centroid in centroids:
        dx, dy = deltas(query, centroid)
        if (dy <= 1 and dx <= 4) or (dx <= 1 and dy <= 4):
            return True
    return False


def viewport_color(
    h: int,
    v: int,
    centroids: Sequence[Centroid] = INITIAL_CENTROIDS,
    mode: int = MODE_L1,
) -> Color:
    query = logical_coordinate(h, v)
    if is_crosshair(query, centroids):
        return WHITE
    return PALETTE[classify(query, centroids, mode)]


def sidebar_color(h: int, v: int, mode_active: int, train_active: bool) -> Color:
    """Return the frozen geometric sidebar color at an active-video point."""
    if not sidebar_on(h, v):
        raise ValueError("physical coordinate is outside the sidebar")
    if not 0 <= mode_active <= 3:
        raise ValueError("active mode must be 0..3")
    if 528 <= h <= 623:
        rows = ((32, 63), (80, 111), (128, 159), (176, 207))
        for row_mode, (first_v, last_v) in enumerate(rows):
            if first_v <= v <= last_v:
                return WHITE if row_mode == mode_active else DIM
        if 256 <= v <= 303:
            return PALETTE[1] if train_active else TRAINING_OFF
        if 336 <= v <= 367:
            chips = ((528, 547), (553, 572), (578, 597), (603, 622))
            for identifier, (first_h, last_h) in enumerate(chips):
                if first_h <= h <= last_h:
                    return PALETTE[identifier]
    return BLACK


def pixel_color(
    h: int,
    v: int,
    centroids: Sequence[Centroid] = INITIAL_CENTROIDS,
    mode: int = MODE_L1,
    training: bool = False,
) -> Color:
    if viewport_on(h, v):
        return viewport_color(h, v, centroids, mode)
    if sidebar_on(h, v):
        return sidebar_color(h, v, mode, training)
    return BLACK


def pack_rgb(color: Color) -> int:
    """Pack 2-bit RGB channels into the TinyVGA dedicated-output pins."""
    red, green, blue = color
    if any(not 0 <= channel <= 3 for channel in color):
        raise ValueError("RGB channels must be 2-bit values")
    return (
        (((red >> 1) & 1) << 0)
        | (((green >> 1) & 1) << 1)
        | (((blue >> 1) & 1) << 2)
        | ((red & 1) << 4)
        | ((green & 1) << 5)
        | ((blue & 1) << 6)
    )


def pack_uo_out(color: Color, hsync_n: int, vsync_n: int) -> int:
    return pack_rgb(color) | ((vsync_n & 1) << 3) | ((hsync_n & 1) << 7)


def lfsr_next(state: int) -> int:
    """Frozen right-shifting 16-bit Galois LFSR transition."""
    if not 0 < state <= 0xFFFF:
        raise ValueError("LFSR state must be a nonzero 16-bit integer")
    shifted = state >> 1
    return (shifted ^ LFSR_TAP_MASK) & 0xFFFF if state & 1 else shifted


def sample_from_lfsr(state: int) -> Tuple[int, int, bool]:
    if not 0 < state <= 0xFFFF:
        raise ValueError("LFSR state must be a nonzero 16-bit integer")
    sample_x = state & 0xFF
    sample_y = (state >> 8) & 0xFF
    return sample_x, sample_y, sample_y < 240


def shifted_coordinate(current: int, sample: int, maximum: int = 255) -> int:
    """Move toward sample by floor(abs(delta)/8), symmetrically."""
    _u8(current)
    _u8(sample)
    step = abs(sample - current) >> 3
    if sample > current:
        return min(maximum, current + step)
    if sample < current:
        return max(0, current - step)
    return current


def train_centroids(
    centroids: Sequence[Centroid], sample: Centroid, mode: int
) -> Tuple[Tuple[Centroid, ...], int]:
    if len(centroids) != 4:
        raise ValueError("training requires exactly four centroids")
    winner = classify(sample, centroids, mode)
    updated = list(centroids)
    cx, cy = centroids[winner]
    sx, sy = sample
    updated[winner] = (
        shifted_coordinate(cx, sx, 255),
        shifted_coordinate(cy, sy, 239),
    )
    return tuple(updated), winner


@dataclass(frozen=True)
class ManualCommand:
    centroid: int
    axis_y: bool
    increment: bool

    def __post_init__(self) -> None:
        if not 0 <= self.centroid <= 3:
            raise ValueError("manual centroid selector must be 0..3")


def apply_manual(
    centroids: Sequence[Centroid], command: ManualCommand
) -> Tuple[Centroid, ...]:
    if len(centroids) != 4:
        raise ValueError("manual update requires exactly four centroids")
    updated = list(centroids)
    x, y = updated[command.centroid]
    if command.axis_y:
        y = min(239, y + 1) if command.increment else max(0, y - 1)
    else:
        x = min(255, x + 1) if command.increment else max(0, x - 1)
    updated[command.centroid] = (x, y)
    return tuple(updated)


@dataclass(frozen=True)
class MachineState:
    centroids: Tuple[Centroid, ...] = INITIAL_CENTROIDS
    mode_active: int = MODE_L1
    train_active: bool = False
    lfsr: int = LFSR_SEED

    def __post_init__(self) -> None:
        if len(self.centroids) != 4:
            raise ValueError("machine state requires four centroids")
        if not 0 <= self.mode_active <= 3:
            raise ValueError("active mode must be 0..3")
        if not 0 < self.lfsr <= 0xFFFF:
            raise ValueError("LFSR must remain nonzero")
        for x, y in self.centroids:
            if not 0 <= x <= 255 or not 0 <= y <= 239:
                raise ValueError("centroid outside logical viewport")


@dataclass(frozen=True)
class BoundaryResult:
    state: MachineState
    sample: Centroid
    sample_valid: bool
    winner: Optional[int]
    manual_applied: bool
    training_applied: bool


def boundary_transition(
    state: MachineState,
    requested_mode: int,
    requested_training: bool,
    pending: Optional[ManualCommand] = None,
) -> BoundaryResult:
    """Apply one frame boundary in the frozen update order.

    Training observes the ending frame's active mode/training state and old LFSR
    sample.  Requested controls become active for the next frame.  A pending
    manual command suppresses training, and the LFSR always advances.
    """
    if not 0 <= requested_mode <= 3:
        raise ValueError("requested mode must be 0..3")
    sample_x, sample_y, valid = sample_from_lfsr(state.lfsr)
    sample = (sample_x, sample_y)
    centroids = state.centroids
    winner: Optional[int] = None
    manual_applied = pending is not None
    training_applied = False

    if pending is not None:
        centroids = apply_manual(centroids, pending)
    elif state.train_active and valid:
        centroids, winner = train_centroids(centroids, sample, state.mode_active)
        training_applied = True

    next_state = MachineState(
        centroids=tuple(centroids),
        mode_active=requested_mode,
        train_active=bool(requested_training),
        lfsr=lfsr_next(state.lfsr),
    )
    return BoundaryResult(
        state=next_state,
        sample=sample,
        sample_valid=valid,
        winner=winner,
        manual_applied=manual_applied,
        training_applied=training_applied,
    )


@dataclass(frozen=True)
class InputControlState:
    """Two-flop UI synchronizer, Step edge history, and one-entry queue."""

    sync1: int = 0
    sync2: int = 0
    step_previous: bool = False
    pending: Optional[ManualCommand] = None


def synchronize_inputs(state: InputControlState, raw_ui: int) -> InputControlState:
    """Model one rising edge using nonblocking-assignment/old-state semantics."""
    if not 0 <= raw_ui <= 0xFF:
        raise ValueError("ui_in must be an 8-bit value")
    old_sync2 = state.sync2
    step = bool(old_sync2 & 0x80)
    pending = state.pending
    if step and not state.step_previous and pending is None:
        pending = ManualCommand(
            centroid=(old_sync2 >> 3) & 0x3,
            axis_y=bool(old_sync2 & 0x20),
            increment=bool(old_sync2 & 0x40),
        )
    return InputControlState(
        sync1=raw_ui,
        sync2=state.sync1,
        step_previous=step,
        pending=pending,
    )


def consume_pending(state: InputControlState) -> InputControlState:
    return InputControlState(
        sync1=state.sync1,
        sync2=state.sync2,
        step_previous=state.step_previous,
        pending=None,
    )


def iter_frame() -> Iterable[Tuple[int, int]]:
    for vertical in range(V_TOTAL):
        for horizontal in range(H_TOTAL):
            yield horizontal, vertical
