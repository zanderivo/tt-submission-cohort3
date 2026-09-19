# Cocotb/Icarus verification for the VGA nearest-prototype tile

SIM ?= icarus
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(CURDIR)/../src
PROJECT_SOURCES = project.v
RTL_TOP ?= tt_um_zanderivo_voronoi
WAVES ?= 0

ifneq ($(GATES),yes)

# RTL simulation. TEST_LEVEL enables hierarchy-dependent acceleration and
# observability in tests that are explicitly skipped by gate-level runs.
SIM_BUILD = sim_build/rtl
VERILOG_SOURCES += $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))
export TEST_LEVEL = rtl

else

# Gate-level simulation for the IHP SG13G2 PDK.  Hierarchy tests are explicitly
# skipped; port tests retain one full frame and add boundary-aligned mode,
# synchronized-manual, and training observations in only three further frames.
SIM_BUILD = sim_build/gl
COMPILE_ARGS += -DGL_TEST
COMPILE_ARGS += -DFUNCTIONAL
COMPILE_ARGS += -DSIM
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_io/verilog/sg13g2_io.v
VERILOG_SOURCES += $(PDK_ROOT)/ihp-sg13g2/libs.ref/sg13g2_stdcell/verilog/sg13g2_stdcell.v
VERILOG_SOURCES += $(CURDIR)/gate_level_netlist.v
export TEST_LEVEL = gate

endif

COMPILE_ARGS += -I$(SRC_DIR)
VERILOG_SOURCES += $(CURDIR)/tb.v
TOPLEVEL = tb
COCOTB_TEST_MODULES ?= test

# Full-frame traces are large and slow, especially for a routed netlist.  Keep
# dumping opt-in while preserving `make WAVES=1` for failure reproduction.
ifeq ($(WAVES),1)
FST ?= -fst
PLUSARGS += +DUMP_WAVES
endif

include $(shell cocotb-config --makefiles)/Makefile.sim

.PHONY: lint model check
lint:
	@mkdir -p $(SIM_BUILD)
	iverilog -g2012 -Wall -Wimplicit -s $(RTL_TOP) -o $(SIM_BUILD)/lint.vvp $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES))

model:
	python -m pytest -q test_model.py

check: model lint sim
