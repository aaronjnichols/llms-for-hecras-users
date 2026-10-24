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
