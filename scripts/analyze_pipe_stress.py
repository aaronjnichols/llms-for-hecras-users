"""Create a reviewable pipe surcharge screening table and figure from a RAS HDF.

This example reads an existing HEC-RAS results HDF in read-only mode. It does not
launch HEC-RAS or change the model. The resulting metrics are screening evidence,
not regulatory or design pass/fail criteria.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import h5py
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")

import matplotlib.patheffects as path_effects  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

RESULTS_BASE = "Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series"
CONDUIT_ATTRIBUTES = "Geometry/Pipe Conduits/Attributes"
POLYLINE_INFO = "Geometry/Pipe Conduits/Polyline Info"
POLYLINE_POINTS = "Geometry/Pipe Conduits/Polyline Points"
SURCHARGE_TOLERANCE_FT = 0.01


@dataclass(frozen=True)
class AnalysisContext:
    """Metadata needed to document and plot the analysis."""

    source_hdf: Path
    network_name: str
    ras_version: str
    units_system: str
    start_time: str
    end_time: str


def decode(value: object) -> str:
    """Decode a HEC-RAS byte string without hiding unexpected types."""
    if isinstance(value, bytes | np.bytes_):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


def require_paths(hdf: h5py.File, paths: list[str]) -> None:
    """Fail with all missing HDF paths in one actionable message."""
    missing = [path for path in paths if path not in hdf]
    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise KeyError(f"The HDF is missing required datasets:\n{formatted}")


def duration_hours(mask: np.ndarray, time_days: np.ndarray) -> float:
    """Integrate a sampled Boolean condition over the irregular HDF time axis."""
    if len(mask) < 2:
        return 0.0
    return float(np.trapezoid(mask.astype(float), time_days) * 24.0)


def maximum_absolute_pair(first: np.ndarray, second: np.ndarray) -> float:
    """Return the largest finite absolute value from two endpoint series."""
    combined = np.concatenate((np.ravel(first), np.ravel(second)))
    finite = combined[np.isfinite(combined)]
    if not len(finite):
        return np.nan
    return float(np.max(np.abs(finite)))


def read_pipe_results(
    hdf_path: Path, network_name: str
) -> tuple[pd.DataFrame, list[np.ndarray], AnalysisContext]:
    """Extract per-conduit screening metrics and mapped pipe polylines."""
    network_geometry = f"Geometry/Pipe Networks/{network_name}"
    network_results = f"{RESULTS_BASE}/Pipe Networks/{network_name}"
    required = [
        CONDUIT_ATTRIBUTES,
        POLYLINE_INFO,
        POLYLINE_POINTS,
        f"{network_geometry}/Cells Node and Conduit IDs",
        f"{network_geometry}/Cells Minimum Elevations",
        f"{RESULTS_BASE}/Time",
        f"{RESULTS_BASE}/Time Date Stamp",
        f"{network_results}/Cell Water Surface",
        f"{network_results}/Pipes/Pipe Flow US",
        f"{network_results}/Pipes/Pipe Flow DS",
        f"{network_results}/Pipes/Vel US",
        f"{network_results}/Pipes/Vel DS",
    ]

    with h5py.File(hdf_path, "r") as hdf:
        require_paths(hdf, required)
        attributes = hdf[CONDUIT_ATTRIBUTES][:]
        polyline_info = hdf[POLYLINE_INFO][:]
        polyline_points = hdf[POLYLINE_POINTS][:]
        cell_ids = hdf[f"{network_geometry}/Cells Node and Conduit IDs"][:, 1]
        cell_minimum_elevation_ft = hdf[f"{network_geometry}/Cells Minimum Elevations"][:]
        time_days = hdf[f"{RESULTS_BASE}/Time"][:]
        timestamps = [decode(value) for value in hdf[f"{RESULTS_BASE}/Time Date Stamp"][:]]
        cell_water_surface_ft = hdf[f"{network_results}/Cell Water Surface"][:]
        flow_us_cfs = hdf[f"{network_results}/Pipes/Pipe Flow US"][:]
        flow_ds_cfs = hdf[f"{network_results}/Pipes/Pipe Flow DS"][:]
        velocity_us_fps = hdf[f"{network_results}/Pipes/Vel US"][:]
        velocity_ds_fps = hdf[f"{network_results}/Pipes/Vel DS"][:]

        conduit_count = len(attributes)
        expected_pipe_shape = (len(time_days), conduit_count)
        for name, values in {
            "Pipe Flow US": flow_us_cfs,
            "Pipe Flow DS": flow_ds_cfs,
            "Vel US": velocity_us_fps,
            "Vel DS": velocity_ds_fps,
        }.items():
            if values.shape != expected_pipe_shape:
                raise ValueError(
                    f"{name} has shape {values.shape}; expected {expected_pipe_shape}."
                )
        if cell_water_surface_ft.shape != (len(time_days), len(cell_ids)):
            raise ValueError(
                "Cell Water Surface shape does not match the HDF time and pipe-cell arrays."
            )
        if np.any(np.diff(time_days) < 0):
            raise ValueError("The HDF time coordinate is not monotonically increasing.")

        polylines: list[np.ndarray] = []
        rows: list[dict[str, object]] = []
        for conduit_index, conduit in enumerate(attributes):
            point_start, point_count = map(int, polyline_info[conduit_index, :2])
            polylines.append(polyline_points[point_start : point_start + point_count])

            pipe_cell_indices = np.flatnonzero(cell_ids == conduit_index)
            pipe_rise_ft = float(conduit["Rise"])
            if len(pipe_cell_indices):
                pipe_depth_ft = (
                    cell_water_surface_ft[:, pipe_cell_indices]
                    - cell_minimum_elevation_ft[pipe_cell_indices]
                )
                maximum_depth_by_time_ft = np.nanmax(pipe_depth_ft, axis=1)
                head_above_crown_by_time_ft = maximum_depth_by_time_ft - pipe_rise_ft
                peak_index = int(np.nanargmax(head_above_crown_by_time_ft))
                max_head_above_crown_ft = float(head_above_crown_by_time_ft[peak_index])
                hours_above_crown = duration_hours(
                    head_above_crown_by_time_ft > SURCHARGE_TOLERANCE_FT,
                    time_days,
                )
                peak_time = timestamps[peak_index]
                maximum_depth_ft = float(maximum_depth_by_time_ft[peak_index])
            else:
                max_head_above_crown_ft = np.nan
                hours_above_crown = np.nan
                peak_time = ""
                maximum_depth_ft = np.nan

            peak_flow_cfs = maximum_absolute_pair(
                flow_us_cfs[:, conduit_index],
                flow_ds_cfs[:, conduit_index],
            )
            peak_velocity_fps = maximum_absolute_pair(
                velocity_us_fps[:, conduit_index],
                velocity_ds_fps[:, conduit_index],
            )
            rows.append(
                {
                    "conduit_index": conduit_index,
                    "pipe_id": decode(conduit["Name"]),
                    "upstream_node": decode(conduit["US Node"]),
                    "downstream_node": decode(conduit["DS Node"]),
                    "modeling_approach": decode(conduit["Modeling Approach"]),
                    "shape": decode(conduit["Shape"]),
                    "length_ft": float(conduit["Conduit Length"]),
                    "rise_ft": pipe_rise_ft,
                    "span_ft": float(conduit["Span"]),
                    "manning_n": float(conduit["Manning's n"]),
                    "maximum_hydraulic_depth_ft": maximum_depth_ft,
                    "max_head_above_crown_ft": max_head_above_crown_ft,
                    "hours_above_crown": hours_above_crown,
                    "peak_flow_cfs": peak_flow_cfs,
                    "peak_velocity_fps": peak_velocity_fps,
                    "peak_head_time": peak_time,
                    "has_pipe_cell_results": bool(len(pipe_cell_indices)),
                }
            )

        context = AnalysisContext(
            source_hdf=hdf_path.resolve(),
            network_name=network_name,
            ras_version=decode(hdf.attrs.get("File Version", "not recorded")),
            units_system=decode(hdf.attrs.get("Units System", "not recorded")),
            start_time=timestamps[0],
            end_time=timestamps[-1],
        )

    results = pd.DataFrame(rows)
    results["exceeded_crown"] = results["max_head_above_crown_ft"] > SURCHARGE_TOLERANCE_FT
    return results, polylines, context


def add_scale_and_north_arrow(ax: plt.Axes, polylines: list[np.ndarray]) -> None:
    """Add compact orientation marks using projected model coordinates."""
    points = np.vstack(polylines)
    x_min, y_min = points.min(axis=0)
    x_max, y_max = points.max(axis=0)
    width = x_max - x_min
    height = y_max - y_min

    scale_length_ft = 1_000.0
    scale_x = x_min + 0.05 * width
    scale_y = y_min + 0.045 * height
    ax.plot(
        [scale_x, scale_x + scale_length_ft],
        [scale_y, scale_y],
        color="#263545",
        linewidth=2.5,
        solid_capstyle="butt",
        zorder=6,
    )
    ax.text(
        scale_x + scale_length_ft / 2,
        scale_y + 0.015 * height,
        "1,000 ft",
        ha="center",
        va="bottom",
        fontsize=8.5,
        color="#263545",
    )

    north_x = x_max - 0.05 * width
    north_y = y_max - 0.12 * height
    ax.annotate(
        "N",
        xy=(north_x, north_y + 0.075 * height),
        xytext=(north_x, north_y),
        ha="center",
        va="bottom",
        fontsize=9,
        fontweight="bold",
        color="#263545",
        arrowprops={"arrowstyle": "-|>", "color": "#263545", "lw": 1.3},
    )


def plot_pipe_stress(
    results: pd.DataFrame,
    polylines: list[np.ndarray],
    context: AnalysisContext,
    png_path: Path,
    preview_path: Path,
    svg_path: Path,
) -> None:
    """Render a report-ready network map and ranked pipe review panel."""
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titleweight": "bold",
            "axes.edgecolor": "#ccd4dc",
            "axes.labelcolor": "#263545",
            "xtick.color": "#536271",
            "ytick.color": "#536271",
        }
    )
    figure = plt.figure(figsize=(15.2, 8.6), facecolor="white")
    grid = figure.add_gridspec(
        1,
        2,
        width_ratios=(1.72, 1.0),
        left=0.045,
        right=0.965,
        top=0.80,
        bottom=0.12,
        wspace=0.16,
    )
    map_ax = figure.add_subplot(grid[0, 0])
    bar_ax = figure.add_subplot(grid[0, 1])

    analyzed = results[results["has_pipe_cell_results"]]
    exceeded = analyzed[analyzed["exceeded_crown"]]
    missing_count = int((~results["has_pipe_cell_results"]).sum())
    maximum_head_ft = float(exceeded["max_head_above_crown_ft"].max())
    color_maximum = max(1.0, np.ceil(maximum_head_ft))
    normalizer = Normalize(vmin=0.0, vmax=color_maximum)
    color_map = matplotlib.colormaps["YlOrRd"]

    figure.text(
        0.045,
        0.945,
        "DAVIS STORM SYSTEM",
        fontsize=9.5,
        fontweight="bold",
        color="#c44f22",
        va="top",
    )
    figure.text(
        0.045,
        0.905,
        "Pipe surcharge screening",
        fontsize=23,
        fontweight="bold",
        color="#17283a",
        va="top",
    )
    figure.text(
        0.045,
        0.858,
        "Maximum modeled hydraulic depth above each pipe crown",
        fontsize=11.5,
        color="#536271",
        va="top",
    )
    figure.text(
        0.965,
        0.938,
        f"{context.ras_version}  •  network {context.network_name}\n"
        f"{context.start_time} to {context.end_time}",
        fontsize=8.8,
        color="#536271",
        ha="right",
        va="top",
        linespacing=1.5,
    )

    map_ax.set_facecolor("#f5f7f9")
    base_widths = 0.65 + 0.24 * np.clip(results["rise_ft"].to_numpy(), 0.5, 6.0)
    map_ax.add_collection(
        LineCollection(
            polylines,
            colors="#cbd3da",
            linewidths=base_widths,
            capstyle="round",
            joinstyle="round",
            zorder=1,
        )
    )

    positive_indices = exceeded.index.to_numpy(dtype=int)
    positive_lines = [polylines[index] for index in positive_indices]
    positive_values = exceeded["max_head_above_crown_ft"].to_numpy()
    positive_widths = base_widths[positive_indices]
    surcharge_collection = LineCollection(
        positive_lines,
        cmap=color_map,
        norm=normalizer,
        linewidths=positive_widths,
        capstyle="round",
        joinstyle="round",
        zorder=3,
    )
    surcharge_collection.set_array(positive_values)
    map_ax.add_collection(surcharge_collection)
    map_ax.autoscale()
    map_ax.margins(0.035)
    map_ax.set_aspect("equal", adjustable="box")
    map_ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    for spine in map_ax.spines.values():
        spine.set_visible(False)
    map_ax.set_title("Where surcharge concentrates", loc="left", fontsize=12, pad=12)
    map_ax.text(
        0.0,
        1.005,
        "Line width follows pipe rise; gray pipes did not exceed the crown or lack cell results.",
        transform=map_ax.transAxes,
        fontsize=8.6,
        color="#667584",
        va="bottom",
    )

    top_for_labels = exceeded.nlargest(5, "max_head_above_crown_ft")
    offsets = [(10, 13), (10, -19), (-12, 13), (10, 13), (-12, -20)]
    for (_, pipe), offset in zip(top_for_labels.iterrows(), offsets, strict=True):
        conduit_index = int(pipe["conduit_index"])
        line = polylines[conduit_index]
        midpoint = line[len(line) // 2]
        annotation = map_ax.annotate(
            f"Pipe {pipe['pipe_id']}",
            xy=midpoint,
            xytext=offset,
            textcoords="offset points",
            ha="left" if offset[0] > 0 else "right",
            va="center",
            fontsize=8.4,
            fontweight="bold",
            color="#17283a",
            arrowprops={"arrowstyle": "-", "color": "#7b8793", "lw": 0.7},
            zorder=7,
        )
        annotation.set_path_effects([path_effects.withStroke(linewidth=3.5, foreground="white")])

    add_scale_and_north_arrow(map_ax, polylines)
    colorbar_ax = map_ax.inset_axes([0.53, 0.035, 0.42, 0.025])
    colorbar = figure.colorbar(surcharge_collection, cax=colorbar_ax, orientation="horizontal")
    colorbar.set_label("Maximum head above crown (ft)", fontsize=8.5, labelpad=4)
    colorbar.ax.tick_params(labelsize=8, length=2)
    colorbar.outline.set_visible(False)

    top_ten = exceeded.nlargest(10, "max_head_above_crown_ft").sort_values(
        "max_head_above_crown_ft"
    )
    y_positions = np.arange(len(top_ten))
    bar_values = top_ten["max_head_above_crown_ft"].to_numpy()
    bar_colors = color_map(normalizer(bar_values))
    bars = bar_ax.barh(y_positions, bar_values, color=bar_colors, height=0.62)
    labels = [
        f"Pipe {pipe_id}   {rise_ft * 12:.0f} in"
        for pipe_id, rise_ft in zip(top_ten["pipe_id"], top_ten["rise_ft"], strict=True)
    ]
    bar_ax.set_yticks(y_positions, labels)
    bar_ax.set_xlim(0, color_maximum * 1.33)
    bar_ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    bar_ax.set_xlabel("Maximum head above crown (ft)", labelpad=9)
    bar_ax.set_title("Highest-priority pipe review", loc="left", fontsize=12, pad=12)
    bar_ax.text(
        0.0,
        1.005,
        "Ranked by maximum head; duration and peak hydraulics shown at right.",
        transform=bar_ax.transAxes,
        fontsize=8.6,
        color="#667584",
        va="bottom",
    )
    bar_ax.grid(axis="x", color="#e1e6ea", linewidth=0.8)
    bar_ax.set_axisbelow(True)
    bar_ax.spines[["top", "right", "left"]].set_visible(False)
    bar_ax.tick_params(axis="y", length=0, labelsize=9)
    bar_ax.tick_params(axis="x", labelsize=8.5)

    for bar, (_, pipe) in zip(bars, top_ten.iterrows(), strict=True):
        value = float(pipe["max_head_above_crown_ft"])
        y_center = bar.get_y() + bar.get_height() / 2
        bar_ax.text(
            value + color_maximum * 0.018,
            y_center + 0.12,
            f"+{value:.1f} ft",
            va="center",
            ha="left",
            fontsize=9,
            fontweight="bold",
            color="#17283a",
        )
        bar_ax.text(
            value + color_maximum * 0.018,
            y_center - 0.15,
            f"{pipe['hours_above_crown']:.1f} h  •  "
            f"{pipe['peak_flow_cfs']:.1f} cfs  •  {pipe['peak_velocity_fps']:.1f} fps",
            va="center",
            ha="left",
            fontsize=7.6,
            color="#667584",
        )

    figure.text(
        0.045,
        0.065,
        f"{len(exceeded)} of {len(analyzed)} conduits exceeded the crown by more than "
        f"{SURCHARGE_TOLERANCE_FT:.2f} ft; {missing_count} conduits had no resolved pipe-cell results.",
        fontsize=9.2,
        color="#263545",
        va="bottom",
    )
    figure.text(
        0.045,
        0.032,
        "SCREENING ONLY  •  Positive values indicate modeled water depth above the crown somewhere "
        "along the conduit. No agency, capacity, or design criterion has been applied.",
        fontsize=8.2,
        color="#667584",
        va="bottom",
    )

    figure.savefig(png_path, dpi=240, facecolor="white", bbox_inches="tight")
    figure.savefig(preview_path, dpi=110, facecolor="white", bbox_inches="tight")
    figure.savefig(svg_path, facecolor="white", bbox_inches="tight")
    plt.close(figure)


def write_summary(
    output_path: Path,
    results: pd.DataFrame,
    context: AnalysisContext,
) -> None:
    """Write method, provenance, and limitations beside the generated outputs."""
    analyzed = results[results["has_pipe_cell_results"]]
    exceeded = analyzed[analyzed["exceeded_crown"]]
    missing = results[~results["has_pipe_cell_results"]]
    top_ten = exceeded.nlargest(10, "max_head_above_crown_ft")
    table_rows = []
    for _, pipe in top_ten.iterrows():
        table_rows.append(
            "| {pipe_id} | {route} | {head:.2f} | {hours:.2f} | {flow:.2f} | {velocity:.2f} |".format(
                pipe_id=pipe["pipe_id"],
                route=f"{pipe['upstream_node']} → {pipe['downstream_node']}",
                head=pipe["max_head_above_crown_ft"],
                hours=pipe["hours_above_crown"],
                flow=pipe["peak_flow_cfs"],
                velocity=pipe["peak_velocity_fps"],
            )
        )

    missing_ids = ", ".join(missing["pipe_id"].astype(str)) or "none"
    text = f"""# Davis storm-system pipe surcharge screen

