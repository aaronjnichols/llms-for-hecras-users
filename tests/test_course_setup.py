"""Check setup boundaries without launching HEC-RAS."""

import io
import json
import os
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts import course_setup as setup


@pytest.fixture
def course(tmp_path, monkeypatch):
    root = tmp_path / "course with spaces"
    (root / "docs").mkdir(parents=True)
    archives = {}
    packages = []
    for model, plan in setup.PLANS.items():
        content = b"Proj Title=Fixture\n"
        import hashlib

        metadata = {
            "model": model,
            "files": {"Example.prj": hashlib.sha256(content).hexdigest()},
            "plans": [plan],
        }
        package = {
            "name": f"{model}.zip",
            "project_path": f"data/{model}/Example.prj",
            "package_metadata": metadata,
        }
        archive = root / package["name"]
        with ZipFile(archive, "w") as zipped:
            zipped.writestr(f"{model}/Example.prj", content)
            zipped.writestr(f"{model}-PACKAGE.json", json.dumps(metadata))
            zipped.writestr(f"{model}-README.txt", "Fixture")
        package.update(
            bytes=archive.stat().st_size,
            sha256=setup.sha256(archive),
            download_url="https://example.invalid/package",
        )
        archives[model] = archive.read_bytes()
        packages.append(package)
    setup.save_json(root / "docs/model_inputs_release.json", {"packages": packages})
    monkeypatch.setattr(setup, "runtime", lambda root: {"version": "3.13.test"})
    monkeypatch.setattr(setup, "provenance", lambda root: {"revision": "unknown"})
    monkeypatch.setattr(setup, "urlopen", lambda url, timeout: io.BytesIO(next_payload.pop(0)))
    next_payload = [archives[model] for model in setup.PLANS]
    return root, packages, archives, next_payload


def test_prepare_both_then_reuse_read_only(course):
    root, packages, archives, payload = course
    receipt = setup.prepare(root)
    assert receipt.is_file()
    before = {str(p): p.stat().st_mtime_ns for p in (root / "data").rglob("*") if p.is_file()}
    payload.extend(archives.values())
    setup.prepare(root)
    assert before == {
        str(p): p.stat().st_mtime_ns for p in (root / "data").rglob("*") if p.is_file()
    }
    assert setup.verify_source(root, packages[0]).is_dir()


@pytest.mark.parametrize("failure", ["truncated", "checksum", "metadata"])
def test_failed_second_candidate_installs_neither(course, failure):
    root, packages, archives, payload = course
    if failure == "truncated":
        payload[1] = payload[1][:-4]
    elif failure == "checksum":
        payload[1] = b"x" * len(payload[1])
    else:
        packages[1]["package_metadata"]["plans"] = ["99"]
        setup.save_json(root / "docs/model_inputs_release.json", {"packages": packages})
    with pytest.raises(ValueError):
        setup.prepare(root)
    assert not (root / "data").exists()
    assert len(list((root / "work").rglob("*.zip"))) == 2


@pytest.mark.parametrize("kind", ["extra", "partial", "conflict", "metadata"])
def test_existing_source_conflicts_preserved(course, kind):
    root, packages, archives, payload = course
    setup.prepare(root)
    folder = setup.source_folder(root, packages[0])
    if kind == "extra":
        (folder / "extra.txt").write_text("student work")
    elif kind == "partial":
        (folder / "Example.prj").unlink()
    elif kind == "conflict":
        (folder / "Example.prj").write_text("student work")
    else:
        (root / "data/beaver-creek-PACKAGE.json").write_text("{}")
    before = setup.manifest(root / "data")
    payload.extend(archives.values())
    with pytest.raises(ValueError):
        setup.prepare(root)
    assert setup.manifest(root / "data") == before


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/outside",
        "x\\y",
        "C:outside",
        "beaver-creek/example.PRJ",
        "extra",
        "folder./file",
    ],
)
def test_zip_paths_and_collisions(course, name):
    root, packages, _, _ = course
    archive = root / "unsafe.zip"
    with ZipFile(root / packages[0]["name"]) as original, ZipFile(archive, "w") as zipped:
        for item in original.infolist():
            zipped.writestr(item, original.read(item))
        zipped.writestr(name, "bad")
    with pytest.raises(ValueError):
        setup.verify_archive(archive, packages[0], root / "extract")
    assert not (root / "extract").exists()


def test_zip_link_rejected(course):
    from zipfile import ZipInfo

    root, packages, _, _ = course
    archive = root / "link.zip"
    info = ZipInfo("link")
    info.external_attr = 0o120777 << 16
    with ZipFile(archive, "w") as zipped:
        zipped.writestr(info, "outside")
    with pytest.raises(ValueError, match="Unsafe"):
        setup.verify_archive(archive, packages[0], root / "extract")


