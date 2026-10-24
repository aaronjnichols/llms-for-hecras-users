"""Export Beaver Creek steady-profile cross-section results and a spatial figure.

The script uses RAS Commander to read an existing plan HDF. It does not launch a
HEC-RAS computation or modify the model. Cross-section coordinates are preserved
as stored; no coordinate reference system is invented when the HDF has none.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
from ras_commander import HdfResultsPlan, HdfXsec

matplotlib.use("Agg")

import matplotlib.patheffects as path_effects  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402

PROFILE_NAME = "May '74 flood"
GRAVITY_FTPS2 = 32.2


def normalize_text(values: pd.Series) -> pd.Series:
    """Normalize HEC-RAS fixed-width strings for reliable joins."""
    return values.astype(str).str.strip()


def extract_cross_sections(
    plan_hdf: Path, profile_name: str
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, str, str]:
    """Join steady results to cross-section cut lines using RAS Commander."""
    all_results = HdfResultsPlan.get_steady_results(plan_hdf)
    profile_results = all_results.loc[all_results["profile"] == profile_name].copy()
    if profile_results.empty:
        available = ", ".join(sorted(all_results["profile"].unique()))
        raise ValueError(f"Profile {profile_name!r} was not found. Available profiles: {available}")

    # HEC-RAS 7.0.1 does not write Froude # Channel into this plan HDF.
    # Use the standard open-channel definition with the matching channel
    # velocity and hydraulic depth supplied by RAS Commander.
    computed_froude = profile_results["velocity"] / np.sqrt(
        GRAVITY_FTPS2 * profile_results["max_depth"]
    )
    profile_results["froude_no"] = profile_results["froude"].fillna(computed_froude)

    cross_sections = HdfXsec.get_cross_sections(plan_hdf)
    if cross_sections.empty:
        raise ValueError(f"No cross-section cut lines were found in {plan_hdf}")
    centerlines = HdfXsec.get_river_centerlines(plan_hdf)

    results_for_join = profile_results.rename(
        columns={"river": "River", "reach": "Reach", "node_id": "RS"}
    )
    for column in ("River", "Reach", "RS"):
        cross_sections[column] = normalize_text(cross_sections[column])
        results_for_join[column] = normalize_text(results_for_join[column])

    joined = cross_sections[["River", "Reach", "RS", "geometry"]].merge(
        results_for_join[["River", "Reach", "RS", "profile", "wsel", "velocity", "froude_no"]],
        on=["River", "Reach", "RS"],
        how="left",
        validate="one_to_one",
    )
    if joined[["wsel", "velocity", "froude_no"]].isna().any().any():
        missing = joined.loc[joined["wsel"].isna(), "RS"].tolist()
        raise ValueError(f"Results did not join to cross sections: {missing}")

    output = gpd.GeoDataFrame(
        {
            "river": joined["River"],
            "reach": joined["Reach"],
            "xs_station": joined["RS"],
            "profile": joined["profile"],
            "wse_ft": joined["wsel"],
            "vel_fps": joined["velocity"],
            "froude_no": joined["froude_no"],
            "geometry": joined["geometry"],
        },
        geometry="geometry",
        crs=cross_sections.crs,
    )
    ras_version = "not recorded"
    units_system = "not recorded"
    import h5py

    with h5py.File(plan_hdf, "r") as hdf:
        raw_version = hdf.attrs.get("File Version", b"not recorded")
        raw_units = hdf.attrs.get("Units System", b"not recorded")
        ras_version = (
            raw_version.decode("utf-8") if isinstance(raw_version, bytes) else str(raw_version)
        )
        units_system = raw_units.decode("utf-8") if isinstance(raw_units, bytes) else str(raw_units)
    return output, centerlines, ras_version, units_system


def write_shapefile_bundle(cross_sections: gpd.GeoDataFrame, output_dir: Path) -> Path:
    """Write an ESRI Shapefile and zip every required sidecar together."""
    shapefile_path = output_dir / "beaver_creek_may74_xs.shp"
    cross_sections.to_file(shapefile_path, driver="ESRI Shapefile", index=False)

    zip_path = output_dir / "beaver_creek_may74_xs_shapefile.zip"
    sidecars = [
        shapefile_path.with_suffix(extension)
        for extension in (".shp", ".shx", ".dbf", ".cpg", ".prj")
        if shapefile_path.with_suffix(extension).exists()
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sidecars:
            archive.write(path, arcname=path.name)
    return zip_path


def plot_cross_sections(
    cross_sections: gpd.GeoDataFrame,
    centerlines: gpd.GeoDataFrame,
    ras_version: str,
    png_path: Path,
    preview_path: Path,
    svg_path: Path,
) -> None:
    """Create a report-ready schematic map colored by water-surface elevation."""
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titleweight": "bold",
        }
    )
    figure, ax = plt.subplots(figsize=(11.6, 8.2), facecolor="white")
    figure.subplots_adjust(left=0.055, right=0.95, top=0.80, bottom=0.16)
    ax.set_facecolor("#f5f7f9")

    wse_values = cross_sections["wse_ft"].to_numpy()
    normalizer = Normalize(vmin=float(wse_values.min()), vmax=float(wse_values.max()))
    color_map = matplotlib.colormaps["viridis"]
    segments = [np.asarray(geometry.coords) for geometry in cross_sections.geometry]
    collection = LineCollection(
        segments,
        cmap=color_map,
        norm=normalizer,
        linewidths=3.0,
        capstyle="round",
        zorder=3,
    )
    collection.set_array(wse_values)
    ax.add_collection(collection)

    if not centerlines.empty:
        for geometry in centerlines.geometry:
            x_coords, y_coords = geometry.xy
            ax.plot(
                x_coords,
                y_coords,
                color="#1e5a78",
                linewidth=3.6,
                path_effects=[path_effects.withStroke(linewidth=5.8, foreground="white")],
                zorder=5,
            )
            midpoint = geometry.interpolate(0.53, normalized=True)
            downstream = geometry.interpolate(0.66, normalized=True)
            ax.annotate(
                "FLOW",
                xy=(downstream.x, downstream.y),
                xytext=(midpoint.x, midpoint.y),
                ha="center",
                va="center",
                fontsize=8,
                fontweight="bold",
                color="#1e5a78",
                arrowprops={"arrowstyle": "-|>", "lw": 1.5, "color": "#1e5a78"},
                zorder=7,
            )

    label_x = max(geometry.bounds[2] for geometry in cross_sections.geometry) + 0.10
    label_y_values = np.linspace(
        max(geometry.coords[0][1] for geometry in cross_sections.geometry),
        min(geometry.coords[0][1] for geometry in cross_sections.geometry),
        len(cross_sections),
    )
    for row, label_y in zip(cross_sections.itertuples(index=False), label_y_values, strict=True):
        anchor = tuple(row.geometry.coords[0])
        annotation = ax.annotate(
            f"{row.xs_station}  •  {row.wse_ft:.2f} ft",
            xy=anchor,
            xytext=(label_x, label_y),
            textcoords="data",
            ha="left",
            va="center",
            fontsize=8.6,
            fontweight="bold",
            color="#182a3b",
            arrowprops={"arrowstyle": "-", "color": "#a4afb8", "lw": 0.7},
            zorder=8,
        )
        annotation.set_path_effects([path_effects.withStroke(linewidth=3.5, foreground="white")])

    ax.autoscale()
    bounds = cross_sections.total_bounds
    ax.set_xlim(bounds[0] - 0.055, label_x + 0.34)
    ax.set_ylim(bounds[1] - 0.05, bounds[3] + 0.055)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    figure.text(
        0.055,
        0.94,
        "BEAVER CREEK • KENTWOOD REACH",
        fontsize=9.5,
        fontweight="bold",
        color="#147b86",
        va="top",
    )
    figure.text(
        0.055,
        0.895,
        "May '74 flood cross-section results",
        fontsize=22,
        fontweight="bold",
        color="#182a3b",
        va="top",
    )
    figure.text(
        0.055,
        0.848,
        "Cross-section station and maximum water-surface elevation",
        fontsize=11,
        color="#5d6c7a",
        va="top",
    )
    figure.text(
        0.91,
        0.93,
        f"{ras_version}\nPlan p01 • 14 cross sections",
        fontsize=8.6,
        color="#5d6c7a",
        ha="right",
        va="top",
        linespacing=1.5,
    )

    colorbar_ax = figure.add_axes([0.28, 0.092, 0.44, 0.022])
    colorbar = figure.colorbar(collection, cax=colorbar_ax, orientation="horizontal")
    colorbar.set_label("Maximum water-surface elevation (ft)", fontsize=8.5, labelpad=4)
    colorbar.ax.tick_params(labelsize=8, length=2)
    colorbar.outline.set_visible(False)
    figure.text(
        0.055,
        0.024,
        "SCHEMATIC MODEL COORDINATES • The HEC-RAS project does not define a CRS; no projection was assigned.",
        fontsize=8,
        color="#6a7885",
        va="bottom",
    )

    figure.savefig(png_path, dpi=240, facecolor="white", bbox_inches="tight")
    figure.savefig(preview_path, dpi=120, facecolor="white", bbox_inches="tight")
    figure.savefig(svg_path, facecolor="white", bbox_inches="tight")
    plt.close(figure)


def write_readme(
    path: Path,
    plan_hdf: Path,
    ras_version: str,
    units_system: str,
    cross_sections: gpd.GeoDataFrame,
) -> None:
    """Record provenance, definitions, and the undefined-CRS limitation."""
    text = f"""# Beaver Creek May '74 flood cross sections

