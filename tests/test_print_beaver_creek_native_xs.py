from pathlib import Path

import pytest

from scripts.print_beaver_creek_native_xs import PLAN_OUTPUTS, sha256, validate_paths


def make_project(root: Path) -> Path:
    project_dir = root / "work" / "beaver"
    project_dir.mkdir(parents=True)
    project = project_dir / "BEAVCREK.prj"
    project.write_text("Proj Title=Single Bridge - Example 2\n", encoding="ascii")
    for _plan, _pdf, result_hdf in PLAN_OUTPUTS:
        project.with_name(result_hdf).write_bytes(b"computed result placeholder")
    return project


def test_validate_paths_accepts_disposable_project(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    project = make_project(tmp_path)

    validate_paths(project, tmp_path / "outputs", overwrite=False)


def test_validate_paths_rejects_source_project(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    source_dir = tmp_path / "data" / "beaver"
    source_dir.mkdir(parents=True)
    project = source_dir / "BEAVCREK.prj"
    project.write_text("source", encoding="ascii")

    with pytest.raises(ValueError, match="disposable copy"):
        validate_paths(project, tmp_path / "outputs", overwrite=False)


def test_sha256_is_stable(tmp_path: Path) -> None:
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"HEC-RAS native plot")

    assert sha256(sample) == "64d5c40ba8a1705255153a6370be41422843077fd66ad367da5fed230ed23ad8"