def test_runtime_and_missing_engine(tmp_path):
    with pytest.raises(ValueError, match="course .venv"):
        setup.runtime(tmp_path)
    with pytest.raises(ValueError, match="missing"):
        setup.executable_version(tmp_path / "Ras.exe")


@pytest.fixture
def run_course(course, monkeypatch):
    root, packages, archives, payload = course
    setup.prepare(root)
    monkeypatch.setattr(setup, "executable_version", lambda path: engine_metadata())
    monkeypatch.setattr(setup, "lesson_results", lambda *args: {"fixture": True})
    return root


def fake_success(command, root, log, timeout):
    project = Path(command[command.index("--project") + 1])
    plan = command[command.index("--plan") + 1]
    result = project.with_suffix(f".p{plan}.hdf")
    result.write_bytes(b"fixture result")
    setup.save_json(
        Path(command[-1]),
        {
            "success": True,
            "plan_number": plan,
            "project_path": str(project),
            "result_hdf_path": str(result),
            "result_hdf_sha256": setup.sha256(result),
        },
    )
    return 0


def test_run_and_check_spaces_sources_unchanged(run_course, monkeypatch):
    root = run_course
    before = setup.manifest(root / "data")
    monkeypatch.setattr(setup, "execute", fake_success)
    output = setup.run(root, "beaver-creek", Path("Ras.exe"), 900)
    assert setup.check(root, output) == {"fixture": True}
    assert (output / "summary.md").is_file()
    assert setup.manifest(root / "data") == before


@pytest.mark.parametrize("failure", ["returncode", "receipt", "timeout"])
def test_failed_runs_record_and_preserve_sources(run_course, monkeypatch, failure):
    root = run_course
    before = setup.manifest(root / "data")

    def process(command, root, log, timeout):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, timeout)
        fake_success(command, root, log, timeout)
        if failure == "receipt":
            setup.save_json(Path(command[-1]), {"success": False})
        return 1 if failure == "returncode" else 0

    monkeypatch.setattr(setup, "execute", process)
    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        setup.run(root, "davis", Path("Ras.exe"), 1)
    record = setup.read_json(next((root / "outputs").rglob("run.json")))
    assert not record["success"] and record["source_unchanged"]
    assert setup.manifest(root / "data") == before


@pytest.mark.parametrize("tamper", ["result", "stale", "record", "receipt", "outside"])
def test_check_rejects_changed_evidence(run_course, monkeypatch, tamper):
    root = run_course
    monkeypatch.setattr(setup, "execute", fake_success)
    output = setup.run(root, "davis", Path("Ras.exe"), 10)
    record = setup.read_json(output / "run.json")
    if tamper == "result":
        Path(record["result"]).write_bytes(b"changed")
    elif tamper == "stale":
        os.utime(record["result"], (1, 1))
    elif tamper == "receipt":
        (output / "runner.json").write_text("{}")
    else:
        record["plan" if tamper == "record" else "result"] = (
            "99" if tamper == "record" else str(root / "outside.hdf")
        )
        setup.save_json(output / "run.json", record)
    with pytest.raises(ValueError):
        setup.check(root, output)


def test_execute_timeout_kills_only_child(tmp_path, monkeypatch):
    from scripts import run_all_example_plans as runner

    killed = []

    class Child:
        pid = 123
        calls = 0

        def wait(self, timeout):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("fixture", timeout)
            return 1

    child = Child()
    monkeypatch.setattr(setup.subprocess, "Popen", lambda *args, **kwargs: child)
    monkeypatch.setattr(
        runner, "terminate_process_tree", lambda process: killed.append(process.pid)
    )
    with pytest.raises(subprocess.TimeoutExpired):
        setup.execute(["fake"], tmp_path, tmp_path / "log", 1)
    assert killed == [123] and child.calls == 2


def test_wrong_engine_version(tmp_path, monkeypatch):
    exe = tmp_path / "Ras.exe"
    exe.write_bytes(b"fixture")
    monkeypatch.setattr(
        setup, "windows_file_version", lambda path: engine_metadata("fixed_file_version", "6.7.0.0")
    )
    with pytest.raises(ValueError, match="7.0.1"):
        setup.executable_version(exe)


