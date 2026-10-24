from __future__ import annotations

import pytest

from scripts.davis_type1_storm_comparison import (
    TYPE_I_CUMULATIVE_FRACTIONS,
    build_plan,
    build_unsteady_flow,
    type_i_incremental_depths,
)


def test_type_i_distribution_is_monotonic_and_complete() -> None:
    assert len(TYPE_I_CUMULATIVE_FRACTIONS) == 50
    assert TYPE_I_CUMULATIVE_FRACTIONS[0] == 0.0
    assert TYPE_I_CUMULATIVE_FRACTIONS[-1] == 1.0
    assert all(
        current >= previous
        for previous, current in zip(
            TYPE_I_CUMULATIVE_FRACTIONS,
            TYPE_I_CUMULATIVE_FRACTIONS[1:],
            strict=False,
        )
    )


@pytest.mark.parametrize("depth", [3.34, 5.10])
def test_type_i_incremental_depths_preserve_total(depth: float) -> None:
    values = type_i_incremental_depths(depth)
    assert len(values) == 50
    assert values[0] == 0.0
    assert values[-1] == 0.0
    assert sum(values) == pytest.approx(depth)


def test_build_unsteady_flow_replaces_only_rainfall_block() -> None:
    source = "\n".join(
        [
            "Flow Title=Original",
            "Boundary Location=area2",
            "Interval=1HOUR",
            "Precipitation Hydrograph= 3 ",
            "      .1      .2       0",
            "DSS Path=",
            "Use DSS=False",
        ]
    )
    result = build_unsteady_flow(source, "10-year Type I", 3.34)
    assert "Flow Title=10-year Type I" in result
    assert "Interval=30MIN" in result
    assert "Precipitation Hydrograph= 50 " in result
    assert "DSS Path=" in result
    assert "Use DSS=False" in result


def test_build_plan_changes_flow_and_duration() -> None:
    source = "\n".join(
        [
            "Plan Title=Original",
            "Short Identifier=Original",
            "Simulation Date=10JAN2000,1200,11JAN2000,2400",
            "Flow File=u01",
        ]
    )
    result = build_plan(source, "10-year", "10-year", "02")
    assert "Plan Title=10-year" in result
    assert "Flow File=u02" in result
    assert "Simulation Date=10JAN2000,1200,12JAN2000,2400" in result
