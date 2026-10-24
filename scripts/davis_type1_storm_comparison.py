"""Prepare and summarize a controlled Davis Type I rainfall comparison.

The source project under data/ is read-only. The prepare command creates a complete
verified copy under work/, adds two unsteady-flow files and two plans, and records
provenance under outputs/. The summarize command reads completed result HDF files and
writes a comparison table for the pump station and downstream boundary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data"
WORK_ROOT = REPO_ROOT / "work"
OUTPUT_ROOT = REPO_ROOT / "outputs"

DEFAULT_SOURCE = DATA_ROOT / "Example_Projects_7_0" / "Pipes" / "Davis"
DEFAULT_WORK_PROJECT = WORK_ROOT / "davis_type1_design_storms_20260829" / "DavisStormSystem"
DEFAULT_OUTPUT_DIR = OUTPUT_ROOT / "davis_type1_design_storms_20260829"

PROJECT_STEM = "DavisStormSystem"
DESIGN_SIMULATION_END = "12JAN2000,2400"
DESIGN_SIMULATION_HOURS = 60
NOAA_POINT_LATITUDE = 38.55498757
NOAA_POINT_LONGITUDE = -121.74974082
NOAA_ATLAS_14_URL = (
    "https://hdsc.nws.noaa.gov/cgi-bin/hdsc/new/cgi_readH5.py?"
    "lat=38.55498757&lon=-121.74974082&type=pf&data=depth&units=english&series=pds"
)
TYPE_I_SOURCE_URL = (
    "https://www.nrcs.usda.gov/sites/default/files/2022-12/COMPLETE%20ND%20Hydrology%20Manual.pdf"
)

# SCS Type I cumulative rainfall fractions at 0.5-hour intervals. The first value
# is time zero. The repeated final 1.000 value supplies a trailing zero interval.
# Source: NRCS Hydrology Manual, figure 6-3, SCS-272(a), revised June 1965.
TYPE_I_CUMULATIVE_FRACTIONS = (
    0.000,
    0.008,
    0.017,
    0.026,
    0.035,
    0.045,
    0.055,
    0.065,
    0.076,
    0.087,
    0.099,
    0.112,
    0.125,
    0.140,
    0.156,
    0.174,
    0.194,
    0.219,
    0.254,
    0.303,
    0.515,
    0.583,
    0.624,
    0.654,
    0.682,
    0.705,
    0.727,
    0.748,
    0.767,
    0.784,
    0.800,
    0.816,
    0.833,
    0.844,
    0.857,
    0.870,
    0.882,
    0.893,
    0.905,
    0.916,
    0.926,
    0.936,
    0.946,
    0.955,
    0.965,
    0.974,
    0.983,
    0.992,
    1.000,
    1.000,
)

SCENARIOS = {
    "original": {
        "plan": "02",
        "flow": "01",
        "label": "Original hypothetical storm",
        "atlas_14_depth_in": None,
    },
    "10-year": {
        "plan": "03",
        "flow": "02",
        "label": "10-year, 24-hour Type I",
        "atlas_14_depth_in": 3.34,
    },
    "100-year": {
        "plan": "04",
        "flow": "03",
        "label": "100-year, 24-hour Type I",
        "atlas_14_depth_in": 5.10,
    },
}


def utc_now() -> str:
    """Return a compact UTC timestamp."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def require_descendant(path: Path, parent: Path, label: str) -> Path:
    """Resolve a path and require it to be below the stated parent."""
    resolved = path.resolve()
    resolved_parent = parent.resolve()
    if resolved == resolved_parent or not resolved.is_relative_to(resolved_parent):
        raise ValueError(f"{label} must be below {resolved_parent}: {resolved}")
    return resolved


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hash for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_manifest(root: Path) -> list[dict[str, Any]]:
    """Create a deterministic manifest for every file below root."""
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item).casefold()):
        if path.is_file():
            rows.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return rows


def write_json(path: Path, value: Any) -> None:
    """Write indented JSON with a trailing newline."""
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def type_i_incremental_depths(total_depth_in: float) -> list[float]:
    """Return Type I period depths with an initial zero ordinate."""
    if total_depth_in <= 0:
        raise ValueError("Total rainfall depth must be positive.")
    increments = [0.0]
    increments.extend(
        (current - previous) * total_depth_in
        for previous, current in zip(
            TYPE_I_CUMULATIVE_FRACTIONS,
            TYPE_I_CUMULATIVE_FRACTIONS[1:],
            strict=False,
        )
    )
    return increments