def test_marker_revision_and_unknown(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise FileNotFoundError("No Git")

    monkeypatch.setattr(setup.subprocess, "run", unavailable)
    assert setup.provenance(tmp_path)["revision"] == "unknown"
    marker = {"repository_url": "https://github.com/example/course", "revision": "a" * 40}
    setup.save_json(tmp_path / "course-source.json", marker)
    assert setup.provenance(tmp_path) == marker
    setup.save_json(tmp_path / "course-source.json", {"revision": "main"})
    with pytest.raises(ValueError):
        setup.provenance(tmp_path)


def test_beaver_check_has_no_student_script_dependency(tmp_path, monkeypatch):
    import builtins

    import h5py
    import numpy as np
    import pandas as pd

    from scripts import export_beaver_creek_may74_xs as reader

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "extract_beaver_creek_may74_results":
            raise AssertionError("The student script must not be imported")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    # Use the same module name as the CLI's local import.
    monkeypatch.setitem(__import__("sys").modules, "export_beaver_creek_may74_xs", reader)
    monkeypatch.setattr(
        reader,
        "extract_cross_sections",
        lambda *args: (
            pd.DataFrame({"wse_ft": np.ones(14), "vel_fps": np.ones(14), "geometry": [None] * 14}),
            None,
            "7.0.1",
            "US Customary",
        ),
    )
    result = tmp_path / "BEAVCREK.p01.hdf"
    steady = "Results/Steady/Output/Output Blocks/Base Output/Steady Profiles"
    with h5py.File(result, "w") as hdf:
        hdf.attrs.update({"File Version": "HEC-RAS 7.0.1", "Units System": "US Customary"})
        hdf.create_group("Plan Data/Plan Information").attrs["Plan Filename"] = "BEAVCREK.p01"
        hdf["Results/Summary/Compute Messages (text)"] = [
            b"Finished Steady Flow Simulation\nComplete Process"
        ]
        hdf[f"{steady}/Profile Names"] = [b"May '74 flood"]
        hdf["Results/Steady/Output/Geometry Info/Cross Section Attributes"] = np.zeros(14)
        for path, unit in (
            (f"{steady}/Cross Sections/Water Surface", "ft"),
            (f"{steady}/Cross Sections/Additional Variables/Velocity Total", "ft/s"),
        ):
            dataset = hdf.create_dataset(path, data=np.ones((1, 14)))
            dataset.attrs["Variable_Unit"] = np.array([[b"value", unit.encode()]])
    assert setup.lesson_results(result, "beaver-creek", tmp_path)["datasets"]
    assert (tmp_path / "beaver_creek_may74_results.csv").is_file()


@pytest.mark.parametrize(
    "name",
    ["check.json", "summary.md", "beaver_creek_may74_results.csv", "davis_selected_series.csv"],
)
def test_report_leaf_link_preserves_target(run_course, monkeypatch, name):
    root = run_course
    monkeypatch.setattr(setup, "execute", fake_success)
    output = setup.run(root, "davis", Path("Ras.exe"), 10)
    target = root / "data/protected-fixture.txt"
    target.write_bytes(b"unchanged")
    try:
        (output / name).symlink_to(target)
    except OSError:
        # Restricted sessions cannot create links. Inject the same filesystem
        # link flag and resolved target so the boundary guard still runs.
        original_resolve = Path.resolve
        original_link = Path.is_symlink
        leaf = output / name
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == leaf or original_link(path))
        monkeypatch.setattr(
            Path,
            "resolve",
            lambda path, *args, **kwargs: (
                target if path == leaf else original_resolve(path, *args, **kwargs)
            ),
        )
    with pytest.raises(ValueError):
        setup.check(root, output)
    assert target.read_bytes() == b"unchanged"


def test_prepare_rejects_linked_outputs_root(course, monkeypatch):
    root, _, _, _ = course
    target = root / "protected-output-target"
    target.mkdir()
    junction = root / "outputs"
    created = (
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )
    if not created:
        original_junction = Path.is_junction
        monkeypatch.setattr(
            Path, "is_junction", lambda path: path == junction or original_junction(path)
        )
    try:
        with pytest.raises(ValueError):
            setup.prepare(root)
        assert list(target.iterdir()) == []
        assert not (root / "data").exists()
    finally:
        if created:
            junction.rmdir()


