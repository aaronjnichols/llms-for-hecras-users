"""Read the four completed Davis plans and plot reporting-interval effects.

This is a project-specific Lesson 04 extractor. It reads the DSS Hydrograph
Output block, with that block's own time axis, and selects Pipe 67 by name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import h5py
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

try:
    from scripts.davis_output_interval import REPO, SOURCE, manifest, plan_settings, save_json
except ModuleNotFoundError:
    from davis_output_interval import REPO, SOURCE, manifest, plan_settings, save_json

BLOCKS = "Results/Unsteady/Output/Output Blocks"
DSS = f"{BLOCKS}/DSS Hydrograph Output/Unsteady Time Series"
BASE = f"{BLOCKS}/Base Output/Unsteady Time Series"
PIPE_ATTRS = "Geometry/Pipe Conduits/Attributes"
NODE_ATTRS = "Geometry/Pipe Nodes/Attributes"
NODE_INDICES = "Geometry/Pipe Networks/Davis/Node Indices"
CONDUIT_INDICES = "Geometry/Pipe Networks/Davis/Conduit Indices"
PIPE_FLOW = f"{DSS}/Pipe Networks/Davis/Pipes/Pipe Flow DS"
NODE_WSE = f"{DSS}/Pipe Networks/Davis/Nodes/Water Surface"
BOUNDARY = f"{DSS}/2D Flow Areas/DS Channel/Boundary Conditions/DS Normal"
ORDER = ["1HOUR", "15MIN", "5MIN", "1MIN"]
COLORS = {
    "1HOUR": "#c45527",
    "15MIN": "#9e6eaa",
    "5MIN": "#21867a",
    "1MIN": "#2268a5",
}
LABELS = {
    "1HOUR": "1 hour",
    "15MIN": "15 minutes",
    "5MIN": "5 minutes",
    "1MIN": "1 minute",
}
VARIABLES = {
    "pipe_flow_cfs": ("Pipe 67 downstream discharge", "cfs"),
    "node_wse_ft": ("Upstream node O14-DMH047 water surface", "ft"),
    "boundary_flow_cfs": ("DS Normal boundary outflow", "cfs"),
    "boundary_wse_ft": ("DS Normal boundary water surface", "ft"),
}
Y_LABELS = {
    "pipe_flow_cfs": "Pipe 67 downstream flow, cfs",
    "node_wse_ft": "WSE at O14-DMH047, ft",
    "boundary_flow_cfs": "DS Normal outflow, cfs",
    "boundary_wse_ft": "DS Normal stage, ft",
}


def decode(value: object) -> str:
    return value.decode().strip() if isinstance(value, bytes) else str(value).strip()


def unique_index(records: np.ndarray, name: str) -> int:
    indices = [
        i
        for i, row in enumerate(records)
        if decode(row["Name"]) == name and decode(row["System Name"]) == "Davis"
    ]
    if len(indices) != 1:
        raise ValueError(f"Expected exactly one Davis record for {name}; found {len(indices)}.")
    return indices[0]


def network_indices(hdf: h5py.File, path: str, records: np.ndarray) -> np.ndarray:
    """Read the explicit result-column to global-geometry index map."""
    if path not in hdf:
        raise ValueError(f"Missing network index map: {path}")
    indices = hdf[path][:]
    if (
        indices.ndim != 1
        or not np.issubdtype(indices.dtype, np.integer)
        or not len(indices)
        or len(np.unique(indices)) != len(indices)
        or np.any(indices < 0)
        or np.any(indices >= len(records))
    ):
        raise ValueError(f"Invalid network index map: {path}")
    if any(decode(records[int(index)]["System Name"]) != "Davis" for index in indices):
        raise ValueError(f"Network map refers to another system: {path}")
    return indices


def result_column(indices: np.ndarray, geometry_index: int) -> int:
    """Invert a validated map for one selected geometry record."""
    columns = np.flatnonzero(indices == geometry_index)
    if len(columns) != 1:
        raise ValueError(f"Geometry index {geometry_index} is absent from the network map.")
    return int(columns[0])


def read_series(path: Path, seconds: int) -> tuple[pd.DataFrame, dict]:
    """Validate identifiers, units, time axes and finite values before extraction."""
    with h5py.File(path, "r") as hdf:
        if decode(hdf.attrs["Units System"]) != "US Customary":
            raise ValueError("This lesson requires US Customary output.")
        pipes = hdf[PIPE_ATTRS][:]
        nodes = hdf[NODE_ATTRS][:]
        conduit_indices = network_indices(hdf, CONDUIT_INDICES, pipes)
        node_indices = network_indices(hdf, NODE_INDICES, nodes)
        pipe_index = unique_index(pipes, "67")
        node_name = decode(pipes[pipe_index]["US Node"])
        if node_name != "O14-DMH047":
            raise ValueError(f"Unexpected Pipe 67 upstream node: {node_name}")
        node_index = unique_index(nodes, node_name)
        pipe_column = result_column(conduit_indices, pipe_index)
        node_column = result_column(node_indices, node_index)
        time_seconds = hdf[f"{DSS}/Time"][:] * 86400
        rounded = np.rint(time_seconds).astype(np.int64)
        if not np.allclose(time_seconds, rounded, atol=1e-5, rtol=0):
            raise ValueError("Time values are not whole seconds as expected.")
        if not np.array_equal(rounded, np.arange(0, 36 * 3600 + 1, seconds)):
            raise ValueError(f"Incomplete simulation or unexpected reporting interval: {path}")
        dates = [decode(value) for value in hdf[f"{DSS}/Time Date Stamp"][:]]
        timestamps = pd.to_datetime(dates, format="%d%b%Y %H:%M:%S")
        if not np.array_equal((timestamps - timestamps[0]).total_seconds(), rounded):
            raise ValueError("Date stamps do not agree with this output block's numeric times.")
        if hdf[PIPE_FLOW].shape != (len(rounded), len(conduit_indices)):
            raise ValueError("Pipe result dimensions do not match time and geometry identifiers.")
        if hdf[NODE_WSE].shape != (len(rounded), len(node_indices)):
            raise ValueError("Node result dimensions do not match time and geometry identifiers.")
        if decode(hdf[PIPE_FLOW].attrs["Units"]) != "ft^3/s":
            raise ValueError("Unexpected pipe discharge unit.")
        if decode(hdf[NODE_WSE].attrs["Units"]) != "ft":
            raise ValueError("Unexpected node stage unit.")
        boundary_columns = [decode(value) for value in hdf[BOUNDARY].attrs["Columns"]]
        if boundary_columns != ["Stage", "Flow"]:
            raise ValueError(f"Unexpected boundary columns: {boundary_columns}")
        if (decode(hdf[BOUNDARY].attrs["Flow"]), decode(hdf[BOUNDARY].attrs["Stage"])) != (
            "cfs",
            "ft",
        ):
            raise ValueError("Unexpected boundary units.")
        frame = pd.DataFrame(
            {
                "time_seconds": rounded,
                "elapsed_hours": rounded / 3600,
                "timestamp": timestamps,
                "pipe_flow_cfs": hdf[PIPE_FLOW][:, pipe_column],
                "node_wse_ft": hdf[NODE_WSE][:, node_column],
                "boundary_flow_cfs": hdf[BOUNDARY][:, 1],
                "boundary_wse_ft": hdf[BOUNDARY][:, 0],
            }
        )
        if not np.isfinite(frame[list(VARIABLES)].to_numpy()).all():
            raise ValueError("A selected result contains a non-finite value.")
        messages = decode(hdf["Results/Summary/Compute Messages (text)"][0]).replace("\r", "")
        if "Finished Unsteady Flow Simulation" not in messages:
            raise ValueError("The computation messages do not confirm a finished simulation.")
        if re.search(r"(?i)aborted|unstable|fatal|error loading|error determining", messages):
            raise ValueError("The computation messages contain a run failure; inspect them.")
        error = re.search(r"Overall Volume Accounting Error as percentage:\s*([-\d.]+)", messages)
        if error is None:
            raise ValueError("No overall volume accounting error was found.")
        base_seconds = hdf[f"{BASE}/Time"][:] * 86400
        if not np.allclose(np.diff(base_seconds), 600, atol=1e-5, rtol=0):
            raise ValueError("The mapping interval changed.")
        computation_seconds = hdf[f"{DSS}/Time Step"][:]
        if not np.all(computation_seconds == 12):
            raise ValueError("The HDF records a different computation step.")
        corrections = {
            area: float(
                np.max(
                    hdf[
                        f"{BLOCKS}/Base Output/Summary Output/2D Flow Areas/{area}/"
                        "Cell Maximum Water Surface Error"
                    ][0]
                )
            )
            for area in ["area2", "DS Channel"]
        }
        geometry = [
            {"name": decode(row["Name"]), "computational_cells": int(row["Cell Count"])}
            for row in hdf["Geometry/2D Flow Areas/Attributes"][:]
        ]
        details = {
            "hdf": str(path),
            "version": decode(hdf.attrs["File Version"]),
            "geometry": geometry,
            "pipe_index_zero_based": pipe_index,
            "node_index_zero_based": node_index,
            "pipe_result_column_zero_based": pipe_column,
            "node_result_column_zero_based": node_column,
            "network_index_maps": {
                CONDUIT_INDICES: conduit_indices.tolist(),
                NODE_INDICES: node_indices.tolist(),
            },
            "pipe_us_node": node_name,
            "pipe_ds_node": decode(pipes[pipe_index]["DS Node"]),
            "pipe_shape": decode(pipes[pipe_index]["Shape"]),
            "pipe_rise_ft": float(pipes[pipe_index]["Rise"]),
            "pipe_us_invert_ft": float(pipes[pipe_index]["US Elevation"]),
            "hydrograph_rows": len(frame),
            "mapping_rows": len(base_seconds),
            "overall_volume_error_percent": float(error[1]),
            "recorded_computation_step_seconds": 12,
            "maximum_2d_water_surface_correction_ft": corrections,
            "compute_messages": messages,
        }
        return frame, details


def shared_time_differences(reference: pd.DataFrame, candidate: pd.DataFrame) -> dict[str, float]:
    """Compare actual common samples, with no averaging or interpolation in Python."""
    matching = reference.set_index("time_seconds").reindex(candidate.time_seconds)
    if matching[list(VARIABLES)].isna().any().any():
        raise ValueError("Candidate times are not contained in the reference output.")
    return {
        name: float(np.max(np.abs(matching[name].to_numpy() - candidate[name].to_numpy())))
        for name in VARIABLES
    }


def finish_figure(fig: plt.Figure, output: Path, name: str, title: str, subtitle: str) -> None:
    fig.suptitle(title, x=0.06, y=0.98, ha="left", fontsize=18, fontweight="bold")
    fig.text(0.06, 0.93, subtitle, ha="left", fontsize=10, color="#475569")
    fig.text(
        0.06,
        0.02,
        "Davis example | HEC-RAS 7.0.1 | 12-second computation | 10-minute mapping\n"
        "Actual HDF hydrograph samples; straight lines join saved values. "
        "1-minute output is the sampling reference.",
        fontsize=9,
        color="#475569",
    )
    fig.subplots_adjust(left=0.08, right=0.97, bottom=0.15, top=0.85, hspace=0.45, wspace=0.25)
    for ax in fig.axes:
        ax.grid(alpha=0.2)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_xlabel("Hours after 10 Jan 2000, 12:00")
    fig.savefig(output / f"{name}.png", dpi=180, facecolor="white", bbox_inches="tight")
    fig.savefig(output / f"{name}.pdf", facecolor="white", bbox_inches="tight")
    plt.close(fig)


def make_plots(series: dict[str, pd.DataFrame], output: Path) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    reference = series["1MIN"]
    ref_peak = reference.pipe_flow_cfs.max()
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for ax, interval in zip(axes.flat, ORDER[:4], strict=True):
        frame = series[interval]
        row = frame.loc[frame.pipe_flow_cfs.idxmax()]
        ax.plot(
            reference.elapsed_hours,
            reference.pipe_flow_cfs,
            color="#b6bdc6",
            lw=2,
            label=f"1 min reference: {ref_peak:.2f} cfs",
        )
        ax.plot(
            frame.elapsed_hours,
            frame.pipe_flow_cfs,
            color=COLORS[interval],
            lw=1.7,
            marker="o",
            ms=3 if interval == "1MIN" else 5,
            label=f"{LABELS[interval]}: {row.pipe_flow_cfs:.2f} cfs",
        )
        ax.scatter(
            [row.elapsed_hours],
            [row.pipe_flow_cfs],
            s=80,
            color=COLORS[interval],
            edgecolor="white",
            zorder=5,
        )
        loss = 100 * (ref_peak - row.pipe_flow_cfs) / ref_peak
        ax.set_title(f"{LABELS[interval]} output | peak {loss:.1f}% below reference", loc="left")
        ax.set(xlim=(2.5, 5.5), ylim=(-1.5, ref_peak * 1.12), ylabel="Pipe 67 downstream flow, cfs")
        ax.legend(loc="upper right", frameon=False, fontsize=9)
    finish_figure(
        fig,
        output,
        "lesson04_davis_peak_detail",
        "An hourly report misses Pipe 67's short discharge peak",
        "Same geometry and rainfall in every run. Only the Hydrograph Output Interval changes.",
    )

    fig, axes = plt.subplots(2, 1, figsize=(13, 9))
    for ax, variable in zip(axes, ["pipe_flow_cfs", "node_wse_ft"], strict=True):
        for interval in ["1MIN", "1HOUR", "15MIN", "5MIN"]:
            frame = series[interval]
            maximum = frame[variable].max()
            ax.plot(
                frame.elapsed_hours,
                frame[variable],
                color=COLORS[interval],
                lw=1.7,
                marker="o" if interval == "1HOUR" else None,
                ms=3,
                label=f"{LABELS[interval]}: peak {maximum:.2f} {VARIABLES[variable][1]}",
            )
        ax.set(xlim=(0, 36), ylabel=Y_LABELS[variable])
        ax.legend(loc="upper right", frameon=False, fontsize=9)
    finish_figure(
        fig,
        output,
        "lesson04_davis_pipe_event",
        "Discharge and water level tell different parts of the story",
        "Pipe 67 downstream flow and its upstream node O14-DMH047. Each peak is found separately.",
    )

    fig, axes = plt.subplots(2, 1, figsize=(13, 9))
    for ax, variable in zip(axes, ["boundary_flow_cfs", "boundary_wse_ft"], strict=True):
        for interval in ["1MIN", "1HOUR", "15MIN", "5MIN"]:
            frame = series[interval]
            ax.plot(
                frame.elapsed_hours,
                frame[variable],
                color=COLORS[interval],
                lw=1.7,
                marker="o" if interval == "1HOUR" else None,
                ms=3,
                label=f"{LABELS[interval]}: peak {frame[variable].max():.3f} {VARIABLES[variable][1]}",
            )
        ax.set(xlim=(0, 36), ylabel=Y_LABELS[variable])
        ax.legend(loc="upper right", frameon=False, fontsize=9)
    finish_figure(
        fig,
        output,
        "lesson04_davis_boundary",
        "The same hourly interval captures the broad outlet peak",
        "DS Normal is the external normal-depth boundary of the 2D DS Channel area.",
    )


def report(output: Path) -> None:
    if not output.is_relative_to(REPO / "outputs"):
        raise ValueError("Reports must be under outputs/.")
    experiment = json.loads((output / "experiment.json").read_text())
    source_manifest = json.loads((output / "source_manifest.json").read_text())
    if manifest(SOURCE) != source_manifest:
        raise ValueError("The source has changed since preparation.")
    series, details, paths = {}, {}, {}
    project = Path(experiment["project"])
    for name in ["DavisStormSystem.g02", "DavisStormSystem.u01"]:
        with (project.parent / name).open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != source_manifest[name]:
            raise ValueError(f"Working geometry or flow input differs from the source: {name}")
    for row in experiment["plans"]:
        interval = row["interval"]
        receipt = json.loads((output / f"run_{interval}.json").read_text())
        path = project.with_suffix(f".p{row['plan']}.hdf")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if not receipt["success"] or digest != receipt["result_hdf_sha256"]:
            raise ValueError(f"Run failed or HDF changed after its run receipt: {interval}")
        current = plan_settings(project.with_suffix(f".p{row['plan']}"))
        for key, expected in experiment["fixed_settings"].items():
            if current.get(key) != expected:
                raise ValueError(f"Fixed setting changed: {interval}, {key}")
        if current["Output Interval"] != interval:
            raise ValueError("Plan output interval differs from the experiment manifest.")
        frame, metadata = read_series(path, row["seconds"])
        metadata["hdf_sha256"] = digest
        metadata["duration_seconds"] = receipt["duration_seconds"]
        series[interval], details[interval], paths[interval] = frame, metadata, path
        frame.to_csv(output / f"hydrographs_{interval}.csv", index=False)
        (output / f"compute_messages_{interval}.txt").write_text(
            metadata["compute_messages"], encoding="utf-8"
        )
    peaks = []
    for interval in ORDER:
        frame = series[interval]
        differences = shared_time_differences(series["1MIN"], frame)
        details[interval]["shared_time_max_absolute_differences"] = differences
        with h5py.File(paths["1MIN"], "r") as ref, h5py.File(paths[interval], "r") as other:
            checks = [
                f"{BASE}/2D Flow Areas/{area}/Water Surface" for area in ["area2", "DS Channel"]
            ]
            checks.append(f"{BASE}/Pipe Networks/Davis/Nodes/Water Surface")
            differences, missing_counts = {}, {}
            for path in checks:
                first, second = ref[path][:], other[path][:]
                if first.shape != second.shape or not np.array_equal(
                    np.isnan(first), np.isnan(second)
                ):
                    raise ValueError(f"Mapping shape or missing-value locations differ: {path}")
                if np.isinf(first).any() or np.isinf(second).any():
                    raise ValueError(f"Infinite mapping output: {path}")
                finite = np.isfinite(first)
                differences[path] = float(np.max(np.abs(first[finite] - second[finite])))
                missing_counts[path] = int(np.isnan(first).sum())
            details[interval]["fixed_mapping_array_differences"] = differences
            details[interval]["fixed_mapping_matching_nan_counts"] = missing_counts
        for variable, (label, units) in VARIABLES.items():
            row = frame.loc[frame[variable].idxmax()]
            reference_peak = series["1MIN"][variable].max()
            peaks.append(
                {
                    "interval": interval,
                    "variable": variable,
                    "location": label,
                    "unit": units,
                    "peak": float(row[variable]),
                    "timestamp": str(row.timestamp),
                    "elapsed_hours": row.elapsed_hours,
                    "peak_shortfall": float(reference_peak - row[variable]),
                    "shortfall_percent": float(
                        100 * (reference_peak - row[variable]) / reference_peak
                    )
                    if units == "cfs"
                    else None,
                }
            )
    pd.DataFrame(peaks).to_csv(output / "peak_comparison.csv", index=False)
    save_json(
        output / "verification.json",
        {
            "source_unchanged": True,
            "working_geometry_and_flow_match_source": True,
            "details": details,
            "peaks": peaks,
            "datasets": [
                PIPE_ATTRS,
                NODE_ATTRS,
                f"{DSS}/Time",
                f"{DSS}/Time Date Stamp",
                PIPE_FLOW,
                NODE_WSE,
                BOUNDARY,
            ],
            "reference_definition": "Maximum of the saved 1-minute samples, not an exact computation-step maximum, observed peak, or proof of computational convergence.",
        },
    )
    make_plots(series, output)
    print(pd.DataFrame(peaks).to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    report(parser.parse_args().output.resolve())
