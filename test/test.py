# SPDX-FileCopyrightText: 2026 Zander Ivo
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer


@cocotb.test()
async def test_counter_increments_for_ten_clock_cycles(dut):
    """Reset the tile, then verify one increment on each of ten clock edges."""
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.clk.value = 0
    dut.rst_n.value = 0

    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await Timer(1, unit="ns")
    assert dut.uo_out.value == 0, "asynchronous reset did not clear the counter"
    assert dut.uio_out.value == 0, "unused bidirectional outputs must be low"
    assert dut.uio_oe.value == 0, "unused bidirectional pins must remain inputs"

    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    for expected_count in range(1, 11):
        await RisingEdge(dut.clk)
        await ReadOnly()
        assert dut.uo_out.value == expected_count, (
            f"expected count {expected_count}, got {dut.uo_out.value.integer}"
        )
