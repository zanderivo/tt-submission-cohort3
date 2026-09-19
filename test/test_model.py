"""Pure pytest qualification for the integer VGA reference model."""

import random

import pytest

from model import (
    BLACK,
    FRAME_CLOCKS,
    H_ACTIVE,
    H_TOTAL,
    H_VIEWPORT,
    INITIAL_CENTROIDS,
    LFSR_SEED,
    MODE_HAMMING,
    MODE_L1,
    MODE_L2_APPROX,
    MODE_LINF,
    PALETTE,
    RGB_PIN_MASK,
    V_ACTIVE,
    V_TOTAL,
    WHITE,
    InputControlState,
    MachineState,
    ManualCommand,
    apply_manual,
    argmin_lowest,
    boundary_transition,
    classify,
    consume_pending,
    display_on,
    distance,
    frame_tick,
    hsync,
    is_crosshair,
    iter_frame,
    lfsr_next,
    logical_coordinate,
    pack_rgb,
    pack_uo_out,
    pixel_color,
    raster_next,
    sample_from_lfsr,
    shifted_coordinate,
    sidebar_color,
    sidebar_on,
    synchronize_inputs,
    train_centroids,
    viewport_color,
    viewport_on,
    vsync,
)


@pytest.mark.parametrize(
    "mode,query,centroid,expected",
    [
        (MODE_L1, (0, 0), (0, 0), 0),
        (MODE_L1, (255, 255), (0, 0), 510),
        (MODE_L1, (200, 100), (0, 0), 300),
        (MODE_L1, (1, 0), (0, 0), 1),
        (MODE_LINF, (3, 9), (0, 0), 9),
        (MODE_LINF, (9, 3), (0, 0), 9),
        (MODE_LINF, (9, 9), (0, 0), 9),
        (MODE_L2_APPROX, (255, 255), (0, 0), 382),
        (MODE_L2_APPROX, (20, 7), (0, 0), 23),
        (MODE_L2_APPROX, (20, 8), (0, 0), 24),
        (MODE_HAMMING, (0x00, 0x00), (0x00, 0x00), 0),
        (MODE_HAMMING, (0xFF, 0xFF), (0x00, 0x00), 16),
        (MODE_HAMMING, (0xAA, 0x0F), (0x55, 0xF0), 16),
        (MODE_HAMMING, (0x80, 0x00), (0x00, 0x00), 1),
    ],
)
def test_metric_directed_vectors(mode, query, centroid, expected):
    assert distance(query, centroid, mode) == expected


def test_metrics_match_independent_integer_formulas_randomly():
    rng = random.Random(0xACE1)
    for _ in range(4_000):
        query = (rng.randrange(256), rng.randrange(256))
        centroid = (rng.randrange(256), rng.randrange(256))
        dx = abs(query[0] - centroid[0])
        dy = abs(query[1] - centroid[1])
        expected = (
            dx + dy,
            max(dx, dy),
            max(dx, dy) + min(dx, dy) // 2,
            bin(query[0] ^ centroid[0]).count("1")
            + bin(query[1] ^ centroid[1]).count("1"),
        )
        for mode in range(4):
            assert distance(query, centroid, mode) == expected[mode]


@pytest.mark.parametrize(
    "values,winner",
    [
        ((0, 1, 2, 3), 0),
        ((3, 0, 2, 1), 1),
        ((3, 2, 0, 1), 2),
        ((3, 2, 1, 0), 3),
        ((7, 7, 9, 10), 0),
        ((9, 10, 7, 7), 2),
        ((7, 9, 7, 9), 0),
        ((9, 7, 9, 7), 1),
        ((5, 5, 5, 5), 0),
    ],
)
def test_argmin_strict_and_tie_cases(values, winner):
    assert argmin_lowest(values) == winner


def test_tie_rule_is_metric_independent():
    duplicated = ((20, 30), (20, 30), (200, 100), (200, 100))
    for mode in range(4):
        assert classify((20, 30), duplicated, mode) == 0


def test_raster_transitions_and_exact_frame_counts():
    h = v = 0
    counts = {
        "display": 0,
        "viewport": 0,
        "sidebar": 0,
        "hsync_low": 0,
        "vsync_low": 0,
        "frame_tick": 0,
    }
    for expected_h, expected_v in iter_frame():
        assert (h, v) == (expected_h, expected_v)
        counts["display"] += display_on(h, v)
        counts["viewport"] += viewport_on(h, v)
        counts["sidebar"] += sidebar_on(h, v)
        counts["hsync_low"] += not hsync(h)
        counts["vsync_low"] += not vsync(v)
        counts["frame_tick"] += frame_tick(h, v)
        h, v = raster_next(h, v)

    assert (h, v) == (0, 0)
    assert FRAME_CLOCKS == 420_000
    assert counts == {
        "display": 640 * 480,
        "viewport": 512 * 480,
        "sidebar": 128 * 480,
        "hsync_low": 96 * 525,
        "vsync_low": 2 * 800,
        "frame_tick": 1,
    }


