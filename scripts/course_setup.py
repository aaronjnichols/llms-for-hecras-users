"""Prepare course sources and record disposable HEC-RAS lesson runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path, PurePosixPath
from urllib.request import urlopen
from zipfile import ZipFile

REPO = Path(__file__).resolve().parents[1]
DEFAULT_RAS_EXE = Path(r"C:\Program Files (x86)\HEC\HEC-RAS\7.0.1\Ras.exe")
PLANS = {"beaver-creek": "01", "davis": "02"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def below(path: Path, parent: Path) -> Path:
    resolved = path.resolve()
    if resolved == parent.resolve() or not resolved.is_relative_to(parent.resolve()):
        raise ValueError(f"Path must be below {parent}: {path}")
    for part in [path, *path.parents]:
        if part.is_symlink() or part.is_junction():
            raise ValueError(f"Links are not permitted: {part}")
        if part == parent:
            break
    return resolved


def manifest(folder: Path) -> dict[str, str]:
    if not folder.is_dir() or folder.is_symlink() or folder.is_junction():
        raise ValueError(f"Missing source folder or unsafe link: {folder}")
    result = {}
    for path in sorted(folder.rglob("*")):
        below(path, folder)
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = sha256(path)
    return result


def output_file(folder: Path, name: str) -> Path:
    """Reject report links before a report writer opens a file."""
    return below(folder / name, folder)


def retained_inputs(folder: Path, source_hashes: dict[str, str]) -> dict[str, str]:
    """Hash retained inputs only. Generated model files are separate evidence."""
    return {name: sha256(below(folder / name, folder)) for name in source_hashes}


def runtime(root: Path) -> dict:
    expected = root / ".venv/Scripts/python.exe"
    if (
        os.name != "nt"
        or sys.version_info[:2] != (3, 13)
        or platform.python_implementation() != "CPython"
        or struct.calcsize("P") != 8
        or Path(sys.executable).resolve() != expected.resolve()
        or (callable(getattr(sys, "_is_gil_enabled", None)) and not sys._is_gil_enabled())
    ):
        raise ValueError("Use the course .venv with standard Windows CPython x64 3.13.x.")
    return {"version": platform.python_version(), "executable": str(expected.resolve())}


def provenance(root: Path) -> dict:
    marker = root / "course-source.json"
    if marker.exists():
        value = read_json(marker)
        if not value.get("repository_url") or not re.fullmatch(
            "[0-9a-f]{40}", value.get("revision", "")
        ):
            raise ValueError("course-source.json must state repository_url and the full revision.")
        return value
    archive_marker = root / ".git_archival.txt"
    if archive_marker.is_file():
        revision = archive_marker.read_text(encoding="utf-8").strip()
        if re.fullmatch("[0-9a-fA-F]{40}", revision):
            return {"revision": revision.lower(), "method": "git archive export-subst"}
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
        return {"revision": revision, "method": "git HEAD"}
    except (OSError, subprocess.CalledProcessError):
        return {"revision": "unknown", "method": "No source marker or readable Git revision"}


def packages(root: Path) -> list[dict]:
    return read_json(root / "docs/model_inputs_release.json")["packages"]


def source_folder(root: Path, package: dict) -> Path:
    return below(root / package["project_path"], root / "data").parent


def verify_source(root: Path, package: dict) -> Path:
    folder = source_folder(root, package)
    if manifest(folder) != package["package_metadata"]["files"]:
        raise ValueError(
            f"Source files differ or include extra files: {folder}. Use a fresh course folder."
        )
    expected_directories = {
        parent.as_posix()
        for name in package["package_metadata"]["files"]
        for parent in PurePosixPath(name).parents
        if parent != PurePosixPath(".")
    }
    actual_directories = {
        path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_dir()
    }
    if actual_directories != expected_directories:
        raise ValueError(f"Source folders differ: {folder}. Use a fresh course folder.")
    metadata = root / "data" / f"{package['package_metadata']['model']}-PACKAGE.json"
    below(metadata, root / "data")
    if read_json(metadata) != package["package_metadata"]:
        raise ValueError(f"Package metadata differs: {metadata}")
    return folder


def download(package: dict, destination: Path) -> None:
    try:
        with (
            urlopen(package["download_url"], timeout=60) as response,
            destination.open("xb") as stream,
        ):
            shutil.copyfileobj(response, stream)
    except OSError as exc:
        raise ValueError(f"Download failed. File retained at {destination}: {exc}") from exc
    if destination.stat().st_size != package["bytes"] or sha256(destination) != package["sha256"]:
        raise ValueError(f"Download size or SHA-256 differs. File retained: {destination}")


def verify_archive(archive: Path, package: dict, destination: Path) -> None:
    model = package["package_metadata"]["model"]
    directory = PurePosixPath(package["project_path"]).parent.relative_to("data")
    expected = {
        str(directory / name): digest
        for name, digest in package["package_metadata"]["files"].items()
    }
    expected_names = set(expected) | {f"{model}-PACKAGE.json", f"{model}-README.txt"}
    with ZipFile(archive) as zipped:
        names = []
        for item in zipped.infolist():
            name = item.filename
            parts = PurePosixPath(name).parts
            mode = item.external_attr >> 16
            if (
                not parts
                or name.startswith("/")
                or "\\" in name
                or ":" in name
                or any(part in {".", ".."} or part.endswith((" ", ".")) for part in parts)
                or item.is_dir()
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
            ):
                raise ValueError(f"Unsafe ZIP member: {name}")
            names.append(name)
        if len({name.casefold() for name in names}) != len(names) or set(names) != expected_names:
            raise ValueError("ZIP members differ or collide. No sources were installed.")
        if json.loads(zipped.read(f"{model}-PACKAGE.json")) != package["package_metadata"]:
            raise ValueError("ZIP package metadata differs.")
        for name, digest in expected.items():
            if hashlib.sha256(zipped.read(name)).hexdigest() != digest:
                raise ValueError(f"ZIP model hash differs: {name}")
        zipped.extractall(destination)


def new_id() -> str:
    return "lesson00_" + time.strftime("%Y%m%dT%H%M%SZ_", time.gmtime()) + uuid.uuid4().hex[:8]


def prepare(root: Path) -> Path:
    python = runtime(root)
    identifier = new_id()
    output = below(root / "outputs" / identifier, root / "outputs")
    setup_receipt = output_file(output, "setup.json")
    stage = below(root / "work" / identifier, root / "work")
    stage.mkdir(parents=True)
    candidates = []
    for package in packages(root):
        archive = stage / package["name"]
        download(package, archive)
        model = package["package_metadata"]["model"]
        extracted = stage / model
        verify_archive(archive, package, extracted)
        folder = source_folder(root, package)
        metadata = root / "data" / f"{model}-PACKAGE.json"
        readme = root / "data" / f"{model}-README.txt"
        for target in (metadata, readme):
            below(target, root / "data")
        if folder.exists():
            verify_source(root, package)
            if (
                not readme.is_file()
                or readme.read_bytes() != (extracted / readme.name).read_bytes()
            ):
                raise ValueError(f"Source README differs or is missing: {readme}")
        elif metadata.exists() or readme.exists():
            raise ValueError(f"Partial source install: {folder}. Use a fresh course folder.")
        candidates.append((package, extracted, folder))
    # Check both candidates before the first source write.
    for package, extracted, folder in candidates:
        if not folder.exists():
            folder.parent.mkdir(parents=True, exist_ok=True)
            relative = Path(package["project_path"]).parent.relative_to("data")
            shutil.copytree(extracted / relative, folder)
            model = package["package_metadata"]["model"]
            for name in (f"{model}-PACKAGE.json", f"{model}-README.txt"):
                with (root / "data" / name).open("xb") as target:
                    target.write((extracted / name).read_bytes())
        verify_source(root, package)
    output.mkdir(parents=True)
    save_json(
        output_file(output, setup_receipt.name),
        {
            "schema_version": 1,
            "python": python,
            "source_code": provenance(root),
            "packages": packages(root),
            "source_paths": [str(row[2]) for row in candidates],
        },
    )
    return setup_receipt


def validate_engine_info(info: dict) -> None:
    """Require the metadata observed in the official HEC-RAS 7.0.1 executable."""
    expected = {
        "FileDescription": "HEC-RAS 7.0.1",
        "CompanyName": "Hydrologic Engineering Center",
        "FileVersion": "7.00.0001",
        "ProductVersion": "7.00.0001",
    }
    if (
        info.get("release") != "7.0.1"
        or info.get("fixed_file_version") != "7.0.0.1"
        or info.get("fixed_product_version") != "7.0.0.1"
        or not info.get("translations")
        or any(item.get("strings") != expected for item in info["translations"])
    ):
        raise ValueError("Use the official HEC-RAS 7.0.1 executable. Its version metadata differs.")


def executable_version(path: Path) -> dict:
    if not path.is_file() or path.name.casefold() != "ras.exe":
        raise ValueError(f"HEC-RAS executable is missing: {path}. Use --ras-exe PATH.")
    info = windows_file_version(path)
    validate_engine_info(info)
    return info


def windows_file_version(path: Path) -> dict:
    """Read fixed and translated VERSIONINFO without starting the executable."""
    import win32api

    try:
        fixed = win32api.GetFileVersionInfo(str(path), "\\")
        translations = win32api.GetFileVersionInfo(str(path), "\\VarFileInfo\\Translation")
        strings = []
        for language, codepage in translations:
            prefix = f"\\StringFileInfo\\{language:04x}{codepage:04x}\\"
            strings.append(
                {
                    "language": language,
                    "codepage": codepage,
                    "strings": {
                        key: win32api.GetFileVersionInfo(str(path), prefix + key)
                        for key in (
                            "FileDescription",
                            "CompanyName",
                            "FileVersion",
                            "ProductVersion",
                        )
                    },
                }
            )
    except win32api.error as exc:
        raise ValueError(f"Cannot read HEC-RAS VERSIONINFO: {path}: {exc}") from exc

    def dotted(ms: int, ls: int) -> str:
        return f"{ms >> 16}.{ms & 65535}.{ls >> 16}.{ls & 65535}"

    return {
        "release": "7.0.1"
        if strings
        and all(item["strings"]["FileDescription"] == "HEC-RAS 7.0.1" for item in strings)
        else "unknown",
        "fixed_file_version": dotted(fixed["FileVersionMS"], fixed["FileVersionLS"]),
        "fixed_product_version": dotted(fixed["ProductVersionMS"], fixed["ProductVersionLS"]),
        "translations": strings,
    }


def execute(command: list[str], root: Path, log: Path, timeout: int) -> int:
    try:
        from scripts.run_all_example_plans import terminate_process_tree
    except ModuleNotFoundError:
        from run_all_example_plans import terminate_process_tree
    with output_file(log.parent, log.name).open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_process_tree(process)
            process.wait(timeout=30)
            raise


def run(root: Path, model: str, ras_exe: Path, timeout: int) -> Path:
    python = runtime(root)
    if timeout <= 0:
        raise ValueError("Timeout must be greater than zero.")
    version = executable_version(ras_exe)
    package = next(item for item in packages(root) if item["package_metadata"]["model"] == model)
    source = verify_source(root, package)
    before = manifest(source)
    identifier = new_id()
    work = below(root / "work" / identifier / model, root / "work")
    output = below(root / "outputs" / identifier / model, root / "outputs")
    shutil.copytree(source, work)
    if manifest(work) != before or manifest(source) != before:
        raise ValueError("The source or disposable copy changed during the copy.")
    output.mkdir(parents=True)
    plan = PLANS[model]
    project = work / Path(package["project_path"]).name
    result = project.with_suffix(f".p{plan}.hdf")
    receipt = output_file(output, "runner.json")
    record = {
        "schema_version": 1,
        "model": model,
        "plan": plan,
        "source": str(source),
        "source_hashes": before,
        "package": package,
        "source_code": provenance(root),
        "python": python,
        "ras_exe": str(ras_exe.resolve()),
        "executable_version": version["release"],
        "executable_version_info": version,
        "project": str(project),
        "result": str(result),
        "timeout_seconds": timeout,
        "started_epoch": time.time(),
        "success": False,
    }
    save_json(output_file(output, "run.json"), record)
    try:
        code = execute(
            [
                sys.executable,
                "-E",
                str(root / "scripts/run_all_example_plans.py"),
                "run-one",
                "--project",
                str(project),
                "--plan",
                plan,
                "--ras-exe",
                str(ras_exe),
                "--result",
                str(receipt),
            ],
            root,
            output / "run.log",
            timeout,
        )
        record["returncode"] = code
        child = read_json(receipt)
        if (
            code != 0
            or child.get("success") is not True
            or child.get("plan_number") != plan
            or Path(child.get("project_path", "")).resolve() != project
        ):
            raise ValueError(f"Run failed or receipts disagree. Inspect {output}")
        if not result.is_file() or child.get("result_hdf_sha256") != sha256(result):
            raise ValueError("The result is missing or differs from the runner receipt.")
        record["result_sha256"] = sha256(result)
        record["runner_sha256"] = sha256(receipt)
        record["work_input_hashes_after_run"] = retained_inputs(work, before)
        record["work_input_changes_during_run"] = {
            name: {"before": digest, "after": record["work_input_hashes_after_run"][name]}
            for name, digest in before.items()
            if digest != record["work_input_hashes_after_run"][name]
        }
        # HEC-RAS can update the working geometry HDF. Hydraulic text inputs
        # must remain equal to the copied source during this lesson run.
        for name in record["work_input_changes_during_run"]:
            if re.search(r"\.[pgfuq]\d{2}$", name, re.IGNORECASE):
                raise ValueError(f"A hydraulic text input changed during the run: {name}")
        record["success"] = True
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        record["ended_epoch"] = time.time()
        record["source_unchanged"] = manifest(source) == before
        if not record["source_unchanged"]:
            record["success"] = False
        save_json(output_file(output, "run.json"), record)
    if not record["success"]:
        raise ValueError("The source changed. Inspect the retained run files.")
    return output


def lesson_results(result: Path, model: str, output: Path) -> dict:
    import h5py
    import numpy as np

    # CLI and test imports use the same local readers.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from export_beaver_creek_may74_xs import PROFILE_NAME, extract_cross_sections
    from plot_davis_inlet_vs_pump import INLET_FLOW, PUMP_RESULTS
    from report_davis_output_interval import (
        CONDUIT_INDICES,
        NODE_ATTRS,
        NODE_INDICES,
        NODE_WSE,
        PIPE_ATTRS,
        PIPE_FLOW,
        decode,
        network_indices,
        read_series,
        result_column,
        unique_index,
    )

    steady = "Results/Steady/Output/Output Blocks/Base Output/Steady Profiles"
    attributes_path = "Results/Steady/Output/Geometry Info/Cross Section Attributes"
    profile_names_path = f"{steady}/Profile Names"
    water_surface_path = f"{steady}/Cross Sections/Water Surface"
    velocity_path = f"{steady}/Cross Sections/Additional Variables/Velocity Total"

    facts = {"datasets": {}}
    with h5py.File(result, "r") as hdf:
        if (
            not re.match(r"^HEC-RAS 7\.0\.1(?:\s|$)", decode(hdf.attrs["File Version"]))
            or decode(hdf.attrs["Units System"]) != "US Customary"
        ):
            raise ValueError("Result version or units differ.")
        message_path = "Results/Summary/Compute Messages (text)"
        messages = "\n".join(decode(value) for value in hdf[message_path][:])
        if re.search(r"(?i)aborted|unstable|fatal|error loading|error determining", messages):
            raise ValueError("Computation messages report a failure.")
        facts["compute_messages_dataset"] = message_path
        facts["compute_messages"] = messages
        plan_info = hdf["Plan Data/Plan Information"].attrs
        expected_plan = result.stem
        if decode(plan_info["Plan Filename"]) != expected_plan:
            raise ValueError("The result records a different plan filename.")
        facts["plan_information"] = {key: str(value) for key, value in plan_info.items()}
        if model == "beaver-creek":
            if "Complete Process" not in messages:
                raise ValueError("No computation completion message was found.")
            names = [decode(value) for value in hdf[profile_names_path][:]]
            if names.count(PROFILE_NAME) != 1 or len(hdf[attributes_path]) != 14:
                raise ValueError("Expected the May '74 flood profile and 14 cross sections.")
            for path, units in ((water_surface_path, "ft"), (velocity_path, "ft/s")):
                dataset = hdf[path]
                if (
                    units
                    not in [
                        decode(value)
                        for value in np.asarray(dataset.attrs.get("Variable_Unit", [])).ravel()
                    ]
                    or dataset.shape != (len(names), 14)
                    or not np.isfinite(dataset[names.index(PROFILE_NAME)]).all()
                ):
                    raise ValueError(f"Unexpected lesson dimensions, units or values: {path}")
                facts["datasets"][path] = {"shape": list(dataset.shape), "units": units}
        else:
            nodes = hdf[NODE_ATTRS][:]
            pipes = hdf[PIPE_ATTRS][:]
            node_indices = network_indices(hdf, NODE_INDICES, nodes)
            conduit_indices = network_indices(hdf, CONDUIT_INDICES, pipes)
            if hdf[NODE_WSE].shape != (217, len(node_indices)) or hdf[PIPE_FLOW].shape != (
                217,
                len(conduit_indices),
            ):
                raise ValueError("Network result columns differ from the explicit maps.")
            for path, columns, units in ((INLET_FLOW, 133, "cfs"), (PUMP_RESULTS, 5, None)):
                dataset = hdf[path]
                if (
                    dataset.shape[0] != 217
                    or (columns and dataset.shape[1] != columns)
                    or not np.isfinite(dataset[:]).all()
                ):
                    raise ValueError(f"Unexpected lesson dimensions or values: {path}")
                if units and decode(dataset.attrs["Units"]) != units:
                    raise ValueError(f"Unexpected units: {path}")
                if path == PUMP_RESULTS:
                    variable_units = [
                        [decode(value) for value in row] for row in dataset.attrs["Variable_Unit"]
                    ]
                    if variable_units != [
                        ["Flow", "cfs"],
                        ["Stage HW", "ft"],
                        ["Stage TW", "ft"],
                        ["Pump Station #1", "cfs"],
                        ["Pump Station #1", "Pumps on"],
                    ]:
                        raise ValueError("The pump columns or units differ.")
                facts["datasets"][path] = {
                    "shape": list(dataset.shape),
                    "attributes": {key: str(value) for key, value in dataset.attrs.items()},
                }
            facts["node_missing_value_coverage"] = [
                {
                    "name": decode(nodes[int(geometry_index)]["Name"]),
                    "geometry_index_zero_based": int(geometry_index),
                    "result_column_zero_based": column,
                    "missing_values": int(np.count_nonzero(~np.isfinite(hdf[NODE_WSE][:, column]))),
                }
                for column, geometry_index in enumerate(node_indices)
                if not np.isfinite(hdf[NODE_WSE][:, column]).all()
            ]
            facts["instantaneous_Pipe_14_missing_values"] = int(
                np.count_nonzero(
                    ~np.isfinite(
                        hdf[PIPE_FLOW][:, result_column(conduit_indices, unique_index(pipes, "14"))]
                    )
                )
            )
            facts["volume_accounting_messages"] = [
                line
                for line in messages.splitlines()
                if "volume" in line.casefold() or "accounting" in line.casefold()
            ]
    if model == "beaver-creek":
        frame, _, _, _ = extract_cross_sections(result, PROFILE_NAME)
        if len(frame) != 14 or not np.isfinite(frame[["wse_ft", "vel_fps"]]).all().all():
            raise ValueError("The Beaver reader did not return 14 finite cross-section results.")
        frame.drop(columns="geometry").to_csv(
            output_file(output, "beaver_creek_may74_results.csv"), index=False
        )
    else:
        frame, details = read_series(result, 600)
        if len(frame) != 217:
            raise ValueError("Expected 217 ten-minute rows over 36 hours.")
        frame.to_csv(output_file(output, "davis_selected_series.csv"), index=False)
        facts["selected_series"] = details
        facts["datasets"].update({PIPE_FLOW: {"units": "ft^3/s"}, NODE_WSE: {"units": "ft"}})
    return facts


def check(root: Path, output: Path) -> dict:
    output = below(output, root / "outputs")
    for name in (
        "check.json",
        "summary.md",
        "beaver_creek_may74_results.csv",
        "davis_selected_series.csv",
    ):
        output_file(output, name)
    record = read_json(output / "run.json")
    if record["source_code"] != provenance(root) or record["python"] != runtime(root):
        raise ValueError("The source revision or course Python differs from the run record.")
    model = record["model"]
    if (
        model not in PLANS
        or record["plan"] != PLANS[model]
        or record.get("success") is not True
        or record.get("source_unchanged") is not True
    ):
        raise ValueError("The run record does not confirm the selected lesson plan.")
    package = next(item for item in packages(root) if item["package_metadata"]["model"] == model)
    source = verify_source(root, package)
    project = below(Path(record["project"]), root / "work")
    expected_work = root / "work" / output.parent.name / model
    if (
        project.parent != expected_work.resolve()
        or project.name != Path(package["project_path"]).name
        or Path(record["source"]) != source
        or record["package"] != package
        or record["source_hashes"] != manifest(source)
    ):
        raise ValueError("Run paths or source provenance differ.")
    if record.get("work_input_hashes_after_run") != retained_inputs(
        project.parent, record["source_hashes"]
    ):
        raise ValueError(
            "Working input files changed or are missing. Preserve this run and make a new copy."
        )
    result = below(Path(record["result"]), project.parent)
    if (
        result != project.with_suffix(f".p{PLANS[model]}.hdf")
        or sha256(result) != record["result_sha256"]
        or sha256(output / "runner.json") != record["runner_sha256"]
    ):
        raise ValueError("Result or runner receipt changed.")
    child = read_json(output / "runner.json")
    if (
        child.get("success") is not True
        or child.get("result_hdf_sha256") != sha256(result)
        or child.get("plan_number") != PLANS[model]
        or Path(child["project_path"]) != project
        or Path(child["result_hdf_path"]) != result
        or record.get("returncode") != 0
    ):
        raise ValueError("Runner and setup records disagree.")
    if not record["started_epoch"] <= result.stat().st_mtime <= record["ended_epoch"] + 2:
        raise ValueError("Result is stale or has a later modification time.")
    validate_engine_info(record["executable_version_info"])
    if record["executable_version"] != "7.0.1":
        raise ValueError("Recorded executable version differs.")
    facts = lesson_results(result, model, output)
    save_json(
        output_file(output, "check.json"),
        {
            "success": True,
            "run_sha256": sha256(output / "run.json"),
            "result_sha256": sha256(result),
            "facts": facts,
            "limitation": "File and lesson data checks do not establish engineering validity.",
        },
    )
    output_file(output, "summary.md").write_text(
        f"# Lesson result check\n\nPASS: {model}, plan {PLANS[model]}.\n\nResult: {result}\n\nSources match the committed package record. The result matches the run receipt. See check.json for dataset paths, units, dimensions, messages and missing values.\n\nThese checks do not establish engineering validity. Review the native HEC-RAS results in the working copy.\n",
        encoding="utf-8",
    )
    return facts


def run_all(root: Path, ras_exe: Path) -> Path:
    """Run and check the two selected lesson plans in order."""
    runtime(root)
    output = below(root / "outputs" / new_id(), root / "outputs")
    summary = output_file(output, "run-all.json")
    text_summary = output_file(output, "FIRST_RUN_RESULTS.txt")
    output.mkdir(parents=True)
    record = {"success": False, "source_code": provenance(root), "models": []}
    print(f"Run summary: {text_summary}", flush=True)
    try:
        for model in PLANS:
            print(f"Run {model}, plan {PLANS[model]}.", flush=True)
            model_output = run(root, model, ras_exe, 900)
            model_record = read_json(model_output / "run.json")
            record["models"].append(
                {
                    "model": model,
                    "plan": PLANS[model],
                    "output": str(model_output),
                    "project": model_record["project"],
                    "result": model_record["result"],
                    "checks_passed": False,
                }
            )
            print(f"Result: {model_record['result']}\nWork project: {model_record['project']}")
            check(root, model_output)
            record["models"][-1]["checks_passed"] = True
        record["success"] = True
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as exc:
        record["error"] = str(exc)
        raise
    finally:
        save_json(output_file(output, summary.name), record)
        lines = ["Course model results", "", "PASS" if record["success"] else "FAIL"]
        for row in record["models"]:
            lines.extend(
                [
                    "",
                    f"Model: {row['model']}, plan {row['plan']}",
                    f"Lesson checks passed: {row['checks_passed']}",
                    f"Work project: {row['project']}",
                    f"Result HDF: {row['result']}",
                    f"Run evidence: {row['output']}",
                ]
            )
        if "error" in record:
            lines.extend(["", f"Failure: {record['error']}", "Keep all run files."])
        lines.extend(["", "These checks do not establish engineering validity."])
        output_file(output, text_summary.name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Model file and lesson data checks passed. Review the working models in HEC-RAS.")
    print("These checks do not establish engineering validity.")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    all_parser = sub.add_parser("run-all")
    all_parser.add_argument("--ras-exe", type=Path, default=DEFAULT_RAS_EXE)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--model", choices=PLANS, required=True)
    run_parser.add_argument("--ras-exe", type=Path, default=DEFAULT_RAS_EXE)
    run_parser.add_argument("--timeout-seconds", type=int, default=900)
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(f"Sources prepared. Receipt: {prepare(REPO)}")
        elif args.command == "run-all":
            summary = run_all(REPO, args.ras_exe)
            print(f"Models complete. Read {summary.parent / 'FIRST_RUN_RESULTS.txt'}")
        elif args.command == "run":
            print(
                f'Run complete. Use check --run "{run(REPO, args.model, args.ras_exe, args.timeout_seconds)}"'
            )
        else:
            runtime(REPO)
            check(REPO, args.run)
            print(f"Lesson data checks passed. Read {args.run / 'summary.md'}")
        return 0
    except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as exc:
        if args.command == "check":
            try:
                output = below(args.run, REPO / "outputs")
                if output.is_dir():
                    check_path = output_file(output, "check.json")
                    summary_path = output_file(output, "summary.md")
                    save_json(check_path, {"success": False, "error": str(exc)})
                    output_file(output, summary_path.name).write_text(
                        f"# Lesson result check\n\nFAIL: {exc}\n\nKeep the run files. Inspect run.json, runner.json and run.log. No engineering validity claim was made.\n",
                        encoding="utf-8",
                    )
            except (OSError, ValueError):
                pass  # An unsafe or unavailable output folder must not receive a report.
        print(f"Course setup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