## Contents

- `beaver_creek_may74_xs.csv`: requested cross-section result table.
- `beaver_creek_may74_xs.shp` and sidecars: cross-section cut lines with results.
- `beaver_creek_may74_xs_shapefile.zip`: complete shapefile bundle.
- `beaver_creek_may74_xs_map.png`: report-resolution spatial figure.
- `beaver_creek_may74_xs_map.svg`: editable vector figure.

## Result definitions

- `xs_station`: HEC-RAS river station, including `*` on interpolated sections.
- `wse_ft`: steady-profile water-surface elevation from the HDF `Water Surface` dataset.
- `vel_fps`: channel velocity from the HDF `Velocity Channel` dataset.
- `froude_no`: channel Froude number. This plan HDF does not contain `Froude # Channel`, so it was calculated as `vel_fps / sqrt(32.2 ft/s^2 * channel hydraulic depth)` using RAS Commander's `velocity` and `max_depth` fields.

## Provenance

- Results HDF, opened read-only: `{plan_hdf.resolve()}`
- HEC-RAS file version: `{ras_version}`
- Unit system: `{units_system}`
- Profile: `{PROFILE_NAME}`
- Feature count: {len(cross_sections)} cross sections
- Results reader: RAS Commander `HdfResultsPlan.get_steady_results()`
- Geometry reader: RAS Commander `HdfXsec.get_cross_sections()`
- Results path: `Results/Steady/Output/Output Blocks/Base Output/Steady Profiles/Cross Sections`
- Geometry path: `Geometry/Cross Sections`