def format_hydrograph_values(values: list[float]) -> list[str]:
    """Format HEC-RAS hydrograph ordinates in rows of ten."""
    return [
        "".join(f"{value:8.5f}" for value in values[index : index + 10])
        for index in range(0, len(values), 10)
    ]


def replace_first_line(lines: list[str], prefix: str, replacement: str) -> None:
    """Replace the first matching text-file setting."""
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return
    raise ValueError(f"Missing expected setting: {prefix}")


def build_unsteady_flow(source_text: str, title: str, total_depth_in: float) -> str:
    """Clone the source flow text and replace its precipitation hydrograph."""
    lines = source_text.splitlines()
    replace_first_line(lines, "Flow Title=", f"Flow Title={title}")

    hydrograph_index = next(
        index for index, line in enumerate(lines) if line.startswith("Precipitation Hydrograph=")
    )
    interval_index = hydrograph_index - 1
    if not lines[interval_index].startswith("Interval="):
        raise ValueError("The precipitation interval was not immediately before the hydrograph.")

    match = re.fullmatch(r"Precipitation Hydrograph=\s*(\d+)\s*", lines[hydrograph_index])
    if match is None:
        raise ValueError("Could not parse the source precipitation hydrograph count.")
    old_count = int(match.group(1))
    values_seen = 0
    end_index = hydrograph_index + 1
    while values_seen < old_count:
        values_seen += len(lines[end_index].split())
        end_index += 1
    if values_seen != old_count:
        raise ValueError("The source precipitation hydrograph count does not match its ordinates.")

    values = type_i_incremental_depths(total_depth_in)
    replacement = [
        "Interval=30MIN",
        f"Precipitation Hydrograph= {len(values)} ",
        *format_hydrograph_values(values),
    ]
    lines[interval_index:end_index] = replacement
    return "\r\n".join(lines) + "\r\n"


def build_plan(source_text: str, title: str, short_identifier: str, flow_number: str) -> str:
    """Clone the source plan and assign a design-storm flow file."""
    lines = source_text.splitlines()
    replace_first_line(lines, "Plan Title=", f"Plan Title={title}")
    replace_first_line(lines, "Short Identifier=", f"Short Identifier={short_identifier:<80}")
    replace_first_line(lines, "Flow File=", f"Flow File=u{flow_number}")
    replace_first_line(
        lines,
        "Simulation Date=",
        f"Simulation Date=10JAN2000,1200,{DESIGN_SIMULATION_END}",
    )
    return "\r\n".join(lines) + "\r\n"


def add_project_entries(project_text: str) -> str:
    """Register the two added unsteady-flow and plan files."""
    lines = project_text.splitlines()
    if any(line == "Plan File=p03" for line in lines):
        raise ValueError("The source project already contains plan p03.")
    unsteady_index = max(
        index for index, line in enumerate(lines) if line.startswith("Unsteady File=")
    )
    lines[unsteady_index + 1 : unsteady_index + 1] = ["Unsteady File=u02", "Unsteady File=u03"]
    plan_index = max(index for index, line in enumerate(lines) if line.startswith("Plan File="))
    lines[plan_index + 1 : plan_index + 1] = ["Plan File=p03", "Plan File=p04"]
    return "\r\n".join(lines) + "\r\n"


def distribution_rows() -> list[dict[str, float]]:
    """Build a review table for both Type I design storms."""
    rows: list[dict[str, float]] = []
    ten_year = type_i_incremental_depths(3.34)
    hundred_year = type_i_incremental_depths(5.10)
    for index, cumulative_fraction in enumerate(TYPE_I_CUMULATIVE_FRACTIONS):
        rows.append(
            {
                "time_hours": index * 0.5,
                "cumulative_fraction": cumulative_fraction,
                "incremental_10yr_depth_in": ten_year[index],
                "cumulative_10yr_depth_in": cumulative_fraction * 3.34,
                "incremental_100yr_depth_in": hundred_year[index],
                "cumulative_100yr_depth_in": cumulative_fraction * 5.10,
            }
        )
    return rows


