"""Targeted Cocotb verification for the VGA nearest-prototype tile.

Gate-level execution is explicitly port-only: hierarchy-dependent tests are
reported as skipped, while reset and one complete 420,000-clock frame run from
pins.  Three additional boundary-aligned frames cover every mode plus real
manual and training updates without force or behavioral-only signals.
"""

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge, Timer

from model import (
    BLACK,
    FRAME_CLOCKS,
    H_ACTIVE,
    H_TOTAL,
    INITIAL_CENTROIDS,
    LFSR_SEED,
    RGB_PIN_MASK,
    V_ACTIVE,
    MachineState,
    ManualCommand,
    apply_manual,
    boundary_transition,
    classify,
    distance,
    frame_tick,
    hsync,
    logical_coordinate,
    pack_rgb,
    pixel_color,
    sample_from_lfsr,
    vsync,
)

GATE_LEVEL = os.getenv("TEST_LEVEL", "rtl").lower() == "gate"
CLOCK_NS = 100 if GATE_LEVEL else 10
GATE_SETTLE_NS = 20
SELECTED_SCANLINES = (40, 88, 136, 184)
BOUNDARY_H = (511, 512, 527, 528, 623, 624, 639, 640)


def _project(dut):
    return dut.user_project


def _find_handle(parent, *names):
    for name in names:
        try:
            return getattr(parent, name)
        except AttributeError:
            pass
    return None


def _state_handle(dut, *names):
    return _find_handle(_project(dut), *names)


def _required_state(dut, name):
    signal = _state_handle(dut, name)
    assert signal is not None, f"RTL signal {name} is required by this RTL-only test"
    return signal


def _integer(signal, description):
    try:
        return int(signal.value)
    except (TypeError, ValueError) as exc:
        raise AssertionError(f"{description} contains X/Z: {signal.value}") from exc


async def _settle_after_edge():
    if GATE_LEVEL:
        await Timer(GATE_SETTLE_NS, unit="ns")
    else:
        await ReadOnly()


async def _wait_cycles(dut, count):
    if count < 0:
        raise ValueError("negative cycle wait")
    if count:
        await ClockCycles(dut.clk, count, rising=True)
        await _settle_after_edge()


async def _start_and_reset(dut, ena=1):
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.ena.value = ena
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    clock = Clock(dut.clk, CLOCK_NS, unit="ns", impl="gpi")
    cocotb.start_soon(clock.start())

    # Long enough for routed reset paths too; reset assertion itself is async.
    await Timer(5 * CLOCK_NS, unit="ns")
    assert _integer(dut.uio_out, "uio_out") == 0
    assert _integer(dut.uio_oe, "uio_oe") == 0
    assert _integer(dut.uo_out, "uo_out") & 0x88 == 0x88

    if not GATE_LEVEL:
        assert _integer(_required_state(dut, "h_count"), "h_count") == 0
        assert _integer(_required_state(dut, "v_count"), "v_count") == 0

    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    return clock


def _read_centroids(dut, required=False):
    project = _project(dut)
    result = []
    for index in range(4):
        x = _find_handle(project, f"c{index}_x")
        y = _find_handle(project, f"c{index}_y")
        if x is None or y is None:
            if required:
                raise AssertionError(f"RTL centroid c{index}_x/c{index}_y is required")
            return None
        result.append((_integer(x, f"centroid {index} X"), _integer(y, f"centroid {index} Y")))
    return tuple(result)


def _read_distances(dut):
    result = []
    for index in range(4):
        signal = _state_handle(dut, f"distance{index}")
        if signal is None:
            return None
        result.append(_integer(signal, f"distance lane {index}"))
    return tuple(result)


def _read_winner(dut):
    signal = _state_handle(dut, "winner_id")
    return None if signal is None else _integer(signal, "winner ID")


def _assert_frozen_reset_state(dut):
    expected_scalars = (
        ("h_count", 0),
        ("v_count", 0),
        ("mode_active", 0),
        ("train_active", 0),
        ("manual_pending", 0),
        ("lfsr", LFSR_SEED),
        ("ui_meta", 0),
        ("ui_sync", 0),
        ("step_sync_d", 0),
    )
    for name, expected in expected_scalars:
        assert _integer(_required_state(dut, name), name) == expected
    assert _read_centroids(dut, required=True) == INITIAL_CENTROIDS


