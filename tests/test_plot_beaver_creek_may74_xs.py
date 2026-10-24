from pathlib import Path

import pytest

from scripts.plot_beaver_creek_may74_xs import output_name, roughness_regions


def test_roughness_regions_uses_change_stations_as_region_starts() -> None:
    regions = roughness_regions(
        {"Station": [0.0, 350.0, 550.0], "Mann n": [0.10, 0.04, 0.14]},
        minimum_station=0.0,
        maximum_station=1_000.0,
    )

    assert regions == [
        (0.0, 350.0, 0.10),
        (350.0, 550.0, 0.04),
        (550.0, 1_000.0, 0.14),
    ]


def test_roughness_regions_rejects_inconsistent_values() -> None:
    with pytest.raises(ValueError, match="missing or inconsistent"):
        roughness_regions(
            {"Station": [0.0, 350.0], "Mann n": [0.10]},
            minimum_station=0.0,
            maximum_station=1_000.0,
        )


def test_output_name_uses_plan_extension() -> None:
    source = Path("BEAVCREK.p02.hdf")

    assert output_name(source) == "beaver_creek_may74_p02_cross_sections.pdf"
