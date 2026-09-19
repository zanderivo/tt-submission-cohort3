"""Validate Tiny Tapeout IHP26b metadata, RTL bindings, and build workflows."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
INFO_PATH = REPO_ROOT / "info.yaml"
WORKFLOW_ROOT = REPO_ROOT / ".github" / "workflows"
ALLOWED_TILES = {"1x1", "1x2", "2x2", "3x2", "4x2", "6x2", "8x2"}
TARGET_ACTION_TAG = "ttihp26b"
TARGET_PDK = "ihp-sg13g2"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_workflow(name: str) -> tuple[dict, str]:
    raw = (WORKFLOW_ROOT / name).read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    require(isinstance(parsed, dict), f"{name} must contain a YAML mapping")
    require(isinstance(parsed.get("jobs"), dict), f"{name} must contain jobs")
    return parsed, raw


def validate_ihp_target() -> None:
    loaded_workflows = {
        name: load_workflow(name)
        for name in ("gds.yaml", "docs.yaml", "fpga.yaml")
    }
    expected_actions = {
        "gds.yaml": {
            "gds": "TinyTapeout/tt-gds-action@ttihp26b",
            "precheck": "TinyTapeout/tt-gds-action/precheck@ttihp26b",
            "viewer": "TinyTapeout/tt-gds-action/viewer@ttihp26b",
        },
        "docs.yaml": {
            "docs": "TinyTapeout/tt-gds-action/docs@ttihp26b",
        },
        "fpga.yaml": {
            "fpga": "TinyTapeout/tt-gds-action/fpga/ice40up5k@ttihp26b",
        },
    }

    for workflow_name, job_actions in expected_actions.items():
        workflow, _ = loaded_workflows[workflow_name]
        jobs = workflow["jobs"]
        observed_actions: list[str] = []
        for job_name, expected_action in job_actions.items():
            job = jobs.get(job_name)
            require(isinstance(job, dict), f"{workflow_name} is missing job {job_name}")
            steps = job.get("steps")
            require(
                isinstance(steps, list),
                f"{workflow_name} job {job_name} must contain steps",
            )
            action_steps = [
                step
                for step in steps
                if isinstance(step, dict)
                and isinstance(step.get("uses"), str)
                and step["uses"].startswith("TinyTapeout/tt-gds-action")
            ]
            observed_actions.extend(step["uses"] for step in action_steps)
            require(
                len(action_steps) == 1 and action_steps[0]["uses"] == expected_action,
                f"{workflow_name} job {job_name} must use {expected_action}",
            )

            if workflow_name == "gds.yaml" and job_name == "gds":
                inputs = action_steps[0].get("with")
                require(
                    isinstance(inputs, dict) and inputs.get("pdk") == TARGET_PDK,
                    f"gds workflow Build GDS step must select {TARGET_PDK}",
                )

        require(
            sorted(observed_actions) == sorted(job_actions.values()),
            f"{workflow_name} contains unexpected Tiny Tapeout action steps",
        )

    gds_jobs = loaded_workflows["gds.yaml"][0]["jobs"]
    for dependent_job in ("precheck", "viewer"):
        require(
            gds_jobs[dependent_job].get("needs") == "gds",
            f"gds.yaml job {dependent_job} must depend on gds",
        )

    dockerfile = (REPO_ROOT / ".devcontainer" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    require(
        re.search(
            rf"^ENV\s+PDK={re.escape(TARGET_PDK)}\s*$", dockerfile, re.MULTILINE
        )
        is not None,
        f"devcontainer must set PDK={TARGET_PDK}",
    )
    require(
        "librelane==3.0.5" in dockerfile,
        "devcontainer LibreLane must match the ttihp26b action default (3.0.5)",
    )

    raw_workflows = [raw for _, raw in loaded_workflows.values()]
    target_text = "\n".join((*raw_workflows, dockerfile)).lower()
    require("ttsky" not in target_text, "Sky Tiny Tapeout action remains in target files")
    require("sky130" not in target_text, "Sky130 PDK reference remains in target files")


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

    validate_ihp_target()

    print(
        f"Tiny Tapeout IHP26b metadata valid: {top_module}, "
        f"{project['tiles']}, {project['clock_hz']} Hz, {TARGET_PDK}"
    )


if __name__ == "__main__":
    main()
