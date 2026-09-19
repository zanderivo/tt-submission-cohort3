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

    // Logical grid is 64 x 60; every logical cell is an 8x8 block of screen
    // pixels inside the 512x480 viewport. Six-bit coordinates keep the four
    // parallel distance lanes, the argmin tree and the prototype registers
    // narrow enough for a 1x1 tile.
    localparam [5:0] X_MAX = 6'd63;
    localparam [5:0] Y_MAX = 6'd59;

    // ------------------------------------------------------------ VGA timing
    reg [9:0] h_count;
    reg [9:0] v_count;

    wire h_last = (h_count == 10'd799);
    wire v_last = (v_count == 10'd524);

    wire h_active = (h_count < 10'd640);
    wire v_active = (v_count < 10'd480);

    // h_count[9] splits the active line at 512: low half is the viewport,
    // high half is the sidebar. No extra comparator needed.
    wire viewport_on = v_active && !h_count[9];
    wire sidebar_on  = v_active && h_count[9] && h_active;

    wire frame_tick = h_last && v_last;
    wire hsync_n = !((h_count >= 10'd656) && (h_count <= 10'd751));
    wire vsync_n = !((v_count >= 10'd490) && (v_count <= 10'd491));

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            h_count <= 10'd0;
            v_count <= 10'd0;
        end else if (h_last) begin
            h_count <= 10'd0;
            v_count <= v_last ? 10'd0 : (v_count + 10'd1);
        end else begin
            h_count <= h_count + 10'd1;
        end
    end

    // -------------------------------------------------------- input capture
    // Level requests take one synchronizing flop; they are captured a second
    // time at the frame boundary, which completes the two-stage handoff. Only
    // the step strobe needs a dedicated two-flop synchronizer plus a delayed
    // copy for edge detection.
    reg       mode_req;
    reg       train_req;
    reg [1:0] id_req;
    reg       axis_req;
    reg       dir_req;
    reg       step_s1;
    reg       step_s2;
    reg       step_d;

    wire step_rise = step_s2 && !step_d;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mode_req  <= 1'b0;
            train_req <= 1'b0;
            id_req    <= 2'd0;
            axis_req  <= 1'b0;
            dir_req   <= 1'b0;
            step_s1   <= 1'b0;
            step_s2   <= 1'b0;
            step_d    <= 1'b0;
        end else begin
            mode_req  <= ui_in[0];
            train_req <= ui_in[2];
            id_req    <= ui_in[4:3];
            axis_req  <= ui_in[5];
            dir_req   <= ui_in[6];
            step_s1   <= ui_in[7];
            step_s2   <= step_s1;
            step_d    <= step_s2;
        end
    end

    // ------------------------------------------------------------ chip state
    reg mode_active;
    reg train_active;
    reg pending;

    reg [5:0] c0x, c0y;
    reg [5:0] c1x, c1y;
    reg [5:0] c2x, c2y;
    reg [5:0] c3x, c3y;

    reg  [15:0] lfsr;
    wire [15:0] lfsr_next = (lfsr >> 1) ^ (lfsr[0] ? 16'hB400 : 16'h0000);
    wire [5:0]  sample_x  = lfsr[5:0];
    wire [5:0]  sample_y  = lfsr[11:6];
    wire        sample_ok = (sample_y <= Y_MAX);

    // The classifier is shared: it answers the raster position during display
    // and the training sample during the final blanking pixel.
    wire [5:0] query_x = frame_tick ? sample_x : h_count[8:3];
    wire [5:0] query_y = frame_tick ? sample_y : v_count[8:3];

    // ----------------------------------------------------- distance lanes
    wire [6:0] d0, d1, d2, d3;
    wire [5:0] dx0, dy0, dx1, dy1, dx2, dy2, dx3, dy3;
    wire       xg0, yg0, xg1, yg1, xg2, yg2, xg3, yg3;

    distance_lane lane0 (
        .qx(query_x), .qy(query_y), .cx(c0x), .cy(c0y), .mode(mode_active),
        .dist(d0), .dx(dx0), .dy(dy0), .xge(xg0), .yge(yg0)
    );
    distance_lane lane1 (
        .qx(query_x), .qy(query_y), .cx(c1x), .cy(c1y), .mode(mode_active),
        .dist(d1), .dx(dx1), .dy(dy1), .xge(xg1), .yge(yg1)
    );
    distance_lane lane2 (
        .qx(query_x), .qy(query_y), .cx(c2x), .cy(c2y), .mode(mode_active),
        .dist(d2), .dx(dx2), .dy(dy2), .xge(xg2), .yge(yg2)
    );
    distance_lane lane3 (
        .qx(query_x), .qy(query_y), .cx(c3x), .cy(c3y), .mode(mode_active),
        .dist(d3), .dx(dx3), .dy(dy3), .xge(xg3), .yge(yg3)
    );

    // Deterministic lowest-index argmin.
    wire       a01 = (d0 <= d1);
    wire       a23 = (d2 <= d3);
    wire [6:0] dA  = a01 ? d0 : d1;
    wire [6:0] dB  = a23 ? d2 : d3;
    wire [1:0] iA  = a01 ? 2'd0 : 2'd1;
    wire [1:0] iB  = a23 ? 2'd2 : 2'd3;
    wire [1:0] win = (dA <= dB) ? iA : iB;

    // --------------------------------------------- shared prototype update
    // Manual nudges and training steps are the same operation: move one
    // prototype along one or both axes by a magnitude, with saturation. A
    // single add/sub per axis serves both, replacing the eight per-register
    // increment/decrement units of the 1x2 design.
    //
    // The training magnitude reuses the winning lane's own |delta|: at
    // frame_tick query_x == sample_x, so dx of the winning lane already is
    // |sample_x - cx|, and dx[5:2] is |delta| >> 2.
    wire [1:0] sel = pending ? id_req : win;

    reg [5:0] sel_x, sel_y;
    reg [3:0] sel_sx, sel_sy;
    reg       sel_xg, sel_yg;

    always @* begin
        case (sel)
            2'd0: begin
                sel_x = c0x; sel_y = c0y;
                sel_sx = dx0[5:2]; sel_sy = dy0[5:2];
                sel_xg = xg0; sel_yg = yg0;
            end
            2'd1: begin
                sel_x = c1x; sel_y = c1y;
                sel_sx = dx1[5:2]; sel_sy = dy1[5:2];
                sel_xg = xg1; sel_yg = yg1;
            end
            2'd2: begin
                sel_x = c2x; sel_y = c2y;
                sel_sx = dx2[5:2]; sel_sy = dy2[5:2];
                sel_xg = xg2; sel_yg = yg2;
            end
            default: begin
                sel_x = c3x; sel_y = c3y;
                sel_sx = dx3[5:2]; sel_sy = dy3[5:2];
                sel_xg = xg3; sel_yg = yg3;
            end
        endcase
    end

    wire [3:0] step_x = pending ? 4'd1 : sel_sx;
    wire [3:0] step_y = pending ? 4'd1 : sel_sy;
    wire       dir_x  = pending ? dir_req : sel_xg;
    wire       dir_y  = pending ? dir_req : sel_yg;

    // One 7-bit adder per axis: add on increment, add the ones' complement
    // with carry-in on decrement. Bit 6 then flags both kinds of overrun.
    wire [6:0] mag_x = dir_x ? {3'b000, step_x} : ~{3'b000, step_x};
    wire [6:0] mag_y = dir_y ? {3'b000, step_y} : ~{3'b000, step_y};
    wire [6:0] res_x = {1'b0, sel_x} + mag_x + {6'b000000, ~dir_x};
    wire [6:0] res_y = {1'b0, sel_y} + mag_y + {6'b000000, ~dir_y};

    wire [5:0] new_x = res_x[6] ? (dir_x ? X_MAX : 6'd0) : res_x[5:0];
    wire [5:0] new_y = dir_y ? ((res_y > {1'b0, Y_MAX}) ? Y_MAX : res_y[5:0])
                             : (res_y[6] ? 6'd0 : res_y[5:0]);

    wire train_go = train_active && sample_ok;
    wire do_upd   = frame_tick && (pending || train_go);
    wire upd_x    = do_upd && (pending ? !axis_req : 1'b1);
    wire upd_y    = do_upd && (pending ?  axis_req : 1'b1);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mode_active  <= 1'b0;
            train_active <= 1'b0;
            pending      <= 1'b0;
            c0x <= 6'd16; c0y <= 6'd15;
            c1x <= 6'd48; c1y <= 6'd15;
            c2x <= 6'd16; c2y <= 6'd45;
            c3x <= 6'd48; c3y <= 6'd45;
            lfsr <= 16'hACE1;
        end else begin
            if (frame_tick) begin
                mode_active  <= mode_req;
                train_active <= train_req;
                lfsr         <= lfsr_next;
                pending      <= 1'b0;
            end

            if (upd_x) begin
                case (sel)
                    2'd0:    c0x <= new_x;
                    2'd1:    c1x <= new_x;
                    2'd2:    c2x <= new_x;
                    default: c3x <= new_x;
                endcase
            end

            if (upd_y) begin
                case (sel)
                    2'd0:    c0y <= new_y;
                    2'd1:    c1y <= new_y;
                    2'd2:    c2y <= new_y;
                    default: c3y <= new_y;
                endcase
            end

            // A step edge arriving on the frame boundary still registers.
            if (step_rise && !pending)
                pending <= 1'b1;
        end
    end

    // ------------------------------------------------------------ rendering
    // Three-by-three logical plus sign per prototype: cheap zero/one tests on
    // the deltas the lanes already produce.
    wire hair0 = ((dx0 == 6'd0) && (dy0 <= 6'd1)) ||
                 ((dy0 == 6'd0) && (dx0 <= 6'd1));
    wire hair1 = ((dx1 == 6'd0) && (dy1 <= 6'd1)) ||
                 ((dy1 == 6'd0) && (dx1 <= 6'd1));
    wire hair2 = ((dx2 == 6'd0) && (dy2 <= 6'd1)) ||
                 ((dy2 == 6'd0) && (dx2 <= 6'd1));
    wire hair3 = ((dx3 == 6'd0) && (dy3 <= 6'd1)) ||
                 ((dy3 == 6'd0) && (dx3 <= 6'd1));
    wire hair  = hair0 || hair1 || hair2 || hair3;

    // Sidebar indicators sit on 32-pixel bands and 64-pixel columns, so every
    // window decodes as an equality test on high counter bits instead of a
    // pair of 10-bit range comparators.
    wire [3:0] vband = v_count[8:5];
    wire       sb_l  = sidebar_on && !h_count[6];
    wire       sb_r  = sidebar_on &&  h_count[6];

    wire ind_m0 = sb_l && (vband == 4'd1);
    wire ind_m1 = sb_l && (vband == 4'd3);
    wire ind_tr = sb_l && (vband == 4'd7);
    wire pal0   = sb_r && (vband == 4'd10);
    wire pal1   = sb_r && (vband == 4'd11);
    wire pal2   = sb_r && (vband == 4'd12);
    wire pal3   = sb_r && (vband == 4'd13);

    reg [1:0] red;
    reg [1:0] green;
    reg [1:0] blue;

    always @* begin
        red   = 2'd0;
        green = 2'd0;
        blue  = 2'd0;

        if (viewport_on) begin
            if (hair) begin
                red = 2'd3; green = 2'd3; blue = 2'd3;
            end else begin
                case (win)
                    2'd0:    begin red = 2'd3; green = 2'd1; blue = 2'd0; end
                    2'd1:    begin red = 2'd0; green = 2'd3; blue = 2'd0; end
                    2'd2:    begin red = 2'd0; green = 2'd2; blue = 2'd3; end
                    default: begin red = 2'd2; green = 2'd0; blue = 2'd3; end
                endcase
            end
        end else if (ind_m0) begin
            if (!mode_active) begin red = 2'd3; green = 2'd3; blue = 2'd3; end
            else              begin red = 2'd1; green = 2'd1; blue = 2'd1; end
        end else if (ind_m1) begin
            if (mode_active)  begin red = 2'd3; green = 2'd3; blue = 2'd3; end
            else              begin red = 2'd1; green = 2'd1; blue = 2'd1; end
        end else if (ind_tr) begin
            if (train_active) begin red = 2'd0; green = 2'd3; blue = 2'd0; end
            else              begin red = 2'd1; green = 2'd0; blue = 2'd0; end
        end else if (pal0) begin
            red = 2'd3; green = 2'd1; blue = 2'd0;
        end else if (pal1) begin
            red = 2'd0; green = 2'd3; blue = 2'd0;
        end else if (pal2) begin
            red = 2'd0; green = 2'd2; blue = 2'd3;
        end else if (pal3) begin
            red = 2'd2; green = 2'd0; blue = 2'd3;
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

    wire _unused_ok = &{ena, uio_in, ui_in[1], 1'b0};

endmodule

module distance_lane (
    input  wire [5:0] qx,
    input  wire [5:0] qy,
    input  wire [5:0] cx,
    input  wire [5:0] cy,
    input  wire       mode,
    output wire [6:0] dist,
    output wire [5:0] dx,
    output wire [5:0] dy,
    output wire       xge,
    output wire       yge
);

    // xge/yge are the comparison the magnitude already needs, exported so the
    // update datapath does not instantiate its own direction comparators.
    assign xge = (qx >= cx);
    assign yge = (qy >= cy);

    assign dx = xge ? (qx - cx) : (cx - qx);
    assign dy = yge ? (qy - cy) : (cy - qy);

    wire [5:0] dmax = (dx >= dy) ? dx : dy;

    assign dist = mode ? {1'b0, dmax} : ({1'b0, dx} + {1'b0, dy});

endmodule

`default_nettype wire