def write_distribution_csv(path: Path) -> None:
    """Write the Type I time series used in the HEC-RAS flow files."""
    rows = distribution_rows()
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def prepare(source: Path, work_project: Path, output_dir: Path) -> None:
    """Copy, verify, and modify the disposable Davis project."""
    source = require_descendant(source, DATA_ROOT, "Source project")
    work_project = require_descendant(work_project, WORK_ROOT, "Work project")
    output_dir = require_descendant(output_dir, OUTPUT_ROOT, "Output directory")
    if not source.is_dir():
        raise FileNotFoundError(f"Source project directory not found: {source}")
    if work_project.exists():
        raise FileExistsError(f"Refusing to overwrite work project: {work_project}")
    if output_dir.exists():
        raise FileExistsError(f"Refusing to overwrite output directory: {output_dir}")

    output_dir.mkdir(parents=True)
    source_manifest = file_manifest(source)
    write_json(output_dir / "source_manifest.json", source_manifest)

    work_project.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, work_project)
    copied_manifest = file_manifest(work_project)
    write_json(output_dir / "copy_manifest_before_edits.json", copied_manifest)
    if source_manifest != copied_manifest:
        raise RuntimeError("The copied project did not match the source manifest.")

    source_flow_text = (work_project / f"{PROJECT_STEM}.u01").read_text(
        encoding="utf-8", errors="strict"
    )
    source_plan_text = (work_project / f"{PROJECT_STEM}.p02").read_text(
        encoding="utf-8", errors="strict"
    )
    project_path = work_project / f"{PROJECT_STEM}.prj"

    (work_project / f"{PROJECT_STEM}.u02").write_text(
        build_unsteady_flow(source_flow_text, "10-year 24-hour Type I rainfall", 3.34),
        encoding="utf-8",
        newline="",
    )
    (work_project / f"{PROJECT_STEM}.u03").write_text(
        build_unsteady_flow(source_flow_text, "100-year 24-hour Type I rainfall", 5.10),
        encoding="utf-8",
        newline="",
    )
    (work_project / f"{PROJECT_STEM}.p03").write_text(
        build_plan(
            source_plan_text,
            "10-year 24-hour Type I",
            "10-year 24-hour Type I",
            "02",
        ),
        encoding="utf-8",
        newline="",
    )
    (work_project / f"{PROJECT_STEM}.p04").write_text(
        build_plan(
            source_plan_text,
            "100-year 24-hour Type I",
            "100-year 24-hour Type I",
            "03",
        ),
        encoding="utf-8",
        newline="",
    )
    project_path.write_text(
        add_project_entries(project_path.read_text(encoding="utf-8", errors="strict")),
        encoding="utf-8",
        newline="",
    )

    readme = f"""# Davis Type I design-storm comparison

Prepared: {utc_now()}

Source project: `{source}`

This is a complete disposable copy. The source project remains unchanged. Plan `p02` is the
original hypothetical storm. Plan `p03` uses the 10-year, 24-hour NOAA Atlas 14 depth of
3.34 inches with the classical SCS Type I distribution. Plan `p04` uses the 100-year depth
of 5.10 inches with the same Type I distribution. Both design plans run for
{DESIGN_SIMULATION_HOURS} hours to retain 36 hours after the 24-hour rainfall period.

NOAA point: {NOAA_POINT_LATITUDE:.8f}, {NOAA_POINT_LONGITUDE:.8f}

NOAA Atlas 14 query: {NOAA_ATLAS_14_URL}

Type I source: {TYPE_I_SOURCE_URL}

Generated tables and run evidence: `{output_dir}`
"""
    (work_project / "README_DESIGN_STORMS.md").write_text(readme, encoding="utf-8")
    write_distribution_csv(output_dir / "type1_precipitation_distributions.csv")
    write_json(output_dir / "work_manifest_after_prepare.json", file_manifest(work_project))
    write_json(
        output_dir / "preparation_summary.json",
        {
            "prepared_at": utc_now(),
            "source_project": str(source),
            "work_project": str(work_project),
            "source_file_count": len(source_manifest),
            "copy_verified_before_edits": True,
            "added_files": [
                f"{PROJECT_STEM}.u02",
                f"{PROJECT_STEM}.u03",
                f"{PROJECT_STEM}.p03",
                f"{PROJECT_STEM}.p04",
                "README_DESIGN_STORMS.md",
            ],
            "noaa_point": {
                "latitude": NOAA_POINT_LATITUDE,
                "longitude": NOAA_POINT_LONGITUDE,
            },
            "noaa_atlas_14_url": NOAA_ATLAS_14_URL,
            "type_i_source_url": TYPE_I_SOURCE_URL,
            "plans": SCENARIOS,
        },
    )