@pytest.mark.parametrize(
    "physical,logical",
    [
        ((0, 0), (0, 0)),
        ((1, 1), (0, 0)),
        ((2, 2), (1, 1)),
        ((510, 478), (255, 239)),
        ((511, 479), (255, 239)),
    ],
)
def test_viewport_downsample(physical, logical):
    assert logical_coordinate(*physical) == logical


def test_viewport_mapping_rejects_sidebar_and_blanking():
    for coordinate in ((512, 0), (639, 479), (0, 480), (799, 524)):
        with pytest.raises(ValueError):
            logical_coordinate(*coordinate)


def test_sync_boundaries_are_exact_and_active_low():
    assert hsync(655) == 1
    assert hsync(656) == 0
    assert hsync(751) == 0
    assert hsync(752) == 1
    assert vsync(489) == 1
    assert vsync(490) == 0
    assert vsync(491) == 0
    assert vsync(492) == 1


def test_palette_and_tinyvga_pin_order():
    assert PALETTE == ((3, 1, 0), (0, 3, 0), (0, 2, 3), (2, 0, 3))
    assert pack_rgb((2, 0, 0)) == 0x01  # R1 -> uo_out[0]
    assert pack_rgb((1, 0, 0)) == 0x10  # R0 -> uo_out[4]
    assert pack_rgb((0, 2, 0)) == 0x02
    assert pack_rgb((0, 1, 0)) == 0x20
    assert pack_rgb((0, 0, 2)) == 0x04
    assert pack_rgb((0, 0, 1)) == 0x40
    assert pack_uo_out(BLACK, 1, 1) == 0x88
    assert pack_rgb(WHITE) == RGB_PIN_MASK


def test_crosshair_geometry_override_and_physical_2x2_mapping():
    centroid = INITIAL_CENTROIDS[0]
    assert is_crosshair(centroid)
    assert is_crosshair((centroid[0] + 4, centroid[1] + 1))
    assert is_crosshair((centroid[0] + 1, centroid[1] + 4))
    assert not is_crosshair((centroid[0] + 5, centroid[1] + 1))
    assert not is_crosshair((centroid[0] + 2, centroid[1] + 2))
    for h in (2 * centroid[0], 2 * centroid[0] + 1):
        for v in (2 * centroid[1], 2 * centroid[1] + 1):
            assert viewport_color(h, v) == WHITE


def test_non_crosshair_viewport_uses_winner_palette_for_every_mode():
    point = (20, 20)
    query = logical_coordinate(*point)
    assert not is_crosshair(query)
    for mode in range(4):
        assert viewport_color(*point, mode=mode) == PALETTE[classify(query, mode=mode)]


def test_sidebar_geometry_uses_frame_active_mode_training_and_palette():
    for active_mode in range(4):
        for row_mode, vertical in enumerate((40, 88, 136, 184)):
            expected = WHITE if row_mode == active_mode else (1, 1, 1)
            assert sidebar_color(540, vertical, active_mode, False) == expected
    assert sidebar_color(540, 270, MODE_L1, False) == (1, 0, 0)
    assert sidebar_color(540, 270, MODE_L1, True) == PALETTE[1]
    for horizontal, color in zip((535, 560, 585, 610), PALETTE):
        assert sidebar_color(horizontal, 350, MODE_L1, False) == color
    assert sidebar_color(520, 40, MODE_L1, False) == BLACK
    assert pixel_color(700, 20, mode=MODE_L1) == BLACK
    assert pixel_color(540, 40, mode=MODE_L1) == WHITE


def test_lfsr_frozen_sequence_and_maximal_nonzero_cycle():
    expected = (0xACE1, 0xE270, 0x7138, 0x389C, 0x1C4E, 0x0E27, 0xB313)
    state = LFSR_SEED
    observed = []
    for _ in expected:
        observed.append(state)
        state = lfsr_next(state)
    assert tuple(observed) == expected

    state = LFSR_SEED
    seen = set()
    for _ in range(0xFFFF):
        assert state != 0
        assert state not in seen
        seen.add(state)
        state = lfsr_next(state)
    assert state == LFSR_SEED
    assert len(seen) == 0xFFFF


@pytest.mark.parametrize(
    "state,expected",
    [
        (0xEFE1, (0xE1, 239, True)),
        (0xF001, (0x01, 240, False)),
        (0xFFAA, (0xAA, 255, False)),
    ],
)
def test_lfsr_byte_mapping_and_candidate_validity(state, expected):
    assert sample_from_lfsr(state) == expected


@pytest.mark.parametrize("magnitude,step", [(0, 0), (1, 0), (7, 0), (8, 1), (15, 1), (16, 2), (255, 31)])
def test_symmetric_magnitude_shift(magnitude, step):
    assert shifted_coordinate(0, magnitude) == step
    assert shifted_coordinate(255, 255 - magnitude) == 255 - step