## Result

- {len(exceeded)} of {len(analyzed)} conduits with resolved pipe cells exceeded the crown by more than {SURCHARGE_TOLERANCE_FT:.2f} ft at least once.
- {len(missing)} conduits had no resolved pipe-cell results: {missing_ids}.
- This is a hydraulic screening result, not a design-code or regulatory pass/fail determination.

| Pipe | Route | Max head above crown (ft) | Hours above crown | Peak flow (cfs) | Peak velocity (fps) |
|---|---|---:|---:|---:|---:|
{chr(10).join(table_rows)}

## Method

For each conduit, HEC-RAS pipe-network cells were matched using conduit index. At every output time, hydraulic depth was calculated as `Cell Water Surface - Cells Minimum Elevations`; the maximum value along the conduit was compared with the conduit `Rise`. Positive `max_head_above_crown_ft` therefore means the modeled hydraulic grade exceeded the pipe crown somewhere along that conduit. Duration was calculated by trapezoidal integration of the sampled above-crown condition over the HDF time coordinate. Peak flow and velocity are the maximum absolute upstream or downstream pipe values.

## Provenance

- Results HDF (read-only): `{context.source_hdf}`
- HEC-RAS file version: `{context.ras_version}`
- Unit system: `{context.units_system}`
- Pipe network: `{context.network_name}`
- Simulation output period: `{context.start_time}` to `{context.end_time}`
- Pipe attributes: `{CONDUIT_ATTRIBUTES}`
- Pipe-cell mapping: `Geometry/Pipe Networks/{context.network_name}/Cells Node and Conduit IDs`
- Pipe-cell invert proxy: `Geometry/Pipe Networks/{context.network_name}/Cells Minimum Elevations`
- Cell water surface: `{RESULTS_BASE}/Pipe Networks/{context.network_name}/Cell Water Surface`
- Pipe flow and velocity: `{RESULTS_BASE}/Pipe Networks/{context.network_name}/Pipes/*`

