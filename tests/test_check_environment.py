from pathlib import Path

import pytest

from scripts.check_environment import IMPORT_NAMES, load_pins


def test_load_pins_follows_local_requirements_files(tmp_path: Path) -> None:
    (tmp_path / "runtime.txt").write_text("numpy==2.5.2\n", encoding="utf-8")
    (tmp_path / "dev.txt").write_text(
        "-r runtime.txt\npytest==9.1.1  # testing\n", encoding="utf-8"
    )

    assert load_pins(tmp_path / "dev.txt") == {
        "numpy": "2.5.2",
        "pytest": "9.1.1",
    }


def test_load_pins_rejects_unpinned_dependencies(tmp_path: Path) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pandas>=3\n", encoding="utf-8")

    with pytest.raises(ValueError, match="exact package pin"):
        load_pins(requirements)


def test_distribution_names_with_different_import_names_are_mapped() -> None:
    assert IMPORT_NAMES["pywin32"] == "win32api"
    assert IMPORT_NAMES["pillow"] == "PIL"