## Spatial-reference limitation

The HEC-RAS project has no projection assigned. Coordinates are the model's schematic coordinates, and the shapefile intentionally has no `.prj` file. Do not overlay it with real-world GIS layers until the correct project CRS and transformation are supplied by the model owner.
"""
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    """Parse explicit source and output locations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_hdf", type=Path, help="Computed Beaver Creek plan HDF")
    parser.add_argument("--profile", default=PROFILE_NAME, help="Exact steady profile name")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/beaver_creek_may74_cross_sections"),
    )
    return parser.parse_args()


def main() -> int:
    """Extract the profile, write the shapefile bundle, and render the map."""
    args = parse_args()
    plan_hdf = args.plan_hdf.resolve()
    if not plan_hdf.is_file():
        raise FileNotFoundError(f"Plan HDF not found: {plan_hdf}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    cross_sections, centerlines, ras_version, units_system = extract_cross_sections(
        plan_hdf, args.profile
    )

    table = cross_sections.drop(columns="geometry").rename(
        columns={
            "xs_station": "cross_section_station",
            "profile": "profile_name",
            "wse_ft": "water_surface_elevation_ft",
            "vel_fps": "channel_velocity_fps",
            "froude_no": "froude_number",
        }
    )
    csv_path = output_dir / "beaver_creek_may74_xs.csv"
    table.to_csv(csv_path, index=False, float_format="%.6f")
    zip_path = write_shapefile_bundle(cross_sections, output_dir)

    png_path = output_dir / "beaver_creek_may74_xs_map.png"
    preview_path = output_dir / "beaver_creek_may74_xs_map_preview.png"
    svg_path = output_dir / "beaver_creek_may74_xs_map.svg"
    plot_cross_sections(
        cross_sections,
        centerlines,
        ras_version,
        png_path,
        preview_path,
        svg_path,
    )
    write_readme(
        output_dir / "README.md",
        plan_hdf,
        ras_version,
        units_system,
        cross_sections,
    )

    print(table.to_string(index=False))
    print(f"Wrote {csv_path}")
    print(f"Wrote {zip_path}")
    print(f"Wrote {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