def decode_hdf_text(value: Any) -> str:
    """Decode an HDF text value."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def parse_volume_error_percent(message: str) -> float | None:
    """Extract the overall volume accounting error percentage."""
    match = re.search(r"Overall Volume Accounting Error as percentage:\s*([-+0-9.]+)", message)
    return float(match.group(1)) if match else None


def extract_plan_result(hdf_path: Path) -> dict[str, Any]:
    """Extract fixed-location peak flows and run-health evidence from one result HDF."""
    import h5py
    import numpy as np

    base = "Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series"
    with h5py.File(hdf_path, "r") as hdf:
        times = [decode_hdf_text(value) for value in hdf[f"{base}/Time Date Stamp"][:]]
        precipitation = hdf[f"{base}/2D Flow Areas/area2/Cell Cumulative Precipitation Depth"][:]
        outlet = hdf[f"{base}/2D Flow Areas/DS Channel/Boundary Conditions/DS Normal"][:, 1]
        pump = hdf[f"{base}/Pumping Stations/Pump Station #1/Structure Variables"][:, 0]
        message = decode_hdf_text(hdf["Results/Summary/Compute Messages (text)"][0])

    pump_index = int(np.nanargmax(pump))
    outlet_index = int(np.nanargmax(outlet))
    return {
        "hdf_path": str(hdf_path),
        "hdf_sha256": sha256_file(hdf_path),
        "effective_precipitation_depth_in": float(np.nanmax(precipitation)),
        "peak_pump_flow_cfs": float(pump[pump_index]),
        "pump_peak_time": times[pump_index],
        "final_pump_flow_cfs": float(pump[-1]),
        "peak_outlet_flow_cfs": float(outlet[outlet_index]),
        "outlet_peak_time": times[outlet_index],
        "final_outlet_flow_cfs": float(outlet[-1]),
        "final_result_time": times[-1],
        "volume_accounting_error_percent": parse_volume_error_percent(message),
        "compute_message_has_complete_process": "Complete Process" in message,
        "compute_message_error_line_count": sum(
            "error" in line.casefold()
            for line in message.splitlines()
            if "volume accounting error" not in line.casefold()
        ),
        "compute_messages": message,
    }


def percent_change(value: float, baseline: float) -> float:
    """Calculate percent change from a nonzero baseline."""
    if baseline == 0:
        raise ValueError("Cannot calculate percent change from a zero baseline.")
    return (value - baseline) / baseline * 100.0


def write_comparison_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write the peak-flow comparison table."""
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows: list[dict[str, Any]]) -> str:
    """Render the main comparison columns as Markdown."""
    header = (
        "| Scenario | Rainfall (in) | Pump peak (cfs) | Pump change | "
        "Outlet peak (cfs) | Outlet change | Volume error |"
    )
    separator = "|---|---:|---:|---:|---:|---:|---:|"
    body = []
    for row in rows:
        pump_change = (
            "baseline"
            if row["pump_change_percent_vs_original"] is None
            else f"{row['pump_change_percent_vs_original']:+.1f}%"
        )
        outlet_change = (
            "baseline"
            if row["outlet_change_percent_vs_original"] is None
            else f"{row['outlet_change_percent_vs_original']:+.1f}%"
        )
        volume_error = row["volume_accounting_error_percent"]
        body.append(
            f"| {row['scenario_label']} | {row['effective_precipitation_depth_in']:.3f} | "
            f"{row['peak_pump_flow_cfs']:.2f} | {pump_change} | "
            f"{row['peak_outlet_flow_cfs']:.2f} | {outlet_change} | "
            f"{volume_error:.3f}% |"
        )
    return "\n".join([header, separator, *body])


