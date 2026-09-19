"""Validate Tiny Tapeout metadata and cross-file top-module bindings."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
INFO_PATH = REPO_ROOT / "info.yaml"
ALLOWED_TILES = {"1x1", "1x2", "2x2", "3x2", "4x2", "6x2", "8x2"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    info = yaml.safe_load(INFO_PATH.read_text(encoding="utf-8"))
    require(isinstance(info, dict), "info.yaml must contain a mapping")
    require(info.get("yaml_version") == 6, "info.yaml yaml_version must be 6")

    project = info.get("project")
    require(isinstance(project, dict), "info.yaml must contain a project mapping")
    for field in (
        "title",
        "author",
        "description",
        "language",
        "clock_hz",
        "tiles",
        "top_module",
        "source_files",
    ):
        require(field in project, f"project.{field} is required")

    require(project["language"] == "Verilog", "project.language must be Verilog")
    require(project["tiles"] in ALLOWED_TILES, "project.tiles is invalid")
    require(
        isinstance(project["clock_hz"], int) and project["clock_hz"] > 0,
        "project.clock_hz must be a positive integer",
    )

    top_module = project["top_module"]
    require(
        isinstance(top_module, str) and top_module.startswith("tt_um_"),
        "project.top_module must start with tt_um_",
    )

    source_files = project["source_files"]
    require(
        isinstance(source_files, list) and source_files,
        "project.source_files must be a non-empty list",
    )

    rtl_parts: list[str] = []
    for source_name in source_files:
        require(isinstance(source_name, str), "each source file must be a string")
        source_path = (SRC_ROOT / source_name).resolve()
        require(
            source_path.is_relative_to(SRC_ROOT.resolve()),
            f"source file escapes src/: {source_name}",
        )
        require(source_path.is_file(), f"missing source file: src/{source_name}")
        rtl_parts.append(source_path.read_text(encoding="utf-8"))

    rtl = "\n".join(rtl_parts)
    require(
        re.search(rf"\bmodule\s+{re.escape(top_module)}\b", rtl) is not None,
        f"RTL does not declare top module {top_module}",
    )

    testbench = (REPO_ROOT / "test" / "tb.v").read_text(encoding="utf-8")
    require(
        re.search(
            rf"\b{re.escape(top_module)}\s+user_project\s*\(", testbench
        )
        is not None,
        f"test/tb.v does not instantiate {top_module} as user_project",
    )

    makefile = (REPO_ROOT / "test" / "Makefile").read_text(encoding="utf-8")
    require(
        re.search(
            rf"^RTL_TOP\s*\?=\s*{re.escape(top_module)}\s*$", makefile, re.MULTILINE
        )
        is not None,
        f"test/Makefile RTL_TOP does not match {top_module}",
    )

    pinout = info.get("pinout")
    require(isinstance(pinout, dict), "info.yaml must contain a pinout mapping")
    expected_pins = {
        f"{group}[{index}]"
        for group in ("ui", "uo", "uio")
        for index in range(8)
    }
    require(set(pinout) == expected_pins, "pinout must contain exactly ui/uo/uio[0:7]")
    require(
        all(isinstance(value, str) for value in pinout.values()),
        "all pinout descriptions must be strings",
    )

    config = json.loads((SRC_ROOT / "config.json").read_text(encoding="utf-8"))
    require(config.get("CLOCK_PORT") == "clk", "config CLOCK_PORT must be clk")
    expected_period_ns = 1_000_000_000 / project["clock_hz"]
    require(
        abs(float(config["CLOCK_PERIOD"]) - expected_period_ns) < 1e-9,
        "info.yaml clock_hz and src/config.json CLOCK_PERIOD disagree",
    )

    print(
        f"Tiny Tapeout metadata valid: {top_module}, "
        f"{project['tiles']}, {project['clock_hz']} Hz"
    )


if __name__ == "__main__":
    main()
