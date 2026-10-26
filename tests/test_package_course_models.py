import json
from pathlib import Path

import pytest

from scripts import package_course_models as package


@pytest.fixture
def staged_inputs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(package, "REPO", tmp_path)
    monkeypatch.setattr(
        package,
        "MODELS",
        {
            "sample": {
                "directory": "Sample",
                "stem": "Test",
                "plans": ["01"],
                "files": ["Test.prj"],
            },
        },
    )
    source = tmp_path / "data/Sample"
    source.mkdir(parents=True)
    (source / "Test.prj").write_text("Proj Title=Test\n", encoding="utf-8")
    stage = tmp_path / "work/release"
    model = stage / "inputs/sample/Sample"
    model.mkdir(parents=True)
    (model / "Test.prj").write_text("Proj Title=Test\n", encoding="utf-8")
    package.save_json(
        stage / "staging_manifest.json",
        {
            "source_hashes": {"sample": package.file_hashes(source)},
            "packages": {"sample": package.file_hashes(stage / "inputs/sample")},
        },
    )
    evidence = tmp_path / "outputs/evidence"
    package.save_json(
        evidence / "independent_review.json",
        {
            "approved": True,
            "stage_manifest_sha256": package.sha256(stage / "staging_manifest.json"),
        },
    )
    package.save_json(
        evidence / "run_checks.json",
        {
            "success": True,
            "stage_manifest_sha256": package.sha256(stage / "staging_manifest.json"),
            "input_file_hashes": {"sample": package.file_hashes(model)},
            "runs": [{"model": "sample", "plan": "01", "success": True}],
        },
    )
    return stage, evidence


def test_approval_rejects_changed_staged_input(staged_inputs):
    stage, evidence = staged_inputs
    (stage / "inputs/sample/Sample/Test.prj").write_text("Changed\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Staged package files changed"):
        package.require_approval(stage, evidence)


def test_approval_rejects_missing_plan_check(staged_inputs):
    stage, evidence = staged_inputs
    checks = json.loads((evidence / "run_checks.json").read_text(encoding="utf-8"))
    checks["runs"] = []
    package.save_json(evidence / "run_checks.json", checks)
    with pytest.raises(ValueError, match="do not cover all packaged plans"):
        package.require_approval(stage, evidence)


def test_zip_creation_rejects_unapproved_inputs(staged_inputs, tmp_path: Path):
    stage, evidence = staged_inputs
    package.save_json(evidence / "independent_review.json", {"approved": False})
    destination = tmp_path / "outputs/release"
    with pytest.raises(ValueError, match="independent approval"):
        package.build_archives(stage, evidence, destination)
    assert not destination.exists()


def test_model_selection_rejects_an_extra_result_file(tmp_path: Path):
    (tmp_path / "Test.prj").write_text("Proj Title=Test\n", encoding="utf-8")
    (tmp_path / "Test.p01.hdf").write_bytes(b"unexpected computation output")
    with pytest.raises(ValueError, match="Input file selection differs"):
        package.check_model_files(tmp_path, {"files": ["Test.prj"]})


def test_staged_project_rejects_leftover_plan_dependency(tmp_path: Path):
    project = tmp_path / "Sample.prj"
    project.write_text("Current Plan=p01\nPlan File=p01\n", encoding="utf-8")
    (tmp_path / "Sample.p01").write_text("Geom File=g01\nFlow File=f01\n", encoding="utf-8")
    (tmp_path / "Sample.g01").write_text("Geometry\n", encoding="utf-8")
    (tmp_path / "Sample.f01").write_text("Flow\n", encoding="utf-8")
    model = {"files": list(package.file_hashes(tmp_path))}
    package.check_model_files(tmp_path, model)
    project.write_text(project.read_text() + "Plan File=p02\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Sample.p02"):
        package.check_model_files(tmp_path, model)