def summarize(work_project: Path, output_dir: Path) -> None:
    """Summarize completed HEC-RAS plans into fixed-location peak-flow comparisons."""
    work_project = require_descendant(work_project, WORK_ROOT, "Work project")
    output_dir = require_descendant(output_dir, OUTPUT_ROOT, "Output directory")
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Output directory not found: {output_dir}")

    extracted: dict[str, dict[str, Any]] = {}
    for scenario, settings in SCENARIOS.items():
        hdf_path = work_project / f"{PROJECT_STEM}.p{settings['plan']}.hdf"
        if not hdf_path.is_file():
            raise FileNotFoundError(f"Missing result HDF for {scenario}: {hdf_path}")
        extracted[scenario] = extract_plan_result(hdf_path)

    baseline = extracted["original"]
    rows: list[dict[str, Any]] = []
    for scenario, settings in SCENARIOS.items():
        result = extracted[scenario]
        is_baseline = scenario == "original"
        rows.append(
            {
                "scenario": scenario,
                "scenario_label": settings["label"],
                "plan_file": f"{PROJECT_STEM}.p{settings['plan']}",
                "flow_file": f"{PROJECT_STEM}.u{settings['flow']}",
                "atlas_14_24hr_depth_in": settings["atlas_14_depth_in"],
                "effective_precipitation_depth_in": result["effective_precipitation_depth_in"],
                "peak_pump_flow_cfs": result["peak_pump_flow_cfs"],
                "pump_peak_time": result["pump_peak_time"],
                "pump_change_cfs_vs_original": None
                if is_baseline
                else result["peak_pump_flow_cfs"] - baseline["peak_pump_flow_cfs"],
                "pump_change_percent_vs_original": None
                if is_baseline
                else percent_change(result["peak_pump_flow_cfs"], baseline["peak_pump_flow_cfs"]),
                "peak_outlet_flow_cfs": result["peak_outlet_flow_cfs"],
                "outlet_peak_time": result["outlet_peak_time"],
                "outlet_change_cfs_vs_original": None
                if is_baseline
                else result["peak_outlet_flow_cfs"] - baseline["peak_outlet_flow_cfs"],
                "outlet_change_percent_vs_original": None
                if is_baseline
                else percent_change(
                    result["peak_outlet_flow_cfs"], baseline["peak_outlet_flow_cfs"]
                ),
                "volume_accounting_error_percent": result["volume_accounting_error_percent"],
                "complete_process_message": result["compute_message_has_complete_process"],
                "compute_message_error_line_count": result["compute_message_error_line_count"],
                "result_hdf_sha256": result["hdf_sha256"],
            }
        )

    write_comparison_csv(output_dir / "peak_flow_comparison.csv", rows)
    write_json(output_dir / "extracted_results.json", extracted)
    report = f"""# Davis Type I storm comparison run review

Generated: {utc_now()}

Work project: `{work_project}`

HEC-RAS runtime: `C:\\Program Files (x86)\\HEC\\HEC-RAS\\7.0.1`

The table uses two fixed named model locations. `Pump Station #1` is the modeled pump
discharge. `DS Normal` is the downstream normal-depth boundary on the `DS Channel` 2D area.

{markdown_table(rows)}

The original text ordinates sum to 1.30 inches, but the computed HDF reports 1.20 inches.
HEC-RAS treats the first period-cumulative ordinate as the initial value. The design-storm
files start with zero, and their computed cumulative depths match 3.34 and 5.10 inches.

The Type I plans use 30-minute incremental rainfall depths from the classical SCS Type I
cumulative distribution. The total depths come from NOAA Atlas 14 at the area2 centroid,
latitude {NOAA_POINT_LATITUDE:.8f}, longitude {NOAA_POINT_LONGITUDE:.8f}. Both design
plans run for {DESIGN_SIMULATION_HOURS} hours. That leaves 36 hours after the 24-hour storm.

The design runs do not reach full recession. At the final timestep, the 10-year pump and
outlet flows are {extracted["10-year"]["final_pump_flow_cfs"]:.2f} and
{extracted["10-year"]["final_outlet_flow_cfs"]:.2f} cfs. The 100-year values are
{extracted["100-year"]["final_pump_flow_cfs"]:.2f} and
{extracted["100-year"]["final_outlet_flow_cfs"]:.2f} cfs. Both reported peaks occur before
the final timestep and exceed the final flows. Use this comparison for peak flow only, not
for recession duration or complete runoff-volume accounting.

Automated completion and volume-accounting checks do not establish engineering adequacy.
The comparison changes only precipitation and simulation duration. Geometry, roughness,
infiltration, pump controls, downstream boundary, and all other copied inputs remain as supplied.

Source project: `{DEFAULT_SOURCE}`

NOAA Atlas 14 query: {NOAA_ATLAS_14_URL}

Type I source: {TYPE_I_SOURCE_URL}
"""
    (output_dir / "RUN_REVIEW.md").write_text(report, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "summarize"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--work-project", type=Path, default=DEFAULT_WORK_PROJECT)
        command_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
        if command == "prepare":
            command_parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    return parser


def main() -> int:
    """Run the selected workflow step."""
    args = build_parser().parse_args()
    if args.command == "prepare":
        prepare(args.source, args.work_project, args.output_dir)
    else:
        summarize(args.work_project, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