def _write_centroids(dut, centroids):
    for index, (x, y) in enumerate(centroids):
        _required_state(dut, f"c{index}_x").value = x
        _required_state(dut, f"c{index}_y").value = y


def _assert_port_pixel(dut, h, v, centroids=INITIAL_CENTROIDS, mode=0, training=False):
    output = _integer(dut.uo_out, "uo_out")
    assert ((output >> 7) & 1) == hsync(h), f"HSync mismatch at ({h},{v})"
    assert ((output >> 3) & 1) == vsync(v), f"VSync mismatch at ({h},{v})"
    expected = pack_rgb(pixel_color(h, v, centroids, mode, training))
    assert output & RGB_PIN_MASK == expected, f"RGB mismatch at ({h},{v}) in mode {mode}"


async def _check_scanline_from_ports(dut, v, centroids, mode, training):
    """Compare one complete current scanline using only dedicated output pins."""
    for h in range(H_TOTAL):
        _assert_port_pixel(dut, h, v, centroids, mode, training)
        if h != H_TOTAL - 1:
            await RisingEdge(dut.clk)
            await _settle_after_edge()


async def _advance_to_index(dut, current_index, target_index):
    if not current_index <= target_index < FRAME_CLOCKS:
        raise ValueError("target must be later in the same frame")
    await _wait_cycles(dut, target_index - current_index)
    return target_index


async def _advance_to_next_frame(dut, current_index):
    await _wait_cycles(dut, FRAME_CLOCKS - current_index)
    return 0


async def _gate_port_modes_manual_and_training(dut):
    """Finish compact gate coverage after the exhaustive reset-mode frame.

    Frame 1 shows mode 1 and captures a synchronized manual C0/X increment.
    Frame 2 shows mode 2 plus that update.  Its ending boundary performs an
    accepted training update, which frame 3 exposes while showing mode 3.
    """
    state = boundary_transition(MachineState(), 1, True).state

    current_index = SELECTED_SCANLINES[1] * H_TOTAL
    await _wait_cycles(dut, current_index)
    await _check_scanline_from_ports(dut, SELECTED_SCANLINES[1], state.centroids, 1, True)
    current_index += H_TOTAL - 1

    # Queue C0/X/increment through the real two-flop synchronizer while also
    # requesting mode 2.  Release Step but retain mode/training before boundary.
    await FallingEdge(dut.clk)
    dut.ui_in.value = 0x80 | 0x40 | (1 << 2) | 2
    await _wait_cycles(dut, 3)
    current_index += 3
    await FallingEdge(dut.clk)
    dut.ui_in.value = (1 << 2) | 2
    current_index = await _advance_to_next_frame(dut, current_index)

    command = ManualCommand(0, axis_y=False, increment=True)
    state = boundary_transition(state, 2, True, command).state
    assert state.centroids == apply_manual(INITIAL_CENTROIDS, command)

    # Request mode 3 early.  A pixel newly covered by the shifted C0 crosshair
    # proves the manual update through ports before the selected mode-2 line.
    await FallingEdge(dut.clk)
    dut.ui_in.value = (1 << 2) | 3
    manual_point = 120 * H_TOTAL + 138
    current_index = await _advance_to_index(dut, current_index, manual_point)
    _assert_port_pixel(dut, 138, 120, state.centroids, 2, True)
    line_start = SELECTED_SCANLINES[2] * H_TOTAL
    current_index = await _advance_to_index(dut, current_index, line_start)
    await _check_scanline_from_ports(dut, SELECTED_SCANLINES[2], state.centroids, 2, True)
    current_index += H_TOTAL - 1
    current_index = await _advance_to_next_frame(dut, current_index)

    result = boundary_transition(state, 3, True)
    assert result.training_applied and result.winner == 0
    state = result.state

    # The new C0 center is visible only after the accepted mode-2 training
    # boundary; then a full selected mode-3 line closes all-mode coverage.
    trained_point = 132 * H_TOTAL + 128
    current_index = await _advance_to_index(dut, current_index, trained_point)
    _assert_port_pixel(dut, 128, 132, state.centroids, 3, True)
    line_start = SELECTED_SCANLINES[3] * H_TOTAL
    current_index = await _advance_to_index(dut, current_index, line_start)
    await _check_scanline_from_ports(dut, SELECTED_SCANLINES[3], state.centroids, 3, True)


