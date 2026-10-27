"""Guard the identifier and timestamp joins used by the reporting lesson."""

import numpy as np
import pandas as pd
import pytest

from scripts.report_davis_output_interval import (
    VARIABLES,
    shared_time_differences,
    unique_index,
)


def test_select_pipe_by_name_and_network_instead_of_position():
    records = np.array(
        [(b"67", b"Other"), (b"99", b"Davis"), (b"67", b"Davis")],
        dtype=[("Name", "S3"), ("System Name", "S8")],
    )
    assert unique_index(records, "67") == 2
    with pytest.raises(ValueError, match="exactly one"):
        unique_index(np.concatenate([records, records]), "67")


def test_shared_time_comparison_joins_times_and_preserves_signed_flow():
    reference = pd.DataFrame(
        {
            "time_seconds": [0, 30, 60, 90, 120],
            **{variable: [0.0, 10.0, 2.0, -5.0, 3.0] for variable in VARIABLES},
        }
    )
    candidate = reference.iloc[[4, 0, 2]].copy()
    assert shared_time_differences(reference, candidate) == dict.fromkeys(VARIABLES, 0.0)
    candidate.loc[4, "pipe_flow_cfs"] += 0.25
    assert shared_time_differences(reference, candidate)["pipe_flow_cfs"] == 0.25


def test_shared_time_comparison_rejects_missing_reference_times():
    reference = pd.DataFrame(
        {
            "time_seconds": [0, 60],
            **{variable: [0.0, 2.0] for variable in VARIABLES},
        }
    )
    candidate = reference.copy()
    candidate.loc[1, "time_seconds"] = 30
    with pytest.raises(ValueError, match="not contained"):
        shared_time_differences(reference, candidate)


@pytest.fixture
def mapped_davis_hdf(tmp_path):
    import h5py

    from scripts import report_davis_output_interval as reader

    path = tmp_path / "mapped.hdf"
    with h5py.File(path, "w") as hdf:
        hdf.attrs.update({"Units System": "US Customary", "File Version": "HEC-RAS 7.0.1"})
        hdf[reader.PIPE_ATTRS] = np.array(
            [
                (b"67", b"Davis", b"O14-DMH047", b"down", b"Circular", 2.0, 3.0),
                (b"other", b"Davis", b"other", b"down", b"Circular", 1.0, 1.0),
            ],
            dtype=[
                ("Name", "S20"),
                ("System Name", "S10"),
                ("US Node", "S20"),
                ("DS Node", "S20"),
                ("Shape", "S20"),
                ("Rise", "f8"),
                ("US Elevation", "f8"),
            ],
        )
        hdf[reader.NODE_ATTRS] = np.array(
            [(b"O14-DMH047", b"Davis"), (b"other", b"Davis")],
            dtype=[("Name", "S20"), ("System Name", "S10")],
        )
        hdf[reader.CONDUIT_INDICES] = [1, 0]
        hdf[reader.NODE_INDICES] = [1, 0]
        seconds = np.arange(0, 36 * 3600 + 1, 600)
        hdf[f"{reader.DSS}/Time"] = seconds / 86400
        hdf[f"{reader.DSS}/Time Step"] = np.full(217, 12)
        hdf[f"{reader.DSS}/Time Date Stamp"] = np.array(
            [
                (pd.Timestamp("2000-01-10 12:00:00") + pd.Timedelta(seconds=int(value)))
                .strftime("%d%b%Y %H:%M:%S")
                .encode()
                for value in seconds
            ]
        )
        hdf[f"{reader.BASE}/Time"] = seconds / 86400
        hdf[reader.PIPE_FLOW] = np.tile([900.0, 111.0], (217, 1))
        hdf[reader.PIPE_FLOW].attrs["Units"] = "ft^3/s"
        hdf[reader.NODE_WSE] = np.tile([90.0, 39.0], (217, 1))
        hdf[reader.NODE_WSE].attrs["Units"] = "ft"
        hdf[reader.BOUNDARY] = np.ones((217, 2))
        hdf[reader.BOUNDARY].attrs.update(
            {"Columns": np.array([b"Stage", b"Flow"]), "Flow": "cfs", "Stage": "ft"}
        )
        hdf["Results/Summary/Compute Messages (text)"] = [
            b"Finished Unsteady Flow Simulation\nOverall Volume Accounting Error as percentage: 0.1"
        ]
        for area in ("area2", "DS Channel"):
            hdf[
                f"{reader.BLOCKS}/Base Output/Summary Output/2D Flow Areas/{area}/Cell Maximum Water Surface Error"
            ] = np.zeros((1, 2))
        hdf["Geometry/2D Flow Areas/Attributes"] = np.array(
            [(b"area2", 2)], dtype=[("Name", "S20"), ("Cell Count", "i4")]
        )
    return path


def test_read_series_uses_both_nonidentity_maps(mapped_davis_hdf):
    from scripts.report_davis_output_interval import read_series

    frame, details = read_series(mapped_davis_hdf, 600)
    assert (frame["pipe_flow_cfs"] == 111.0).all()
    assert (frame["node_wse_ft"] == 39.0).all()
    assert details["pipe_index_zero_based"] == details["node_index_zero_based"] == 0
    assert details["pipe_result_column_zero_based"] == details["node_result_column_zero_based"] == 1


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "float",
        "duplicate",
        "negative",
        "range",
        "two_dimensional",
        "wrong_columns",
        "missing_selected",
    ],
)
@pytest.mark.parametrize("map_name", ["NODE_INDICES", "CONDUIT_INDICES"])
def test_read_series_rejects_bad_maps(mapped_davis_hdf, kind, map_name):
    import h5py

    from scripts import report_davis_output_interval as reader

    path = getattr(reader, map_name)
    with h5py.File(mapped_davis_hdf, "r+") as hdf:
        del hdf[path]
        if kind != "missing":
            values = {
                "float": [1.0, 0.0],
                "duplicate": [0, 0],
                "negative": [-1, 0],
                "range": [2, 0],
                "two_dimensional": [[1, 0]],
                "wrong_columns": [0],
                "missing_selected": [1],
            }[kind]
            hdf[path] = values
    with pytest.raises(ValueError):
        reader.read_series(mapped_davis_hdf, 600)