@pytest.mark.parametrize("change", ["project_missing", "plan_changed", "geometry_changed"])
def test_check_rejects_working_input_changes(run_course, monkeypatch, change):
    root = run_course
    package = setup.packages(root)[1]
    folder = setup.source_folder(root, package)
    # Add text fixtures to the committed package record before a new run.
    for name in ("Example.p02", "Example.g02"):
        (folder / name).write_text("hydraulic fixture")
        package["package_metadata"]["files"][name] = setup.sha256(folder / name)
    all_packages = setup.packages(root)
    all_packages[1] = package
    setup.save_json(root / "docs/model_inputs_release.json", {"packages": all_packages})
    setup.save_json(root / "data/davis-PACKAGE.json", package["package_metadata"])
    monkeypatch.setattr(setup, "execute", fake_success)
    output = setup.run(root, "davis", Path("Ras.exe"), 10)
    record = setup.read_json(output / "run.json")
    project = Path(record["project"])
    if change == "project_missing":
        project.unlink()
    else:
        project.with_suffix(".p02" if change == "plan_changed" else ".g02").write_text("changed")
    with pytest.raises((OSError, ValueError)):
        setup.check(root, output)


def test_post_run_geometry_hdf_changes_and_derived_files_are_supported(run_course, monkeypatch):
    root = run_course
    package = setup.packages(root)[1]
    folder = setup.source_folder(root, package)
    name = "Example.g02.hdf"
    (folder / name).write_bytes(b"source geometry hdf")
    package["package_metadata"]["files"][name] = setup.sha256(folder / name)
    all_packages = setup.packages(root)
    all_packages[1] = package
    setup.save_json(root / "docs/model_inputs_release.json", {"packages": all_packages})
    setup.save_json(root / "data/davis-PACKAGE.json", package["package_metadata"])

    def computation(command, root, log, timeout):
        project = Path(command[command.index("--project") + 1])
        (project.parent / name).write_bytes(b"HEC updated working geometry")
        (project.parent / "derived.tmp").write_bytes(b"derived")
        return fake_success(command, root, log, timeout)

    monkeypatch.setattr(setup, "execute", computation)
    output = setup.run(root, "davis", Path("Ras.exe"), 10)
    assert setup.check(root, output) == {"fixture": True}
    record = setup.read_json(output / "run.json")
    assert name in record["work_input_changes_during_run"]
    (Path(record["project"]).parent / name).write_bytes(b"later change")
    with pytest.raises(ValueError, match="Working input"):
        setup.check(root, output)


@pytest.mark.parametrize("name", ["check.json", "summary.md"])
def test_failure_report_rejects_leaf_links(run_course, monkeypatch, name):
    root = run_course
    output = root / "outputs/failed-run"
    output.mkdir()
    target = root / "data/failure-report-target.txt"
    target.write_bytes(b"unchanged")
    leaf = output / name
    original_resolve = Path.resolve
    original_link = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == leaf or original_link(path))
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda path, *args, **kwargs: (
            target if path == leaf else original_resolve(path, *args, **kwargs)
        ),
    )
    monkeypatch.setattr(setup, "REPO", root)
    monkeypatch.setattr(setup.sys, "argv", ["course_setup.py", "check", "--run", str(output)])
    assert setup.main() == 1
    assert target.read_bytes() == b"unchanged"


def engine_metadata(field=None, value=None):
    info = {
        "release": "7.0.1",
        "fixed_file_version": "7.0.0.1",
        "fixed_product_version": "7.0.0.1",
        "translations": [
            {
                "language": 1033,
                "codepage": 1200,
                "strings": {
                    "FileDescription": "HEC-RAS 7.0.1",
                    "CompanyName": "Hydrologic Engineering Center",
                    "FileVersion": "7.00.0001",
                    "ProductVersion": "7.00.0001",
                },
            }
        ],
    }
    if field:
        if field in info:
            info[field] = value
        else:
            info["translations"][0]["strings"][field] = value
    return info


def test_actual_official_executable_metadata_is_accepted(tmp_path, monkeypatch):
    exe = tmp_path / "Ras.exe"
    exe.write_bytes(b"fixture")
    info = engine_metadata()
    monkeypatch.setattr(setup, "windows_file_version", lambda path: info)
    assert setup.executable_version(exe) == info


@pytest.mark.parametrize(
    "field,value",
    [
        ("fixed_file_version", "7.0.1.0"),
        ("fixed_product_version", "7.0.0.0"),
        ("FileDescription", "HEC-RAS 7.0"),
        ("CompanyName", "Other company"),
        ("FileVersion", "7.00.0000"),
        ("ProductVersion", "7.00.0000"),
    ],
)
def test_wrong_executable_metadata_is_rejected(tmp_path, monkeypatch, field, value):
    exe = tmp_path / "Ras.exe"
    exe.write_bytes(b"fixture")
    monkeypatch.setattr(setup, "windows_file_version", lambda path: engine_metadata(field, value))
    with pytest.raises(ValueError, match="metadata differs"):
        setup.executable_version(exe)