@cocotb.test()
async def test_async_reset_tieoffs_and_ena_policy(dut):
    """Check asynchronous reset, safe bidirectional pins, and ignored ena."""
    await _start_and_reset(dut, ena=0)

    await RisingEdge(dut.clk)
    await _settle_after_edge()
    h_count = None if GATE_LEVEL else _required_state(dut, "h_count")
    if h_count is not None:
        assert _integer(h_count, "h_count") == 1, "ena=0 must not freeze VGA timing"

    await FallingEdge(dut.clk)
    dut.ena.value = 1
    await RisingEdge(dut.clk)
    await _settle_after_edge()
    if h_count is not None:
        assert _integer(h_count, "h_count") == 2

    await Timer(CLOCK_NS // 3, unit="ns")
    dut.rst_n.value = 0
    await Timer(GATE_SETTLE_NS if GATE_LEVEL else 1, unit="ns")
    assert _integer(dut.uio_out, "uio_out") == 0
    assert _integer(dut.uio_oe, "uio_oe") == 0
    if not GATE_LEVEL:
        _assert_frozen_reset_state(dut)

    if not GATE_LEVEL:
        # Repeat asynchronous assertion at horizontal porch, HSync, and VSync.
        v_count = _required_state(dut, "v_count")
        for target, label in ((640, "front porch"), (656, "HSync"), (490 * H_TOTAL, "VSync")):
            await FallingEdge(dut.clk)
            dut.rst_n.value = 1
            await _wait_cycles(dut, target)
            assert (_integer(h_count, "h_count"), _integer(v_count, "v_count")) == (
                target % H_TOTAL,
                target // H_TOTAL,
            ), f"failed to reach {label} reset point"
            await Timer(CLOCK_NS // 3, unit="ns")
            dut.rst_n.value = 0
            await Timer(1, unit="ns")
            _assert_frozen_reset_state(dut)


@cocotb.test(skip=GATE_LEVEL)
async def test_distance_lane_extrema_random_vectors_and_argmin_ties(dut):
    """Drive the RTL-only probe lane and construct deterministic top ties."""
    await _start_and_reset(dut)

    rng = random.Random(0xB400)
    vectors = [
        (255, 255, 0, 0),
        (200, 100, 0, 0),
        (255, 0, 0, 255),
        (0xAA, 0x0F, 0x55, 0xF0),
    ]
    vectors.extend(tuple(rng.randrange(256) for _ in range(4)) for _ in range(256))
    for qx, qy, cx, cy in vectors:
        for mode in range(4):
            dut.probe_qx.value = qx
            dut.probe_qy.value = qy
            dut.probe_cx.value = cx
            dut.probe_cy.value = cy
            dut.probe_mode.value = mode
            await Timer(1, unit="ns")
            assert _integer(dut.probe_distance, "metric probe") == distance((qx, qy), (cx, cy), mode)

    h_count = _required_state(dut, "h_count")
    v_count = _required_state(dut, "v_count")
    mode_active = _required_state(dut, "mode_active")
    winner = _required_state(dut, "winner_id")
    tie_layouts = (
        (((1, 0), (1, 0), (10, 0), (10, 0)), 0),
        (((10, 0), (10, 0), (1, 0), (1, 0)), 2),
        (((1, 0), (10, 0), (1, 0), (10, 0)), 0),
        (((1, 0), (1, 0), (1, 0), (1, 0)), 0),
    )
    for mode in range(4):
        for centroids, expected_winner in tie_layouts:
            h_count.value = 0
            v_count.value = 0
            mode_active.value = mode
            _write_centroids(dut, centroids)
            await Timer(1, unit="ns")
            assert _integer(winner, "winner ID") == expected_winner


@cocotb.test()
async def test_complete_800x525_frame_from_ports(dut):
    """Prove one exact frame; gate mode then covers controls in three more."""
    await _start_and_reset(dut, ena=0)
    h_count = None if GATE_LEVEL else _required_state(dut, "h_count")
    v_count = None if GATE_LEVEL else _required_state(dut, "v_count")
    tick = None if GATE_LEVEL else _required_state(dut, "frame_tick")

    # The request is synchronized during frame 0 but cannot affect that frame.
    # At its ending boundary gate mode enters mode 1 with training enabled.
    if GATE_LEVEL:
        dut.ui_in.value = (1 << 2) | 1

    hsync_low_count = 0
    vsync_low_count = 0
    tick_count = 0
    visible_count = 0
    viewport_count = 0
    sidebar_count = 0
    boundary_points = {(h, v) for h in BOUNDARY_H for v in (479, 480)}
    crosshair_points = set()
    for centroid_x, centroid_y in INITIAL_CENTROIDS:
        crosshair_points.update(
            {
                (2 * centroid_x, 2 * centroid_y),
                (2 * (centroid_x + 4), 2 * (centroid_y + 1)),
                (2 * (centroid_x + 1), 2 * (centroid_y + 4)),
                (2 * (centroid_x + 5), 2 * (centroid_y + 1)),
            }
        )

    # Reset state is (0,0); cycle N samples the state after N increments.
    for cycle in range(1, FRAME_CLOCKS + 1):
        await RisingEdge(dut.clk)
        await _settle_after_edge()
        h = cycle % H_TOTAL
        v = (cycle // H_TOTAL) % 525
        output = _integer(dut.uo_out, "uo_out")

        assert ((output >> 7) & 1) == hsync(h), f"HSync mismatch at ({h},{v})"
        assert ((output >> 3) & 1) == vsync(v), f"VSync mismatch at ({h},{v})"
        hsync_low_count += ((output >> 7) & 1) == 0
        vsync_low_count += ((output >> 3) & 1) == 0

        in_display = h < H_ACTIVE and v < V_ACTIVE
        visible_count += in_display
        viewport_count += h < 512 and v < V_ACTIVE
        sidebar_count += 512 <= h < H_ACTIVE and v < V_ACTIVE
        if not in_display:
            assert output & RGB_PIN_MASK == 0, f"non-black blanking at ({h},{v})"

        # A full mode-0 scanline plus explicit geometry boundaries and sparse
        # center/arm/outside probes for every replicated reset crosshair are
        # checked directly at the output pins.
        if (
            v == SELECTED_SCANLINES[0]
            or (h, v) in boundary_points
            or (h, v) in crosshair_points
        ):
            _assert_port_pixel(dut, h, v, INITIAL_CENTROIDS, 0, False)

        if h_count is not None:
            assert _integer(h_count, "h_count") == h
            assert _integer(v_count, "v_count") == v
            expected_tick = frame_tick(h, v)
            assert bool(_integer(tick, "frame_tick")) is expected_tick
            tick_count += expected_tick

    assert hsync_low_count == 96 * 525
    assert vsync_low_count == 2 * 800
    assert visible_count == 640 * 480
    assert viewport_count == 512 * 480
    assert sidebar_count == 128 * 480
    if tick is not None:
        assert tick_count == 1
        assert (_integer(h_count, "h_count"), _integer(v_count, "v_count")) == (0, 0)

    if GATE_LEVEL:
        await _gate_port_modes_manual_and_training(dut)


@cocotb.test(skip=GATE_LEVEL)
async def test_all_metric_modes_render_and_latch_per_frame(dut):
    """Compare a complete selected RTL scanline in every frame-latched mode."""
    await _start_and_reset(dut)
    current_index = 0
    mode_active = _required_state(dut, "mode_active")

    for mode, scanline in enumerate(SELECTED_SCANLINES):
        assert _integer(mode_active, "mode_active") == mode
        target = scanline * H_TOTAL
        current_index = await _advance_to_index(dut, current_index, target)
        await _check_scanline_from_ports(dut, scanline, INITIAL_CENTROIDS, mode, False)
        current_index += H_TOTAL - 1

        if mode == 3:
            break
        await FallingEdge(dut.clk)
        dut.ui_in.value = mode + 1
        await _wait_cycles(dut, 3)
        current_index += 3
        assert _integer(mode_active, "mode_active") == mode
        current_index = await _advance_to_next_frame(dut, current_index)
        assert _integer(mode_active, "mode_active") == mode + 1


@cocotb.test(skip=GATE_LEVEL)
async def test_manual_pending_payload_one_shot_and_boundary_application(dut):
    """Verify capture, manual-over-training priority, saturation, and no repeat."""
    await _start_and_reset(dut)
    assert _read_centroids(dut, required=True) == INITIAL_CENTROIDS
    pending = _required_state(dut, "manual_pending")
    train_active = _required_state(dut, "train_active")

    dut.ui_in.value = 1 << 2
    current_index = await _advance_to_next_frame(dut, 0)
    assert _integer(train_active, "train_active") == 1
    assert _read_centroids(dut, required=True) == INITIAL_CENTROIDS

    await FallingEdge(dut.clk)
    dut.ui_in.value = (1 << 2) | 0x80 | 0x40
    await _wait_cycles(dut, 3)
    current_index += 3
    assert _integer(pending, "manual pending") == 1
    await FallingEdge(dut.clk)
    dut.ui_in.value = 0x80 | (3 << 3) | 0x20
    current_index = await _advance_to_next_frame(dut, current_index)
    expected = list(INITIAL_CENTROIDS)
    expected[0] = (65, 60)
    assert _read_centroids(dut, required=True) == tuple(expected)
    assert _integer(pending, "manual pending") == 0
    assert _integer(train_active, "train_active") == 0

    current_index = await _advance_to_next_frame(dut, current_index)
    assert _read_centroids(dut, required=True) == tuple(expected)

    await FallingEdge(dut.clk)
    dut.ui_in.value = 0
    await _wait_cycles(dut, 3)
    current_index += 3
    await FallingEdge(dut.clk)
    _required_state(dut, "c3_y").value = 0
    expected[3] = (192, 0)
    dut.ui_in.value = 0x80 | (3 << 3) | 0x20
    await _wait_cycles(dut, 3)
    current_index += 3
    await _advance_to_next_frame(dut, current_index)
    assert _read_centroids(dut, required=True) == tuple(expected)

    await Timer(CLOCK_NS // 3, unit="ns")
    dut.rst_n.value = 0
    await Timer(1, unit="ns")
    _assert_frozen_reset_state(dut)


@cocotb.test(skip=GATE_LEVEL)
async def test_lfsr_and_training_follow_boundary_model(dut):
    """Check old-frame training semantics, LFSR advance, and winner-only update."""
    await _start_and_reset(dut)
    lfsr = _required_state(dut, "lfsr")
    assert _read_centroids(dut, required=True) == INITIAL_CENTROIDS
    assert _integer(lfsr, "LFSR") == LFSR_SEED

    dut.ui_in.value = 1 << 2
    model_state = MachineState()
    current_index = await _advance_to_next_frame(dut, 0)
    model_state = boundary_transition(model_state, 0, True).state
    assert _integer(lfsr, "LFSR") == model_state.lfsr
    assert _read_centroids(dut, required=True) == model_state.centroids

    for _ in range(2):
        old_centroids = model_state.centroids
        current_index = await _advance_to_next_frame(dut, current_index)
        result = boundary_transition(model_state, 0, True)
        model_state = result.state
        assert result.sample_valid
        assert _integer(lfsr, "LFSR") == model_state.lfsr
        observed = _read_centroids(dut, required=True)
        assert observed == model_state.centroids
        assert sum(a != b for a, b in zip(old_centroids, observed)) <= 1

    for seeded_lfsr, expected_valid in ((0xEFE1, True), (0xF001, False), (0xFF01, False)):
        await FallingEdge(dut.clk)
        lfsr.value = seeded_lfsr
        model_state = MachineState(model_state.centroids, 0, True, seeded_lfsr)
        old_centroids = model_state.centroids
        current_index = await _advance_to_next_frame(dut, current_index)
        result = boundary_transition(model_state, 0, True)
        model_state = result.state
        assert result.sample_valid is expected_valid
        assert _integer(lfsr, "LFSR") == model_state.lfsr
        assert _read_centroids(dut, required=True) == model_state.centroids
        if not expected_valid:
            assert model_state.centroids == old_centroids

    assert sample_from_lfsr(LFSR_SEED) == (0xE1, 0xAC, True)


@cocotb.test(skip=GATE_LEVEL)
async def test_accelerated_boundary_transition_trace(dut):
    """Compare 5,000 actual sequential frame edges with the frozen model."""
    await _start_and_reset(dut)
    h_count = _required_state(dut, "h_count")
    v_count = _required_state(dut, "v_count")
    mode_active = _required_state(dut, "mode_active")
    train_active = _required_state(dut, "train_active")
    lfsr = _required_state(dut, "lfsr")
    ui_sync = _required_state(dut, "ui_sync")
    step_sync_d = _required_state(dut, "step_sync_d")
    manual_pending = _required_state(dut, "manual_pending")
    manual_id = _required_state(dut, "manual_id")
    manual_axis = _required_state(dut, "manual_axis")
    manual_direction = _required_state(dut, "manual_direction")
    tick = _required_state(dut, "frame_tick")

    state = MachineState()
    accepted = rejected = disabled = manual = priority = different_winner = 0

    for transition in range(5_000):
        requested_mode = (transition + 1) & 3
        requested_training = transition % 7 not in (0, 1)
        command = None
        if transition % 97 == 13:
            command = ManualCommand(
                centroid=(transition // 97) & 3,
                axis_y=bool(transition & 1),
                increment=bool(transition & 2),
            )

        await FallingEdge(dut.clk)
        h_count.value = 799
        v_count.value = 524
        mode_active.value = state.mode_active
        train_active.value = int(state.train_active)
        lfsr.value = state.lfsr
        _write_centroids(dut, state.centroids)
        ui_sync.value = requested_mode | (int(requested_training) << 2)
        step_sync_d.value = 0
        manual_pending.value = int(command is not None)
        manual_id.value = 0 if command is None else command.centroid
        manual_axis.value = 0 if command is None else int(command.axis_y)
        manual_direction.value = 0 if command is None else int(command.increment)
        await Timer(1, unit="ns")
        assert _integer(tick, "frame_tick") == 1

        sample_x, sample_y, valid = sample_from_lfsr(state.lfsr)
        if state.train_active and valid and command is None:
            old_winner = classify((sample_x, sample_y), state.centroids, state.mode_active)
            new_winner = classify((sample_x, sample_y), state.centroids, requested_mode)
            different_winner += old_winner != new_winner

        old = state
        result = boundary_transition(state, requested_mode, requested_training, command)
        state = result.state
        await RisingEdge(dut.clk)
        await _settle_after_edge()

        assert (_integer(h_count, "h_count"), _integer(v_count, "v_count")) == (0, 0)
        assert _integer(tick, "frame_tick") == 0
        assert _integer(mode_active, "mode_active") == state.mode_active
        assert bool(_integer(train_active, "train_active")) is state.train_active
        assert _integer(lfsr, "lfsr") == state.lfsr
        assert _read_centroids(dut, required=True) == state.centroids
        assert sum(a != b for a, b in zip(old.centroids, state.centroids)) <= 1
        assert state.lfsr != 0 and state.lfsr != old.lfsr
        assert all(0 <= x <= 255 and 0 <= y <= 239 for x, y in state.centroids)

        manual += result.manual_applied
        accepted += result.training_applied
        rejected += old.train_active and not result.sample_valid and command is None
        disabled += not old.train_active and command is None
        priority += command is not None and old.train_active and result.sample_valid
        if command is not None:
            assert result.manual_applied and not result.training_applied
        elif result.training_applied:
            assert old.train_active and result.sample_valid

    assert accepted > 1_000
    assert rejected > 100
    assert disabled > 500
    assert manual > 40
    assert priority > 10
    assert different_winner > 100


@cocotb.test(skip=GATE_LEVEL)
async def test_actual_rtl_manual_saturation_all_centroids_axes_bounds(dut):
    """Hit lower/decrement and upper/increment saturation in every RTL lane."""
    await _start_and_reset(dut)
    h_count = _required_state(dut, "h_count")
    v_count = _required_state(dut, "v_count")
    manual_pending = _required_state(dut, "manual_pending")
    manual_id = _required_state(dut, "manual_id")
    manual_axis = _required_state(dut, "manual_axis")
    manual_direction = _required_state(dut, "manual_direction")
    train_active = _required_state(dut, "train_active")
    ui_sync = _required_state(dut, "ui_sync")
    tick = _required_state(dut, "frame_tick")

    cases = 0
    for centroid_id in range(4):
        for axis_y, maximum in ((False, 255), (True, 239)):
            for bound, increment in ((0, False), (maximum, True)):
                centroids = [(31 + index, 47 + index) for index in range(4)]
                x, y = centroids[centroid_id]
                centroids[centroid_id] = (x, bound) if axis_y else (bound, y)
                expected = tuple(centroids)

                await FallingEdge(dut.clk)
                h_count.value = 799
                v_count.value = 524
                _write_centroids(dut, expected)
                train_active.value = 1
                ui_sync.value = 0
                manual_pending.value = 1
                manual_id.value = centroid_id
                manual_axis.value = int(axis_y)
                manual_direction.value = int(increment)
                await Timer(1, unit="ns")
                assert _integer(tick, "frame_tick") == 1
                await RisingEdge(dut.clk)
                await _settle_after_edge()

                assert _read_centroids(dut, required=True) == expected
                assert _integer(manual_pending, "manual_pending") == 0
                assert (_integer(h_count, "h_count"), _integer(v_count, "v_count")) == (0, 0)
                cases += 1

    assert cases == 4 * 2 * 2
