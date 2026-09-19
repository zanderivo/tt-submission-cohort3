`default_nettype none
`timescale 1ns / 1ps

module tb ();

  // Full-frame dumps are intentionally opt-in: make WAVES=1.
  initial begin
    if ($test$plusargs("DUMP_WAVES")) begin
      $dumpfile("tb.fst");
      $dumpvars(0, tb);
    end
  end

  reg        clk;
  reg        rst_n;
  reg        ena;
  reg  [7:0] ui_in;
  reg  [7:0] uio_in;
  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;

  tt_um_zanderivo_voronoi user_project (
      .ui_in  (ui_in),
      .uo_out (uo_out),
      .uio_in (uio_in),
      .uio_out(uio_out),
      .uio_oe (uio_oe),
      .ena    (ena),
      .clk    (clk),
      .rst_n  (rst_n)
  );

`ifndef GL_TEST
  // Combinational metric probe for wide/random directed vectors that legal VGA
  // coordinates cannot all produce. It instantiates the real RTL lane and is
  // excluded from gate-level builds, where only tile ports are used.
  reg  [7:0] probe_qx;
  reg  [7:0] probe_qy;
  reg  [7:0] probe_cx;
  reg  [7:0] probe_cy;
  reg  [1:0] probe_mode;
  wire [8:0] probe_distance;
  wire [7:0] probe_dx;
  wire [7:0] probe_dy;

  distance_lane metric_probe (
      .qx(probe_qx),
      .qy(probe_qy),
      .cx(probe_cx),
      .cy(probe_cy),
      .mode(probe_mode),
      .distance(probe_distance),
      .dx(probe_dx),
      .dy(probe_dy)
  );
`endif

endmodule
