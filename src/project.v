/*
 * Copyright (c) 2026 Zander Ivo
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_smoketest (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // Bidirectional inputs
    output wire [7:0] uio_out,  // Bidirectional outputs
    output wire [7:0] uio_oe,   // Bidirectional enable (1=out, 0=in)
    input  wire       ena,      // Tiny Tapeout enable signal
    input  wire       clk,      // System clock
    input  wire       rst_n     // Active-low asynchronous reset
);

    assign uio_out = 8'b00000000;
    assign uio_oe  = 8'b00000000;

    reg [7:0] count_reg;
    assign uo_out = count_reg;

    wire _unused_ok = &{ena, ui_in, uio_in, 1'b0};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count_reg <= 8'h00;
        end else begin
            count_reg <= count_reg + 1'b1;
        end
    end

endmodule