## Limitations

- The screen identifies modeled hydraulic depth above the crown; it does not by itself prove structural surcharge, inlet flooding, manhole overflow, capacity noncompliance, or damage.
- Results depend on this plan's geometry, boundary conditions, rainfall/runoff inputs, numerical settings, and output interval.
- Conduits without resolved pipe cells remain in the CSV with `has_pipe_cell_results = False` and no calculated crown metric.
- Engineering review should inspect the controlling nodes, profile behavior, model diagnostics, and applicable local criteria before recommending changes.
"""
    output_path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    """Parse explicit source and destination paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_hdf", type=Path, help="Existing HEC-RAS plan HDF to read")
    parser.add_argument("--network", default="Davis", help="Pipe-network name in the HDF")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/davis_pipe_stress"),
        help="Directory for the CSV, figure, and summary",
    )
    return parser.parse_args()


def main() -> int:
    """Run the read-only analysis and write reproducible outputs."""
    args = parse_args()
    hdf_path = args.plan_hdf.resolve()
    if not hdf_path.is_file():
        raise FileNotFoundError(f"HEC-RAS plan HDF not found: {hdf_path}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results, polylines, context = read_pipe_results(hdf_path, args.network)
    csv_path = output_dir / "pipe_stress_screen.csv"
    png_path = output_dir / "pipe_stress_screen.png"
    preview_path = output_dir / "pipe_stress_preview.png"
    svg_path = output_dir / "pipe_stress_screen.svg"
    summary_path = output_dir / "README.md"
    results.sort_values("max_head_above_crown_ft", ascending=False, na_position="last").to_csv(
        csv_path, index=False, float_format="%.6f"
    )
    plot_pipe_stress(results, polylines, context, png_path, preview_path, svg_path)
    write_summary(summary_path, results, context)

    print(f"Analyzed {len(results)} conduits from {hdf_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {png_path}")
    print(f"Wrote {preview_path}")
    print(f"Wrote {svg_path}")
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
