"""Run the Lesson 04 Davis hydrograph reporting-interval experiment.

Only disposable copies under work/ can be changed or computed. Geometry,
rainfall, the 12-second computation step, and the 10-minute mapping interval
stay fixed. The four plans change only the hydrograph reporting interval.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "data/Example_Projects_7_0/Pipes/Davis"
RAS_EXE = Path(r"C:\Program Files (x86)\HEC\HEC-RAS\7.0.1\Ras.exe")
INTERVALS = {"1MIN": 60, "1HOUR": 3600, "15MIN": 900, "5MIN": 300}
STEM = "DavisStormSystem"


def manifest(root: Path) -> dict[str, str]:
    """Hash every file in the small source project, including terrain."""
    import hashlib

    hashes = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            with path.open("rb") as stream:
                hashes[path.relative_to(root).as_posix()] = hashlib.file_digest(
                    stream, "sha256"
                ).hexdigest()
    return hashes


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def plan_settings(path: Path) -> dict[str, str]:
    return {
        key: value.strip()
        for line in path.read_text().splitlines()
        if "=" in line
        for key, value in [line.split("=", 1)]
    }


def check_paths(output: Path, project: Path) -> None:
    if not output.resolve().is_relative_to(REPO / "outputs"):
        raise ValueError("Reports must be under outputs/.")
    if not project.resolve().is_relative_to(REPO / "work"):
        raise ValueError("The project to modify or compute must be under work/.")


def prepare(output: Path) -> None:
    """Copy the complete source, verify it, then clone plans with RAS Commander."""
    from ras_commander import RasPlan, init_ras_project

    project = REPO / "work" / output.name / "Davis"
    check_paths(output, project)
    if output.exists() or project.exists():
        raise FileExistsError(
            "Use a new output directory name; existing experiments are preserved."
        )
    before = manifest(SOURCE)
    shutil.copytree(SOURCE, project)
    if manifest(project) != before:
        raise RuntimeError("The disposable copy does not match the source.")
    output.mkdir(parents=True)
    save_json(output / "source_manifest.json", before)
    ras = init_ras_project(
        project / f"{STEM}.prj",
        str(RAS_EXE),
        ras_object="new",
        load_results_summary=False,
        hide_intro=True,
        accept_tcu=False,
    )
    template = project / f"{STEM}.p02"
    baseline = plan_settings(template)
    expected = {
        "Computation Interval": "12SEC",
        "Mapping Interval": "10MIN",
        "Simulation Date": "10JAN2000,1200,11JAN2000,2400",
        "Geom File": "g02",
        "Flow File": "u01",
        "Computation Time Step Use Courant": "0",
    }
    for key, value in expected.items():
        if baseline.get(key) != value:
            raise ValueError(f"Unexpected source {key}: {baseline.get(key)}; expected {value}.")
    plans = []
    for interval, seconds in INTERVALS.items():
        number = RasPlan.clone_plan(
            "02",
            new_shortid=f"Report {interval}",
            new_title=f"Davis reporting {interval}",
            ras_object=ras,
        )
        path = project / f"{STEM}.p{number}"
        RasPlan.update_plan_intervals(path, output_interval=interval, ras_object=ras)
        actual = plan_settings(path)
        changed = sorted(
            key for key in baseline.keys() | actual.keys() if baseline.get(key) != actual.get(key)
        )
        if set(changed) - {"Plan Title", "Short Identifier", "Output Interval"}:
            raise RuntimeError(f"Unexpected plan changes: {changed}")
        plans.append(
            {
                "interval": interval,
                "seconds": seconds,
                "plan": str(number),
                "changed_settings": changed,
            }
        )
    save_json(
        output / "experiment.json",
        {
            "created_utc": datetime.now(UTC).isoformat(),
            "source": str(SOURCE),
            "project": str(project / f"{STEM}.prj"),
            "ras_exe": str(RAS_EXE),
            "fixed_settings": expected,
            "plans": plans,
            "source_unchanged": manifest(SOURCE) == before,
        },
    )
    print(output / "experiment.json")


def run(output: Path, interval: str) -> None:
    """Run one fresh plan using the course's RAS Commander runner and retain its log."""
    experiment = json.loads((output / "experiment.json").read_text())
    project = Path(experiment["project"])
    check_paths(output, project)
    selected = next(row for row in experiment["plans"] if row["interval"] == interval)
    receipt = output / f"run_{interval}.json"
    hdf = project.with_suffix(f".p{selected['plan']}.hdf")
    if receipt.exists() or hdf.exists():
        raise FileExistsError(f"Preserving existing results for {interval}; use a new experiment.")
    with (output / f"run_{interval}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                str(REPO / "scripts/run_all_example_plans.py"),
                "run-one",
                "--project",
                str(project),
                "--plan",
                selected["plan"],
                "--ras-exe",
                experiment["ras_exe"],
                "--result",
                str(receipt),
            ],
            cwd=REPO,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            returncode = process.wait(timeout=900)
        except subprocess.TimeoutExpired as exc:
            # Stop only this runner and its child HEC-RAS processes on Windows.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=True,
            )
            process.wait(timeout=30)
            raise RuntimeError(f"HEC-RAS exceeded 15 minutes; inspect {log.name}.") from exc
    if manifest(SOURCE) != json.loads((output / "source_manifest.json").read_text()):
        raise RuntimeError("Source project hashes changed.")
    if returncode:
        raise RuntimeError(f"HEC-RAS run failed. Inspect {receipt} and the matching log.")
    print(receipt)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", choices=INTERVALS, default="1MIN")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.command == "prepare":
        prepare(output)
    else:
        run(output, args.interval)


if __name__ == "__main__":
    main()