def test_manual_saturation_on_both_axes_and_directions():
    centroids = ((0, 0), (255, 239), (10, 10), (20, 20))
    assert apply_manual(centroids, ManualCommand(0, False, False))[0] == (0, 0)
    assert apply_manual(centroids, ManualCommand(0, True, False))[0] == (0, 0)
    assert apply_manual(centroids, ManualCommand(1, False, True))[1] == (255, 239)
    assert apply_manual(centroids, ManualCommand(1, True, True))[1] == (255, 239)
    assert apply_manual(centroids, ManualCommand(2, False, True))[2] == (11, 10)
    assert apply_manual(centroids, ManualCommand(2, True, False))[2] == (10, 9)


def test_training_changes_only_lowest_id_winner():
    centroids = ((0, 0), (0, 0), (255, 239), (255, 239))
    updated, winner = train_centroids(centroids, (80, 80), MODE_L1)
    assert winner == 0
    assert updated[0] == (10, 10)
    assert updated[1:] == centroids[1:]


def test_boundary_latches_requests_but_trains_with_ending_frame_controls():
    state = MachineState(train_active=False)
    first = boundary_transition(state, requested_mode=MODE_HAMMING, requested_training=True)
    assert first.state.mode_active == MODE_HAMMING
    assert first.state.train_active is True
    assert first.state.centroids == INITIAL_CENTROIDS
    assert first.training_applied is False
    assert first.state.lfsr == lfsr_next(LFSR_SEED)

    second = boundary_transition(first.state, requested_mode=MODE_LINF, requested_training=False)
    expected, winner = train_centroids(
        INITIAL_CENTROIDS, second.sample, MODE_HAMMING
    )
    assert second.training_applied is True
    assert second.winner == winner
    assert second.state.centroids == expected
    assert second.state.mode_active == MODE_LINF
    assert second.state.train_active is False


def test_rejected_training_sample_still_advances_lfsr():
    state = MachineState(train_active=True, lfsr=0xF055)
    result = boundary_transition(state, MODE_L1, True)
    assert result.sample == (0x55, 0xF0)
    assert result.sample_valid is False
    assert result.training_applied is False
    assert result.state.centroids == state.centroids
    assert result.state.lfsr == lfsr_next(state.lfsr)


def test_manual_has_priority_over_valid_training_and_is_consumed_once():
    state = MachineState(train_active=True)
    command = ManualCommand(3, axis_y=True, increment=False)
    result = boundary_transition(state, MODE_L2_APPROX, True, command)
    assert result.manual_applied is True
    assert result.training_applied is False
    assert result.winner is None
    assert result.state.centroids[3] == (192, 179)
    assert result.state.centroids[:3] == state.centroids[:3]
    assert result.state.lfsr == lfsr_next(state.lfsr)


def test_two_flop_step_pending_payload_and_rearm_behavior():
    control = InputControlState()
    asserted = 0x80 | (2 << 3) | 0x20 | 0x40  # C2, Y, increment

    control = synchronize_inputs(control, asserted)
    assert control.pending is None
    control = synchronize_inputs(control, asserted)
    assert control.pending is None
    control = synchronize_inputs(control, asserted)
    assert control.pending == ManualCommand(2, axis_y=True, increment=True)

    # Raw payload changes while held cannot mutate or repeat the transaction.
    held_other_payload = 0x80 | (1 << 3)
    for _ in range(5):
        control = synchronize_inputs(control, held_other_payload)
        assert control.pending == ManualCommand(2, axis_y=True, increment=True)

    control = consume_pending(control)
    for _ in range(3):
        control = synchronize_inputs(control, held_other_payload)
    assert control.pending is None

    # Release must propagate through both flops and edge history before re-press.
    for _ in range(3):
        control = synchronize_inputs(control, 0)
    for _ in range(3):
        control = synchronize_inputs(control, held_other_payload)
    assert control.pending == ManualCommand(1, axis_y=False, increment=False)


def test_long_deterministic_boundary_trace_preserves_invariants():
    state = MachineState()
    for frame in range(5_000):
        requested_mode = (frame * 3) & 3
        requested_training = frame % 7 != 0
        pending = None
        if frame % 113 == 17:
            pending = ManualCommand(
                centroid=(frame // 113) & 3,
                axis_y=bool(frame & 1),
                increment=bool(frame & 2),
            )
        old = state
        result = boundary_transition(
            state, requested_mode, requested_training, pending
        )
        state = result.state
        changed = sum(a != b for a, b in zip(old.centroids, state.centroids))
        assert changed <= 1
        assert state.lfsr != old.lfsr
        assert state.lfsr != 0
        assert all(0 <= x <= 255 and 0 <= y <= 239 for x, y in state.centroids)
        assert result.manual_applied is (pending is not None)
        if result.training_applied:
            assert old.train_active and result.sample_valid and pending is None
