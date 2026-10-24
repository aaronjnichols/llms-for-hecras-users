"""Prepare Davis-area land cover and soils for the Lesson 06 GIS exercise.

Run from the repository root with the course Python environment. The source HEC-RAS
geometry is opened read-only. Downloads and prepared files go under outputs/.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import geopandas as gpd
import h5py
import numpy as np
import pandas as pd
import rasterio
from pyproj import CRS, Transformer
from rasterio.features import shapes
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import Polygon, shape
from shapely.ops import transform, unary_union

REPO_ROOT = Path(__file__).resolve().parents[1]
DAVIS = REPO_ROOT / "data/Example_Projects_7_0/Pipes/Davis"
SOURCE_HDF = DAVIS / "DavisStormSystem.g02.hdf"
SOURCE_PROJECTION = DAVIS / "GIS/2871.prj"
WCS_URL = "https://dmsdata.cr.usgs.gov/geoserver/mrlc_Land-Cover-Native_conus_year_data/wcs"
WCS_COVERAGE = "mrlc_Land-Cover-Native_conus_year_data:Land-Cover-Native_conus_year_data"
WFS_URL = "https://sdmdataaccess.sc.egov.usda.gov/Spatial/SDMWGS84Geographic.wfs"
SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
NLCD_NAMES = {
    11: "Open Water",
    12: "Perennial Ice/Snow",
    21: "Developed, Open Space",
    22: "Developed, Low Intensity",
    23: "Developed, Medium Intensity",
    24: "Developed, High Intensity",
    31: "Barren Land",
    41: "Deciduous Forest",
    42: "Evergreen Forest",
    43: "Mixed Forest",
    52: "Shrub/Scrub",
    71: "Grassland/Herbaceous",
    81: "Pasture/Hay",
    82: "Cultivated Crops",
    90: "Woody Wetlands",
    95: "Emergent Herbaceous Wetlands",
}


def fetch(url: str, parameters: dict[str, object], *, post: bool = False) -> bytes:
    encoded = urlencode(parameters).encode("utf-8")
    request = Request(
        url if post else f"{url}?{encoded.decode('utf-8')}",
        data=encoded if post else None,
        headers={"User-Agent": "llms-for-hecras-users/lesson06"},
    )
    with urlopen(request, timeout=120) as response:
        return response.read()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_davis_perimeters() -> gpd.GeoDataFrame:
    """Reconstruct the two 2D polygons from HDF point/part offsets."""
    with h5py.File(SOURCE_HDF, "r") as hdf:
        group = hdf["Geometry/2D Flow Areas"]
        attrs = group["Attributes"][:]
        info = group["Polygon Info"][:]
        parts = group["Polygon Parts"][:]
        points = group["Polygon Points"][:]
    records: list[dict[str, object]] = []
    for attr, polygon_info in zip(attrs, info, strict=True):
        name = attr["Name"].decode("utf-8").strip()
        part_start, part_count = (int(x) for x in polygon_info[2:4])
        rings = []
        for part in parts[part_start : part_start + part_count]:
            point_start, point_count = (int(x) for x in part)
            rings.append(points[point_start : point_start + point_count].tolist())
        if len(rings) != 1:
            raise ValueError(f"2D area {name!r} has {len(rings)} parts; review manually")
        polygon = Polygon(rings[0])
        if polygon.is_empty or not polygon.is_valid:
            raise ValueError(f"Invalid 2D perimeter for {name!r}")
        records.append({"area_name": name, "geometry": polygon})
    crs = CRS.from_wkt(SOURCE_PROJECTION.read_text(encoding="utf-8"))
    if not crs.is_projected or "foot" not in crs.axis_info[0].unit_name.lower():
        raise ValueError(f"Expected projected feet in {SOURCE_PROJECTION}: {crs}")
    return gpd.GeoDataFrame(records, crs=crs)


def download_nlcd(buffer_geometry: object, crs: CRS, source_dir: Path) -> Path:
    to_5070 = Transformer.from_crs(crs, 5070, always_xy=True).transform
    bounds = transform(to_5070, buffer_geometry).bounds
    # Extra source pixels prevent reprojection from leaving an edge gap.
    left, bottom, right, top = (
        math.floor(bounds[0] - 90),
        math.floor(bounds[1] - 90),
        math.ceil(bounds[2] + 90),
        math.ceil(bounds[3] + 90),
    )
    width = math.ceil((right - left) / 30)
    height = math.ceil((top - bottom) / 30)
    parameters = {
        "service": "WCS",
        "version": "1.0.0",
        "request": "GetCoverage",
        "coverage": WCS_COVERAGE,
        "format": "GeoTIFF",
        "bbox": f"{left},{bottom},{right},{top}",
        "crs": "EPSG:5070",
        "response_crs": "EPSG:5070",
        "width": width,
        "height": height,
        "time": "2025-01-01",
    }
    data = fetch(WCS_URL, parameters)
    if data[:4] not in (b"II*\x00", b"MM\x00*"):
        raise ValueError(f"USGS did not return a GeoTIFF: {data[:300]!r}")
    path = source_dir / "annual_nlcd_2025_davis_wcs.tif"
    path.write_bytes(data)
    with rasterio.open(path) as raster:
        if raster.count != 1 or raster.crs != CRS.from_epsg(5070):
            raise ValueError("Unexpected NLCD raster bands or CRS")
        classes = set(np.unique(raster.read(1)).tolist()) - {250}
        if not classes or not classes.issubset(NLCD_NAMES):
            raise ValueError(f"Unexpected 2025 NLCD classes: {sorted(classes)}")
    return path


def prepare_nlcd(
    source: Path, buffer_geometry: object, crs: CRS, output_dir: Path
) -> tuple[Path, gpd.GeoDataFrame]:
    raster_path = output_dir / "nlcd_2025_clipped.tif"
    with rasterio.open(source) as src:
        dst_transform, dst_width, dst_height = calculate_default_transform(
            src.crs,
            crs,
            src.width,
            src.height,
            *src.bounds,
            resolution=30 / crs.axis_info[0].unit_conversion_factor,
        )
        destination = np.full((dst_height, dst_width), 250, dtype=np.uint8)
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            src_nodata=src.nodata,
            dst_transform=dst_transform,
            dst_crs=crs,
            dst_nodata=250,
            resampling=Resampling.nearest,
        )
        profile = src.profile.copy()
    profile.update(
        driver="GTiff",
        crs=crs,
        transform=dst_transform,
        width=dst_width,
        height=dst_height,
        count=1,
        dtype="uint8",
        nodata=250,
        compress="deflate",
    )
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(destination, 1)
            clipped, clipped_transform = mask(
                dst,
                [buffer_geometry.__geo_interface__],
                crop=True,
                all_touched=True,
                nodata=250,
            )
    profile.update(transform=clipped_transform, width=clipped.shape[2], height=clipped.shape[1])
    with rasterio.open(raster_path, "w", **profile) as dst:
        dst.write(clipped)
    records = []
    for geometry, value in shapes(clipped[0], mask=clipped[0] != 250, transform=clipped_transform):
        code = int(value)
        polygon = shape(geometry).intersection(buffer_geometry)
        if not polygon.is_empty:
            records.append({"NLCD": code, "LC_NAME": NLCD_NAMES[code], "geometry": polygon})
    land_use = gpd.GeoDataFrame(records, crs=crs)
    if land_use.empty or not land_use.geometry.is_valid.all():
        raise ValueError("Polygonized NLCD output is empty or invalid")
    return raster_path, land_use


def download_soils(buffer_geometry: object, crs: CRS, source_dir: Path) -> gpd.GeoDataFrame:
    to_lonlat = Transformer.from_crs(crs, 4326, always_xy=True).transform
    west, south, east, north = transform(to_lonlat, buffer_geometry).bounds
    data = fetch(
        WFS_URL,
        {
            "service": "WFS",
            "version": "1.0.0",  # Traditional longitude/latitude axis order.
            "request": "GetFeature",
            "typeName": "MapunitPoly",
            "bbox": f"{west},{south},{east},{north}",
            "outputFormat": "GML2",
        },
    )
    if b"FeatureCollection" not in data[:1000]:
        raise ValueError(f"NRCS did not return GML soil polygons: {data[:300]!r}")
    (source_dir / "nrcs_mapunitpoly_davis_bbox.gml").write_bytes(data)
    soils = gpd.read_file(io.BytesIO(data)).set_crs(4326)
    if soils.empty or not (soils.total_bounds[0] < -100 and soils.total_bounds[1] > 0):
        raise ValueError(f"Unexpected NRCS soil coordinates: {soils.total_bounds}")
    soils = soils.to_crs(crs)
    soils = gpd.clip(soils, buffer_geometry, keep_geom_type=True)
    if soils.empty:
        raise ValueError("NRCS soils do not intersect the Davis buffer")
    keys = sorted(set(soils["mukey"].astype(str)))
    rating_rows: list[list[object]] = []
    for first in range(0, len(keys), 150):
        key_list = ",".join(f"'{key}'" for key in keys[first : first + 150])
        query = (
            "SELECT m.mukey, m.muname, a.hydgrpdcd "
            "FROM mapunit AS m LEFT JOIN muaggatt AS a ON m.mukey = a.mukey "
            f"WHERE m.mukey IN ({key_list})"
        )
        response = fetch(SDA_URL, {"query": query, "format": "JSON"}, post=True)
        payload = json.loads(response)
        rating_rows.extend(payload.get("Table", []))
    (source_dir / "nrcs_hsg_ratings.json").write_text(
        json.dumps(rating_rows, indent=2), encoding="utf-8"
    )
    ratings = pd.DataFrame(rating_rows, columns=["MUKEY", "MUNAME", "HSG"])
    if ratings["MUKEY"].duplicated().any():
        raise ValueError("NRCS returned duplicate map-unit HSG ratings")
    soils["MUKEY"] = soils["mukey"].astype(str)
    soils = soils.merge(ratings, on="MUKEY", how="left", validate="many_to_one")
    if soils["HSG"].isna().any():
        raise ValueError("Some NRCS soil polygons have no matching HSG rating")
    return soils[["MUKEY", "musym", "MUNAME", "HSG", "geometry"]].rename(columns={"musym": "MUSYM"})


def write_vector(frame: gpd.GeoDataFrame, stem: str, output_dir: Path) -> None:
    frame.to_file(output_dir / f"{stem}.gpkg", driver="GPKG")
    frame.to_file(output_dir / f"{stem}.shp", driver="ESRI Shapefile")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=REPO_ROOT / "outputs/lesson06_davis_gis_inputs_20260922"
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"Output already exists: {output}. Choose a new --output folder.")
    source_dir = output / "source_downloads"
    prepared = output / "prepared"
    source_dir.mkdir(parents=True)
    prepared.mkdir()

    perimeters = read_davis_perimeters()
    buffer_geometry = unary_union(perimeters.geometry).buffer(500)
    if buffer_geometry.is_empty or not buffer_geometry.is_valid:
        raise ValueError("Invalid 500-foot Davis buffer")
    crs = CRS.from_user_input(perimeters.crs)
    write_vector(perimeters, "davis_2d_perimeters", prepared)
    write_vector(
        gpd.GeoDataFrame([{"buffer_ft": 500, "geometry": buffer_geometry}], crs=crs),
        "davis_2d_buffer_500ft",
        prepared,
    )

    nlcd_source = download_nlcd(buffer_geometry, crs, source_dir)
    nlcd_raster, land_use = prepare_nlcd(nlcd_source, buffer_geometry, crs, prepared)
    write_vector(land_use, "land_use_nlcd_2025", prepared)
    soils = download_soils(buffer_geometry, crs, source_dir)
    write_vector(soils, "soils_hsg", prepared)

    soil_union = unary_union(soils.geometry)
    land_union = unary_union(land_use.geometry)
    report = {
        "source_hdf": str(SOURCE_HDF),
        "source_hdf_sha256": sha256(SOURCE_HDF),
        "source_projection": str(SOURCE_PROJECTION),
        "crs": crs.to_string(),
        "buffer_ft": 500,
        "2d_areas": perimeters["area_name"].tolist(),
        "buffer_area_sqft": buffer_geometry.area,
        "nlcd_source_url": WCS_URL,
        "nlcd_source_sha256": sha256(nlcd_source),
        "nlcd_year": 2025,
        "nlcd_raster": str(nlcd_raster),
        "nlcd_class_counts": {
            str(int(k)): int(v) for k, v in land_use["NLCD"].value_counts().items()
        },
        "land_use_features": len(land_use),
        "land_use_missing_buffer_area_sqft": buffer_geometry.difference(land_union).area,
        "soil_source_url": WFS_URL,
        "soil_ratings_url": SDA_URL,
        "soil_features": len(soils),
        "soil_map_units": int(soils["MUKEY"].nunique()),
        "soil_hsg_counts": {
            str(k): int(v) for k, v in soils["HSG"].value_counts(dropna=False).items()
        },
        "soil_missing_buffer_area_sqft": buffer_geometry.difference(soil_union).area,
        "soil_hsg_missing_count": int(soils["HSG"].isna().sum()),
    }
    (output / "qa_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
