"""Create paginated Beaver Creek cross-section result plots.

The script reads existing steady-flow plan HDF files with RAS Commander. It
does not run HEC-RAS or change model files. Each PDF page is US Letter portrait
with four cross sections arranged in two rows and two columns.
"""

from __future__ import annotations

import argparse
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import matplotlib
import numpy as np
import pandas as pd
from ras_commander import HdfResultsPlan, HdfXsec

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

DEFAULT_PROFILE = "May '74 flood"
PLOTS_PER_PAGE = 4


@dataclass(frozen=True)
class PlanMetadata:
    """Identifiers and provenance carried into the plotted PDF."""

    title: str
    short_id: str
    plan_file: str
    geometry_file: str
    hdf_version: str
    units_system: str
    sha256: str


def decode_hdf_text(value: Any) -> str:
    """Convert an HDF attribute value to plain text."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a source file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_plan_metadata(plan_hdf: Path) -> PlanMetadata:
    """Read the adjacent plan text file and read-only HDF attributes."""
    plan_file = plan_hdf.with_suffix("")
    fields: dict[str, str] = {}
    if plan_file.is_file():
        for line in plan_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key in {"Plan Title", "Short Identifier", "Geom File"}:
                fields[key] = value.strip()

    with h5py.File(plan_hdf, "r") as hdf:
        version = decode_hdf_text(hdf.attrs.get("File Version", "not recorded"))
        units = decode_hdf_text(hdf.attrs.get("Units System", "not recorded"))

    return PlanMetadata(
        title=fields.get("Plan Title", plan_file.name),
        short_id=fields.get("Short Identifier", plan_file.name),
        plan_file=plan_file.name,
        geometry_file=fields.get("Geom File", "not recorded"),
        hdf_version=version,
        units_system=units,
        sha256=sha256_file(plan_hdf),
    )


def normalize_text(values: pd.Series) -> pd.Series:
    """Normalize HEC-RAS fixed-width text for joins."""
    return values.astype(str).str.strip()


def extract_energy_grades(plan_hdf: Path, profile_name: str) -> pd.DataFrame:
    """Read the steady Energy Grade matrix when RAS Commander leaves it empty."""
    results_root = "Results/Steady/Output/Output Blocks/Base Output/Steady Profiles"
    with h5py.File(plan_hdf, "r") as hdf:
        profile_names = [
            decode_hdf_text(value).strip() for value in hdf[f"{results_root}/Profile Names"][:]
        ]
        try:
            profile_index = profile_names.index(profile_name)
        except ValueError as exc:
            available = ", ".join(profile_names)
            raise ValueError(
                f"Profile {profile_name!r} was not found in {plan_hdf}. "
                f"Available profiles: {available}"
            ) from exc

        attributes = hdf["Results/Steady/Output/Geometry Info/Cross Section Attributes"][:]
        energy_grade = hdf[f"{results_root}/Cross Sections/Energy Grade"][profile_index]

    return pd.DataFrame(
        {
            "River": [decode_hdf_text(row["River"]).strip() for row in attributes],
            "Reach": [decode_hdf_text(row["Reach"]).strip() for row in attributes],
            "RS": [decode_hdf_text(row["Station"]).strip() for row in attributes],
            "energy_hdf": np.asarray(energy_grade, dtype=float),
        }
    )


def extract_plot_data(plan_hdf: Path, profile_name: str) -> pd.DataFrame:
    """Join cross-section geometry and roughness to one steady profile."""
    cross_sections = HdfXsec.get_cross_sections(str(plan_hdf))
    if cross_sections.empty:
        raise ValueError(f"No cross sections were found in {plan_hdf}")

    all_results = HdfResultsPlan.get_steady_results(str(plan_hdf))
    profile_results = all_results.loc[all_results["profile"] == profile_name].copy()
    if profile_results.empty:
        profiles = ", ".join(sorted(all_results["profile"].astype(str).unique()))
        raise ValueError(
            f"Profile {profile_name!r} was not found in {plan_hdf}. Available profiles: {profiles}"
        )

    cross_sections = cross_sections.copy()
    profile_results = profile_results.rename(
        columns={"river": "River", "reach": "Reach", "node_id": "RS"}
    )
    for column in ("River", "Reach", "RS"):
        cross_sections[column] = normalize_text(cross_sections[column])
        profile_results[column] = normalize_text(profile_results[column])

    result_columns = ["River", "Reach", "RS", "profile", "wsel", "energy", "flow", "velocity"]
    joined = cross_sections.merge(
        profile_results[result_columns],
        on=["River", "Reach", "RS"],
        how="left",
        validate="one_to_one",
    )
    missing = joined.loc[joined["wsel"].isna(), "RS"].tolist()
    if missing:
        raise ValueError(f"Results did not join to cross sections: {missing}")

    energy_grades = extract_energy_grades(plan_hdf, profile_name)
    joined = joined.merge(
        energy_grades,
        on=["River", "Reach", "RS"],
        how="left",
        validate="one_to_one",
    )
    joined["energy"] = joined["energy"].fillna(joined["energy_hdf"])
    if joined["energy"].isna().any():
        missing_energy = joined.loc[joined["energy"].isna(), "RS"].tolist()
        raise ValueError(f"Energy-grade results are missing at cross sections: {missing_energy}")
    joined = joined.drop(columns="energy_hdf")

    joined["river_station_number"] = pd.to_numeric(
        joined["RS"].str.replace("*", "", regex=False), errors="raise"
    )
    return joined.sort_values("river_station_number", ascending=False).reset_index(drop=True)


def roughness_regions(
    mannings_n: dict[str, list[float]], minimum_station: float, maximum_station: float
) -> list[tuple[float, float, float]]:
    """Convert HEC-RAS roughness change stations to labeled plot regions."""
    starts = np.asarray(mannings_n["Station"], dtype=float)
    values = np.asarray(mannings_n["Mann n"], dtype=float)
    if starts.size == 0 or starts.size != values.size:
        raise ValueError("Manning's n stations and values are missing or inconsistent")

    order = np.argsort(starts)
    starts = starts[order]
    values = values[order]
    if starts[0] > minimum_station:
        starts = np.insert(starts, 0, minimum_station)
        values = np.insert(values, 0, values[0])

    regions: list[tuple[float, float, float]] = []
    for index, (start, value) in enumerate(zip(starts, values, strict=True)):
        end = starts[index + 1] if index + 1 < starts.size else maximum_station
        clipped_start = max(float(start), minimum_station)
        clipped_end = min(float(end), maximum_station)
        if clipped_end > clipped_start:
            regions.append((clipped_start, clipped_end, float(value)))
    return regions


def plot_one_cross_section(ax: plt.Axes, row: pd.Series) -> None:
    """Plot one cross-section profile with results, banks, and n-value labels."""
    profile = np.asarray(row["station_elevation"], dtype=float)
    stations = profile[:, 0]
    elevations = profile[:, 1]
    order = np.argsort(stations, kind="stable")
    stations = stations[order]
    elevations = elevations[order]

    minimum_station = float(stations.min())
    maximum_station = float(stations.max())
    station_span = maximum_station - minimum_station
    water_surface = float(row["wsel"])
    energy_grade = float(row["energy"])

    dense_stations = np.linspace(minimum_station, maximum_station, 1200)
    dense_elevations = np.interp(dense_stations, stations, elevations)
    wet = dense_elevations <= water_surface
    if wet.any():
        wet_stations = dense_stations[wet]
        water_left = float(wet_stations[0])
        water_right = float(wet_stations[-1])
        ax.fill_between(
            dense_stations,
            dense_elevations,
            water_surface,
            where=wet,
            interpolate=True,
            color="#7cc8e8",
            alpha=0.42,
            linewidth=0,
            zorder=1,
        )
        ax.hlines(
            water_surface,
            water_left,
            water_right,
            color="#087eaa",
            linewidth=1.7,
            zorder=4,
        )
        ax.hlines(
            energy_grade,
            water_left,
            water_right,
            color="#d36b21",
            linewidth=1.25,
            linestyle="--",
            zorder=4,
        )

    ground_floor = float(elevations.min() - max(1.0, np.ptp(elevations) * 0.12))
    ax.fill_between(stations, ground_floor, elevations, color="#d6d0c4", alpha=0.68, zorder=2)
    ax.plot(stations, elevations, color="#282b2f", linewidth=1.35, zorder=5)

    left_bank = float(row["Left Bank"])
    right_bank = float(row["Right Bank"])
    for station, label, x_offset, alignment in (
        (left_bank, "LB", -5, "right"),
        (right_bank, "RB", 5, "left"),
    ):
        bank_elevation = float(np.interp(station, stations, elevations))
        ax.plot(
            station,
            bank_elevation,
            marker="v",
            markersize=5.5,
            color="#744c9e",
            markeredgecolor="white",
            markeredgewidth=0.5,
            zorder=7,
        )
        ax.annotate(
            label,
            xy=(station, bank_elevation),
            xytext=(x_offset, 7),
            textcoords="offset points",
            ha=alignment,
            va="bottom",
            fontsize=6.5,
            fontweight="bold",
            color="#5d397e",
            zorder=8,
        )

    colors = ("#e8f1ed", "#f4eadf")
    regions = roughness_regions(row["mannings_n"], minimum_station, maximum_station)
    for index, (start, end, n_value) in enumerate(regions):
        rectangle = Rectangle(
            (start, 0.925),
            end - start,
            0.075,
            transform=ax.get_xaxis_transform(),
            facecolor=colors[index % len(colors)],
            edgecolor="#a7acae",
            linewidth=0.35,
            clip_on=False,
            zorder=0,
        )
        ax.add_patch(rectangle)
        region_fraction = (end - start) / station_span
        rotation = 90 if region_fraction < 0.055 else 0
        ax.text(
            (start + end) / 2,
            0.963,
            f"n={n_value:.3f}",
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="center",
            fontsize=5.5 if rotation else 6.25,
            rotation=rotation,
            color="#384045",
            clip_on=False,
            zorder=6,
        )
        if start > minimum_station:
            ax.axvline(start, color="#8d9498", linewidth=0.45, linestyle=":", zorder=0)

    plotted_maximum = max(float(elevations.max()), water_surface, energy_grade)
    y_span = plotted_maximum - ground_floor
    ax.set_xlim(minimum_station, maximum_station)
    ax.set_ylim(ground_floor, plotted_maximum + max(0.8, y_span * 0.10))
    ax.grid(axis="y", color="#d7dadd", linewidth=0.55)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#8a9094")
    ax.tick_params(axis="both", labelsize=7, colors="#40464a", length=3)
    ax.set_xlabel("Cross-section station (ft)", fontsize=7.5)
    ax.set_ylabel("Elevation (ft)", fontsize=7.5)

    interpolation_note = "  interpolated" if "*" in str(row["RS"]) else ""
    ax.set_title(
        f"RS {row['RS']}{interpolation_note}",
        loc="left",
        fontsize=9,
        fontweight="bold",
        color="#17324d",
        pad=6,
    )
    ax.text(
        0.985,
        0.91,
        (
            f"Q {float(row['flow']):,.0f} cfs   "
            f"WSE {water_surface:.2f} ft   EG {energy_grade:.2f} ft"
        ),
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=6.5,
        color="#4c555b",
        bbox={"boxstyle": "square,pad=0.18", "fc": "white", "ec": "none", "alpha": 0.82},
        zorder=9,
    )


def write_plan_pdf(
    plan_hdf: Path,
    output_pdf: Path,
    profile_name: str = DEFAULT_PROFILE,
) -> int:
    """Write all cross-section pages for one HEC-RAS plan."""
    metadata = read_plan_metadata(plan_hdf)
    cross_sections = extract_plot_data(plan_hdf, profile_name)
    page_count = math.ceil(len(cross_sections) / PLOTS_PER_PAGE)

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8,
            "axes.titleweight": "bold",
        }
    )
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf_metadata = {
        "Title": f"Beaver Creek {profile_name} cross sections - {metadata.title}",
        "Author": "Programmatic export from HEC-RAS results",
        "Subject": (
            f"Read-only source {plan_hdf.resolve()}; SHA-256 {metadata.sha256}; "
            f"profile {profile_name}"
        ),
        "Keywords": "HEC-RAS, Beaver Creek, cross sections, Manning's n",
    }

    legend_handles = [
        Line2D([0], [0], color="#282b2f", lw=1.35, label="Ground"),
        Line2D([0], [0], color="#087eaa", lw=1.7, label="Water surface"),
        Line2D([0], [0], color="#d36b21", lw=1.25, ls="--", label="Energy grade"),
        Line2D(
            [0],
            [0],
            marker="v",
            color="none",
            markerfacecolor="#744c9e",
            markeredgecolor="white",
            markersize=6,
            label="Bank stations",
        ),
        Patch(facecolor="#e8f1ed", edgecolor="#a7acae", label="Manning's n region"),
    ]

    with PdfPages(output_pdf, metadata=pdf_metadata) as pdf:
        for page_index in range(page_count):
            figure, axes = plt.subplots(2, 2, figsize=(8.5, 11), facecolor="white")
            figure.subplots_adjust(
                left=0.085,
                right=0.965,
                top=0.865,
                bottom=0.075,
                hspace=0.31,
                wspace=0.22,
            )
            first = page_index * PLOTS_PER_PAGE
            page_rows = cross_sections.iloc[first : first + PLOTS_PER_PAGE]
            for ax, (_, row) in zip(axes.flat, page_rows.iterrows(), strict=False):
                plot_one_cross_section(ax, row)
            for ax in axes.flat[len(page_rows) :]:
                ax.axis("off")

            figure.text(
                0.085,
                0.958,
                "BEAVER CREEK - KENTWOOD REACH",
                fontsize=8.5,
                fontweight="bold",
                color="#087eaa",
                va="top",
            )
            figure.text(
                0.085,
                0.925,
                f"{profile_name} cross-section results",
                fontsize=17,
                fontweight="bold",
                color="#17324d",
                va="top",
            )
            figure.text(
                0.085,
                0.892,
                (
                    f"{metadata.title} | {metadata.plan_file} | "
                    f"geometry {metadata.geometry_file} | {metadata.units_system}"
                ),
                fontsize=8,
                color="#515c63",
                va="top",
            )
            figure.legend(
                handles=legend_handles,
                loc="upper right",
                bbox_to_anchor=(0.965, 0.962),
                ncol=2,
                frameon=False,
                fontsize=7,
                columnspacing=1.2,
                handlelength=2.1,
            )
            figure.text(
                0.085,
                0.027,
                (
                    f"Existing computed HDF, read only | {metadata.hdf_version} | "
                    f"SHA-256 {metadata.sha256[:16]}..."
                ),
                fontsize=6.6,
                color="#687178",
                va="bottom",
            )
            figure.text(
                0.965,
                0.027,
                f"Page {page_index + 1} of {page_count}",
                fontsize=6.6,
                color="#687178",
                ha="right",
                va="bottom",
            )
            pdf.savefig(figure)
            plt.close(figure)

    return page_count


def output_name(plan_hdf: Path) -> str:
    """Build a stable output name from a plan HDF filename."""
    plan_id = plan_hdf.with_suffix("").suffix.removeprefix(".").lower()
    return f"beaver_creek_may74_{plan_id}_cross_sections.pdf"


def parse_args() -> argparse.Namespace:
    """Parse explicit plan HDF inputs and output location."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "plan_hdfs",
        nargs="+",
        type=Path,
        help="Existing computed Beaver Creek plan HDF files",
    )
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Exact steady profile name")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/beaver_creek_may74_xs_plots"),
    )
    return parser.parse_args()


def main() -> int:
    """Render one paginated cross-section PDF for each supplied plan."""
    args = parse_args()
    output_dir = args.output_dir.resolve()
    for raw_path in args.plan_hdfs:
        plan_hdf = raw_path.resolve()
        if not plan_hdf.is_file():
            raise FileNotFoundError(f"Plan HDF not found: {plan_hdf}")
        output_pdf = output_dir / output_name(plan_hdf)
        page_count = write_plan_pdf(plan_hdf, output_pdf, args.profile)
        print(f"Wrote {output_pdf} ({page_count} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
