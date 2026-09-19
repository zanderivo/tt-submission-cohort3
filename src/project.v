/*
 * Copyright (c) 2026 Zander Ivo
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_zanderivo_voronoi (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

    reg [9:0] h_count;
    reg [9:0] v_count;

    wire display_on = (h_count < 10'd640) && (v_count < 10'd480);
    wire viewport_on = display_on && (h_count < 10'd512);
    wire sidebar_on = display_on && (h_count >= 10'd512);
    wire frame_tick = (h_count == 10'd799) && (v_count == 10'd524);
    wire hsync_n = !((h_count >= 10'd656) && (h_count <= 10'd751));
    wire vsync_n = !((v_count >= 10'd490) && (v_count <= 10'd491));

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            h_count <= 10'd0;
            v_count <= 10'd0;
        end else if (h_count == 10'd799) begin
            h_count <= 10'd0;
            if (v_count == 10'd524)
                v_count <= 10'd0;
            else
                v_count <= v_count + 10'd1;
        end else begin
            h_count <= h_count + 10'd1;
        end
    end

    reg [7:0] ui_meta;
    reg [7:0] ui_sync;
    reg       step_sync_d;

    wire step_rise = ui_sync[7] && !step_sync_d;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            ui_meta     <= 8'd0;
            ui_sync     <= 8'd0;
            step_sync_d <= 1'b0;
        end else begin
            ui_meta     <= ui_in;
            ui_sync     <= ui_meta;
            step_sync_d <= ui_sync[7];
        end
    end

    reg       mode_active;
    reg       train_active;

    reg [7:0] c0_x;
    reg [7:0] c0_y;
    reg [7:0] c1_x;
    reg [7:0] c1_y;
    reg [7:0] c2_x;
    reg [7:0] c2_y;
    reg [7:0] c3_x;
    reg [7:0] c3_y;

    reg       manual_pending;
    reg [1:0] manual_id;
    reg       manual_axis;
    reg       manual_direction;

    reg [15:0] lfsr;
    wire [7:0] sample_x = lfsr[7:0];
    wire [7:0] sample_y = lfsr[15:8];
    wire       sample_valid = sample_y < 8'd240;
    wire [15:0] lfsr_next = (lfsr >> 1) ^ (lfsr[0] ? 16'hB400 : 16'h0000);

    wire [7:0] query_x = frame_tick ? sample_x : h_count[8:1];
    wire [7:0] query_y = frame_tick ? sample_y : v_count[8:1];

    wire [8:0] distance0;
    wire [8:0] distance1;
    wire [8:0] distance2;
    wire [8:0] distance3;
    wire [7:0] dx0;
    wire [7:0] dy0;
    wire [7:0] dx1;
    wire [7:0] dy1;
    wire [7:0] dx2;
    wire [7:0] dy2;
    wire [7:0] dx3;
    wire [7:0] dy3;

    distance_lane lane0 (
        .qx(query_x), .qy(query_y), .cx(c0_x), .cy(c0_y),
        .mode(mode_active), .distance(distance0), .dx(dx0), .dy(dy0)
    );
    distance_lane lane1 (
        .qx(query_x), .qy(query_y), .cx(c1_x), .cy(c1_y),
        .mode(mode_active), .distance(distance1), .dx(dx1), .dy(dy1)
    );
    distance_lane lane2 (
        .qx(query_x), .qy(query_y), .cx(c2_x), .cy(c2_y),
        .mode(mode_active), .distance(distance2), .dx(dx2), .dy(dy2)
    );
    distance_lane lane3 (
        .qx(query_x), .qy(query_y), .cx(c3_x), .cy(c3_y),
        .mode(mode_active), .distance(distance3), .dx(dx3), .dy(dy3)
    );

    wire       pair01_choose0 = distance0 <= distance1;
    wire       pair23_choose2 = distance2 <= distance3;
    wire [8:0] pair01_distance = pair01_choose0 ? distance0 : distance1;
    wire [8:0] pair23_distance = pair23_choose2 ? distance2 : distance3;
    wire [1:0] pair01_id = pair01_choose0 ? 2'd0 : 2'd1;
    wire [1:0] pair23_id = pair23_choose2 ? 2'd2 : 2'd3;
    wire       choose_pair01 = pair01_distance <= pair23_distance;
    wire [1:0] winner_id = choose_pair01 ? pair01_id : pair23_id;

    reg [7:0] winner_cx;
    reg [7:0] winner_cy;
    always @* begin
        case (winner_id)
            2'd0: begin winner_cx = c0_x; winner_cy = c0_y; end
            2'd1: begin winner_cx = c1_x; winner_cy = c1_y; end
            2'd2: begin winner_cx = c2_x; winner_cy = c2_y; end
            default: begin winner_cx = c3_x; winner_cy = c3_y; end
        endcase
    end

    function [4:0] abs_delta_div8;
        input [7:0] lhs;
        input [7:0] rhs;
        begin
            if (lhs >= rhs) begin
                if (lhs[2:0] < rhs[2:0])
                    abs_delta_div8 = lhs[7:3] - rhs[7:3] - 5'd1;
                else
                    abs_delta_div8 = lhs[7:3] - rhs[7:3];
            end else begin
                if (rhs[2:0] < lhs[2:0])
                    abs_delta_div8 = rhs[7:3] - lhs[7:3] - 5'd1;
                else
                    abs_delta_div8 = rhs[7:3] - lhs[7:3];
            end
        end
    endfunction

    wire [4:0] train_step_x = abs_delta_div8(sample_x, winner_cx);
    wire [4:0] train_step_y = abs_delta_div8(sample_y, winner_cy);
    wire [8:0] train_sum_x = {1'b0, winner_cx} + {4'b0000, train_step_x};
    wire [8:0] train_sum_y = {1'b0, winner_cy} + {4'b0000, train_step_y};

    reg [7:0] train_new_x;
    reg [7:0] train_new_y;
    always @* begin
        train_new_x = winner_cx;
        train_new_y = winner_cy;

        if (sample_x > winner_cx) begin
            if (train_sum_x > 9'd255)
                train_new_x = 8'd255;
            else
                train_new_x = train_sum_x[7:0];
        end else if (sample_x < winner_cx) begin
            if ({3'b000, train_step_x} > winner_cx)
                train_new_x = 8'd0;
            else
                train_new_x = winner_cx - {3'b000, train_step_x};
        end

        if (sample_y > winner_cy) begin
            if (train_sum_y > 9'd239)
                train_new_y = 8'd239;
            else
                train_new_y = train_sum_y[7:0];
        end else if (sample_y < winner_cy) begin
            if ({3'b000, train_step_y} > winner_cy)
                train_new_y = 8'd0;
            else
                train_new_y = winner_cy - {3'b000, train_step_y};
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mode_active      <= 1'b0;
            train_active     <= 1'b0;
            c0_x             <= 8'd64;
            c0_y             <= 8'd60;
            c1_x             <= 8'd192;
            c1_y             <= 8'd60;
            c2_x             <= 8'd64;
            c2_y             <= 8'd180;
            c3_x             <= 8'd192;
            c3_y             <= 8'd180;
            manual_pending   <= 1'b0;
            manual_id        <= 2'd0;
            manual_axis      <= 1'b0;
            manual_direction <= 1'b0;
            lfsr             <= 16'hACE1;
        end else begin
            if (frame_tick) begin
                mode_active  <= ui_sync[0];
                train_active <= ui_sync[2];
                lfsr         <= lfsr_next;

                if (manual_pending) begin
                    case (manual_id)
                        2'd0: begin
                            if (!manual_axis) begin
                                if (manual_direction) begin
                                    if (c0_x != 8'd255) c0_x <= c0_x + 8'd1;
                                end else begin
                                    if (c0_x != 8'd0) c0_x <= c0_x - 8'd1;
                                end
                            end else begin
                                if (manual_direction) begin
                                    if (c0_y != 8'd239) c0_y <= c0_y + 8'd1;
                                end else begin
                                    if (c0_y != 8'd0) c0_y <= c0_y - 8'd1;
                                end
                            end
                        end
                        2'd1: begin
                            if (!manual_axis) begin
                                if (manual_direction) begin
                                    if (c1_x != 8'd255) c1_x <= c1_x + 8'd1;
                                end else begin
                                    if (c1_x != 8'd0) c1_x <= c1_x - 8'd1;
                                end
                            end else begin
                                if (manual_direction) begin
                                    if (c1_y != 8'd239) c1_y <= c1_y + 8'd1;
                                end else begin
                                    if (c1_y != 8'd0) c1_y <= c1_y - 8'd1;
                                end
                            end
                        end
                        2'd2: begin
                            if (!manual_axis) begin
                                if (manual_direction) begin
                                    if (c2_x != 8'd255) c2_x <= c2_x + 8'd1;
                                end else begin
                                    if (c2_x != 8'd0) c2_x <= c2_x - 8'd1;
                                end
                            end else begin
                                if (manual_direction) begin
                                    if (c2_y != 8'd239) c2_y <= c2_y + 8'd1;
                                end else begin
                                    if (c2_y != 8'd0) c2_y <= c2_y - 8'd1;
                                end
                            end
                        end
                        default: begin
                            if (!manual_axis) begin
                                if (manual_direction) begin
                                    if (c3_x != 8'd255) c3_x <= c3_x + 8'd1;
                                end else begin
                                    if (c3_x != 8'd0) c3_x <= c3_x - 8'd1;
                                end
                            end else begin
                                if (manual_direction) begin
                                    if (c3_y != 8'd239) c3_y <= c3_y + 8'd1;
                                end else begin
                                    if (c3_y != 8'd0) c3_y <= c3_y - 8'd1;
                                end
                            end
                        end
                    endcase
                    manual_pending <= 1'b0;
                end else if (train_active && sample_valid) begin
                    case (winner_id)
                        2'd0: begin c0_x <= train_new_x; c0_y <= train_new_y; end
                        2'd1: begin c1_x <= train_new_x; c1_y <= train_new_y; end
                        2'd2: begin c2_x <= train_new_x; c2_y <= train_new_y; end
                        default: begin c3_x <= train_new_x; c3_y <= train_new_y; end
                    endcase
                end
            end

            if (step_rise && !manual_pending) begin
                manual_pending   <= 1'b1;
                manual_id        <= ui_sync[4:3];
                manual_axis      <= ui_sync[5];
                manual_direction <= ui_sync[6];
            end
        end
    end

    wire crosshair0 = ((dy0 <= 8'd1) && (dx0 <= 8'd4)) ||
                      ((dx0 <= 8'd1) && (dy0 <= 8'd4));
    wire crosshair1 = ((dy1 <= 8'd1) && (dx1 <= 8'd4)) ||
                      ((dx1 <= 8'd1) && (dy1 <= 8'd4));
    wire crosshair2 = ((dy2 <= 8'd1) && (dx2 <= 8'd4)) ||
                      ((dx2 <= 8'd1) && (dy2 <= 8'd4));
    wire crosshair3 = ((dy3 <= 8'd1) && (dx3 <= 8'd4)) ||
                      ((dx3 <= 8'd1) && (dy3 <= 8'd4));
    wire any_crosshair = crosshair0 || crosshair1 || crosshair2 || crosshair3;

    wire mode_row_h = (h_count >= 10'd528) && (h_count <= 10'd623);
    wire mode_row0 = mode_row_h && (v_count >= 10'd32)  && (v_count <= 10'd63);
    wire mode_row1 = mode_row_h && (v_count >= 10'd80)  && (v_count <= 10'd111);
    wire training_block = mode_row_h && (v_count >= 10'd256) && (v_count <= 10'd303);
    wire palette_v = (v_count >= 10'd336) && (v_count <= 10'd367);
    wire palette0 = palette_v && (h_count >= 10'd528) && (h_count <= 10'd547);
    wire palette1 = palette_v && (h_count >= 10'd553) && (h_count <= 10'd572);
    wire palette2 = palette_v && (h_count >= 10'd578) && (h_count <= 10'd597);
    wire palette3 = palette_v && (h_count >= 10'd603) && (h_count <= 10'd622);

    reg [1:0] red;
    reg [1:0] green;
    reg [1:0] blue;

    always @* begin
        red   = 2'd0;
        green = 2'd0;
        blue  = 2'd0;

        if (display_on) begin
            if (sidebar_on) begin
                if (mode_row0) begin
                    if (mode_active == 2'd0) begin red = 2'd3; green = 2'd3; blue = 2'd3; end
                    else begin red = 2'd1; green = 2'd1; blue = 2'd1; end
                end else if (mode_row1) begin
                    if (mode_active == 2'd1) begin red = 2'd3; green = 2'd3; blue = 2'd3; end
                    else begin red = 2'd1; green = 2'd1; blue = 2'd1; end
                end else if (training_block) begin
                    if (train_active) begin red = 2'd0; green = 2'd3; blue = 2'd0; end
                    else begin red = 2'd1; green = 2'd0; blue = 2'd0; end
                end else if (palette0) begin
                    red = 2'd3; green = 2'd1; blue = 2'd0;
                end else if (palette1) begin
                    red = 2'd0; green = 2'd3; blue = 2'd0;
                end else if (palette2) begin
                    red = 2'd0; green = 2'd2; blue = 2'd3;
                end else if (palette3) begin
                    red = 2'd2; green = 2'd0; blue = 2'd3;
                end
            end else if (viewport_on) begin
                if (any_crosshair) begin
                    red = 2'd3; green = 2'd3; blue = 2'd3;
                end else begin
                    case (winner_id)
                        2'd0: begin red = 2'd3; green = 2'd1; blue = 2'd0; end
                        2'd1: begin red = 2'd0; green = 2'd3; blue = 2'd0; end
                        2'd2: begin red = 2'd0; green = 2'd2; blue = 2'd3; end
                        default: begin red = 2'd2; green = 2'd0; blue = 2'd3; end
                    endcase
                end
            end
        end
    end

    assign uo_out[0] = red[1];
    assign uo_out[1] = green[1];
    assign uo_out[2] = blue[1];
    assign uo_out[3] = vsync_n;
    assign uo_out[4] = red[0];
    assign uo_out[5] = green[0];
    assign uo_out[6] = blue[0];
    assign uo_out[7] = hsync_n;

    assign uio_out = 8'b00000000;
    assign uio_oe  = 8'b00000000;

    wire _unused_ok = &{ena, uio_in, 1'b0};

endmodule

module distance_lane (
    input  wire [7:0] qx,
    input  wire [7:0] qy,
    input  wire [7:0] cx,
    input  wire [7:0] cy,
    input  wire       mode,
    output reg  [8:0] distance,
    output wire [7:0] dx,
    output wire [7:0] dy
);

    assign dx = (qx >= cx) ? (qx - cx) : (cx - qx);
    assign dy = (qy >= cy) ? (qy - cy) : (cy - qy);

    wire [7:0] max_d = (dx >= dy) ? dx : dy;

    always @* begin
        case (mode)
            1'b0: distance = {1'b0, dx} + {1'b0, dy};
            default: distance = {1'b0, max_d};
        endcase
    end

endmodule

`default_nettype wire
