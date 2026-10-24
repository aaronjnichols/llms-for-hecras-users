"""Run every HEC-RAS example plan against a disposable corpus copy.

This script deliberately separates preparation from execution:

1. ``prepare`` inventories and hashes the immutable source corpus, copies it under
   ``work/``, verifies the copy, and writes provenance under ``outputs/``.
2. ``plan-batches`` creates project-aware execution batches. Steady projects are packed up
   to ten plans, unsteady projects use smaller batches, and specialized projects stay alone.
3. ``run-batch`` launches one isolated Python child process per plan in one selected batch
   and updates a JSON/CSV ledger after every attempt. Successful attempts can be resumed.
4. ``run-one`` is an internal child command that initializes one project and forces one real
   HEC-RAS computation through RAS Commander.

The source tree is never passed to a mutating RAS Commander call.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "data" / "Example_Projects_7_0"
WORK_ROOT = REPO_ROOT / "work"
OUTPUT_ROOT = REPO_ROOT / "outputs"
DEFAULT_RAS_EXE = Path(r"C:\Program Files (x86)\HEC\HEC-RAS\7.0.1\Ras.exe")
PLAN_PATTERN = re.compile(r"^(?P<stem>.+)\.p(?P<number>\d{2})$", re.IGNORECASE)
FLOW_FILE_PATTERN = re.compile(r"^[fuq]\d{2}$", re.IGNORECASE)
CATEGORY_ORDER = ("steady", "unsteady_1d", "unsteady_2d", "sediment", "pipes")


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def default_batch_id() -> str:
    """Return a sortable UTC batch identifier."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def require_descendant(path: Path, parent: Path, label: str) -> Path:
    """Resolve *path* and fail unless it is below *parent*."""
    resolved = path.resolve()
    resolved_parent = parent.resolve()
    if not resolved.is_relative_to(resolved_parent) or resolved == resolved_parent:
        raise ValueError(f"{label} must be below {resolved_parent}: {resolved}")
    return resolved


def is_hec_ras_project(path: Path) -> bool:
    """Identify HEC-RAS project files without confusing GIS ``.prj`` files."""
    if path.suffix.lower() != ".prj":
        return False
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            return any(
                line.startswith("Proj Title=") for _, line in zip(range(40), stream, strict=False)
            )
    except OSError:
        return False


def read_project_title(path: Path) -> str | None:
    """Read the first HEC-RAS project title."""
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for _, line in zip(range(40), stream, strict=False):
            if line.startswith("Proj Title="):
                return line.partition("=")[2].strip()
    return None


def plan_files(project_path: Path) -> list[Path]:
    """Return plan files belonging to one project, case-insensitively."""
    matches: list[Path] = []
    for candidate in project_path.parent.iterdir():
        if not candidate.is_file():
            continue
        match = PLAN_PATTERN.match(candidate.name)
        if match and match.group("stem").casefold() == project_path.stem.casefold():
            matches.append(candidate)
    return sorted(matches, key=lambda item: item.name.casefold())


def inventory(corpus_root: Path) -> dict[str, Any]:
    """Inventory genuine HEC-RAS projects and their plans."""
    projects: list[dict[str, Any]] = []
    for project_path in sorted(corpus_root.rglob("*.prj"), key=lambda item: str(item).casefold()):
        if not is_hec_ras_project(project_path):
            continue
        plans = plan_files(project_path)
        projects.append(
            {
                "project_relative_path": project_path.relative_to(corpus_root).as_posix(),
                "project_title": read_project_title(project_path),
                "plans": [
                    {
                        "plan_relative_path": plan.relative_to(corpus_root).as_posix(),
                        "plan_number": PLAN_PATTERN.match(plan.name).group("number"),  # type: ignore[union-attr]
                    }
                    for plan in plans
                ],
            }
        )
    return {
        "project_count": len(projects),
        "runnable_project_count": sum(bool(project["plans"]) for project in projects),
        "no_plan_project_count": sum(not project["plans"] for project in projects),
        "plan_count": sum(len(project["plans"]) for project in projects),
        "projects": projects,
    }


def read_plan_value(plan_path: Path, key: str) -> str | None:
    """Read the first exact ``key=value`` setting from a plan file."""
    prefix = f"{key}="
    with plan_path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.startswith(prefix):
                return line.partition("=")[2].strip()
    return None


def classify_project(project: dict[str, Any], corpus_root: Path) -> dict[str, Any]:
    """Classify one runnable project from its plan flow-file references and path."""
    project_relative = project["project_relative_path"]
    path_parts = Path(project_relative).parts
    flow_files: list[str] = []
    plans: list[dict[str, Any]] = []
    for plan in project["plans"]:
        plan_path = corpus_root / Path(plan["plan_relative_path"])
        flow_file = read_plan_value(plan_path, "Flow File")
        if flow_file is None or not FLOW_FILE_PATTERN.fullmatch(flow_file):
            raise ValueError(f"Unrecognized Flow File in {plan_path}: {flow_file!r}")
        normalized_flow_file = flow_file.casefold()
        flow_files.append(normalized_flow_file)
        plans.append({**plan, "flow_file": normalized_flow_file})

    if path_parts and path_parts[0].casefold() == "pipes":
        category = "pipes"
    elif any(flow_file.startswith("q") for flow_file in flow_files) or any(
        "sediment" in part.casefold() for part in path_parts
    ):
        category = "sediment"
    elif path_parts and path_parts[0].casefold().startswith("2d unsteady"):
        category = "unsteady_2d"
    elif any(flow_file.startswith("u") for flow_file in flow_files):
        category = "unsteady_1d"
    elif all(flow_file.startswith("f") for flow_file in flow_files):
        category = "steady"
    else:  # Defensive: recognized flow-file prefixes should make this unreachable.
        raise ValueError(f"Could not classify project: {project_relative}")

    return {
        "project_relative_path": project_relative,
        "project_title": project["project_title"],
        "category": category,
        "plan_count": len(plans),
        "plans": plans,
    }


def build_execution_batches(
    inventory_data: dict[str, Any],
    corpus_root: Path,
    steady_cap: int = 10,
    unsteady_cap: int = 5,
) -> list[dict[str, Any]]:
    """Pack complete projects into bounded execution batches."""
    if steady_cap < 1 or unsteady_cap < 1:
        raise ValueError("Batch caps must be positive integers.")

    classified = [
        classify_project(project, corpus_root)
        for project in inventory_data["projects"]
        if project["plans"]
    ]
    by_category = {
        category: [project for project in classified if project["category"] == category]
        for category in CATEGORY_ORDER
    }
    batches: list[dict[str, Any]] = []

    def append_batch(category: str, cap: int, projects: list[dict[str, Any]]) -> None:
        plan_count = sum(project["plan_count"] for project in projects)
        batches.append(
            {
                "category": category,
                "nominal_plan_cap": cap,
                "over_cap": plan_count > cap,
                "project_count": len(projects),
                "plan_count": plan_count,
                "projects": projects,
            }
        )

    for category in CATEGORY_ORDER:
        projects = by_category[category]
        if category in {"sediment", "unsteady_2d", "pipes"}:
            for project in projects:
                append_batch(category, steady_cap, [project])
            continue

        cap = steady_cap if category == "steady" else unsteady_cap
        current: list[dict[str, Any]] = []
        current_plan_count = 0
        for project in projects:
            if current and current_plan_count + project["plan_count"] > cap:
                append_batch(category, cap, current)
                current = []
                current_plan_count = 0
            current.append(project)
            current_plan_count += project["plan_count"]
        if current:
            append_batch(category, cap, current)

    for number, batch in enumerate(batches, start=1):
        batch["execution_batch_id"] = f"B{number:03d}"

    expected_plan_keys = {
        (project["project_relative_path"], plan["plan_number"])
        for project in inventory_data["projects"]
        for plan in project["plans"]
    }
    actual_plan_keys = {
        (project["project_relative_path"], plan["plan_number"])
        for batch in batches
        for project in batch["projects"]
        for plan in project["plans"]
    }
    if actual_plan_keys != expected_plan_keys:
        raise RuntimeError("Execution batches do not cover every plan exactly once.")
    return batches


def sha256_file(path: Path) -> str:
    """Hash one file without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_manifest(root: Path) -> list[dict[str, Any]]:
    """Create a deterministic SHA-256 manifest for every file under *root*."""
    rows: list[dict[str, Any]] = []
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()), key=lambda item: str(item).casefold()
    ):
        stat = path.stat()
        rows.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "size_bytes": stat.st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def write_json_atomic(path: Path, value: Any) -> None:
    """Write JSON through a sibling temporary file and atomically replace the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def write_ledger_csv(path: Path, records: list[dict[str, Any]]) -> None:
    """Write the compact plan ledger as CSV."""
    columns = [
        "execution_batch_id",
        "category",
        "project_relative_path",
        "project_title",
        "plan_relative_path",
        "plan_number",
        "status",
        "success",
        "started_at",
        "ended_at",
        "duration_seconds",
        "return_code",
        "result_hdf_relative_path",
        "result_hdf_size_bytes",
        "exception",
        "log_relative_path",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    temporary.replace(path)


def write_execution_batches_csv(path: Path, batches: list[dict[str, Any]]) -> None:
    """Write one student-readable row per plan in the execution manifest."""
    columns = [
        "execution_batch_id",
        "category",
        "nominal_plan_cap",
        "over_cap",
        "project_relative_path",
        "project_title",
        "plan_relative_path",
        "plan_number",
        "flow_file",
    ]
    rows = []
    for batch in batches:
        for project in batch["projects"]:
            for plan in project["plans"]:
                rows.append(
                    {
                        "execution_batch_id": batch["execution_batch_id"],
                        "category": batch["category"],
                        "nominal_plan_cap": batch["nominal_plan_cap"],
                        "over_cap": batch["over_cap"],
                        "project_relative_path": project["project_relative_path"],
                        "project_title": project["project_title"],
                        "plan_relative_path": plan["plan_relative_path"],
                        "plan_number": plan["plan_number"],
                        "flow_file": plan["flow_file"],
                    }
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def prepare(batch_id: str, source_root: Path, ras_exe: Path) -> dict[str, Any]:
    """Copy and verify the source corpus for a new batch."""
    source_root = source_root.resolve()
    if source_root != SOURCE_ROOT.resolve():
        raise ValueError(f"Source root must be the repository corpus: {SOURCE_ROOT.resolve()}")
    if not ras_exe.is_file():
        raise FileNotFoundError(f"HEC-RAS executable not found: {ras_exe}")

    work_batch = require_descendant(
        WORK_ROOT / f"example_plans_{batch_id}", WORK_ROOT, "Work batch"
    )
    output_batch = require_descendant(
        OUTPUT_ROOT / f"example_plans_{batch_id}", OUTPUT_ROOT, "Output batch"
    )
    corpus_copy = work_batch / "Example_Projects_7_0"
    if work_batch.exists() or output_batch.exists():
        raise FileExistsError(f"Batch already exists: {batch_id}")

    output_batch.mkdir(parents=True)
    source_inventory = inventory(source_root)
    source_manifest = file_manifest(source_root)
    write_json_atomic(output_batch / "source_manifest.json", source_manifest)

    work_batch.mkdir(parents=True)
    shutil.copytree(source_root, corpus_copy, copy_function=shutil.copy2)
    copy_manifest = file_manifest(corpus_copy)
    write_json_atomic(output_batch / "copy_manifest.json", copy_manifest)
    copy_verified = source_manifest == copy_manifest
    if not copy_verified:
        raise RuntimeError("Disposable corpus copy did not match the source SHA-256 manifest.")

    batch = {
        "batch_id": batch_id,
        "prepared_at": utc_now(),
        "source_root": str(source_root),
        "work_batch": str(work_batch),
        "corpus_copy": str(corpus_copy),
        "output_batch": str(output_batch),
        "ras_exe": str(ras_exe.resolve()),
        "ras_exe_mtime_ns": ras_exe.stat().st_mtime_ns,
        "source_file_count": len(source_manifest),
        "source_size_bytes": sum(row["size_bytes"] for row in source_manifest),
        "copy_verified": copy_verified,
        "inventory": source_inventory,
    }
    write_json_atomic(output_batch / "batch.json", batch)
    return batch


def plan_batches(
    output_batch: Path,
    steady_cap: int = 10,
    unsteady_cap: int = 5,
) -> dict[str, Any]:
    """Create and persist the project-aware execution manifest."""
    batch = load_batch(output_batch)
    corpus_copy = require_descendant(Path(batch["corpus_copy"]), WORK_ROOT, "Corpus copy")
    batches = build_execution_batches(
        batch["inventory"],
        corpus_copy,
        steady_cap=steady_cap,
        unsteady_cap=unsteady_cap,
    )
    manifest = {
        "batch_id": batch["batch_id"],
        "created_at": utc_now(),
        "policy": {
            "keep_projects_together": True,
            "steady_plan_cap": steady_cap,
            "unsteady_1d_plan_cap": unsteady_cap,
            "specialized_batches": "one project per batch",
            "over_cap_rule": "A project may exceed a cap rather than being split.",
        },
        "execution_batch_count": len(batches),
        "project_count": sum(item["project_count"] for item in batches),
        "plan_count": sum(item["plan_count"] for item in batches),
        "category_counts": {
            category: {
                "batch_count": sum(item["category"] == category for item in batches),
                "project_count": sum(
                    item["project_count"] for item in batches if item["category"] == category
                ),
                "plan_count": sum(
                    item["plan_count"] for item in batches if item["category"] == category
                ),
            }
            for category in CATEGORY_ORDER
        },
        "batches": batches,
    }
    write_json_atomic(output_batch / "execution_batches.json", manifest)
    write_execution_batches_csv(output_batch / "execution_batches.csv", batches)
    return manifest


def summarize_runs(output_batch: Path) -> dict[str, Any]:
    """Aggregate every execution-batch ledger and verify complete plan coverage."""
    prepared = load_batch(output_batch)
    manifest_path = output_batch / "execution_batches.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Execution manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        (project["project_relative_path"], plan["plan_number"]): {
            "execution_batch_id": batch["execution_batch_id"],
            "category": batch["category"],
        }
        for batch in manifest["batches"]
        for project in batch["projects"]
        for plan in project["plans"]
    }
    records_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    missing_ledgers: list[str] = []
    for execution_batch in manifest["batches"]:
        execution_batch_id = execution_batch["execution_batch_id"]
        ledger_path = output_batch / "batch_runs" / execution_batch_id / "plan_ledger.json"
        if not ledger_path.is_file():
            missing_ledgers.append(execution_batch_id)
            continue
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        for record in ledger["records"]:
            key = (record["project_relative_path"], record["plan_number"])
            if key in records_by_key:
                raise RuntimeError(f"Duplicate plan record in aggregate ledger: {key}")
            records_by_key[key] = record

    expected_keys = set(expected)
    actual_keys = set(records_by_key)
    missing_keys = sorted(expected_keys - actual_keys)
    unexpected_keys = sorted(actual_keys - expected_keys)
    records = [records_by_key[key] for key in sorted(records_by_key)]
    category_counts = {
        category: {
            "expected": sum(value["category"] == category for value in expected.values()),
            "recorded": sum(record["category"] == category for record in records),
            "success": sum(
                record["category"] == category and record.get("success") is True
                for record in records
            ),
            "exception": sum(
                record["category"] == category and record.get("success") is not True
                for record in records
            ),
        }
        for category in CATEGORY_ORDER
    }
    summary = {
        "batch_id": prepared["batch_id"],
        "generated_at": utc_now(),
        "hec_ras_executable": prepared["ras_exe"],
        "source_root": prepared["source_root"],
        "corpus_copy": prepared["corpus_copy"],
        "copy_was_verified_at_preparation": prepared["copy_verified"],
        "execution_batch_count": manifest["execution_batch_count"],
        "expected_plan_count": len(expected),
        "record_count": len(records),
        "success_count": sum(record.get("success") is True for record in records),
        "exception_count": sum(record.get("success") is not True for record in records),
        "complete_coverage": (not missing_ledgers and not missing_keys and not unexpected_keys),
        "missing_execution_batch_ledgers": missing_ledgers,
        "missing_plan_keys": missing_keys,
        "unexpected_plan_keys": unexpected_keys,
        "category_counts": category_counts,
        "exceptions": [record for record in records if record.get("success") is not True],
        "records": records,
    }
    write_json_atomic(output_batch / "corpus_run_summary.json", summary)
    write_ledger_csv(output_batch / "corpus_plan_ledger.csv", records)
    return summary


def snapshot_recent_files(project_dir: Path, started_epoch: float) -> list[dict[str, Any]]:
    """Record files written or updated during a plan attempt."""
    rows: list[dict[str, Any]] = []
    for path in project_dir.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        if stat.st_mtime >= started_epoch - 1.0:
            rows.append(
                {
                    "relative_path": path.relative_to(project_dir).as_posix(),
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                }
            )
    return sorted(rows, key=lambda row: row["relative_path"].casefold())


def run_one(project_path: Path, plan_number: str, ras_exe: Path, result_path: Path) -> int:
    """Run and verify one plan inside the disposable corpus."""
    project_path = require_descendant(project_path, WORK_ROOT, "Project path")
    result_path = require_descendant(result_path, OUTPUT_ROOT, "Result path")
    if project_path.suffix.lower() != ".prj" or not is_hec_ras_project(project_path):
        raise ValueError(f"Not a HEC-RAS project file: {project_path}")
    if not re.fullmatch(r"\d{2}", plan_number):
        raise ValueError(f"Invalid plan number: {plan_number}")

    started_at = utc_now()
    started_epoch = time.time()
    record: dict[str, Any] = {
        "started_at": started_at,
        "plan_number": plan_number,
        "project_path": str(project_path),
        "success": False,
        "status": "failed",
    }
    exit_code = 1
    try:
        from ras_commander import RasCmdr, init_ras_project
        from ras_commander.RasBco import BcoMonitor

        def preserve_plan_logging_setting(_plan_path: Path) -> bool:
            """Keep the plan's existing logging level during bulk smoke runs."""
            return True

        # ras-commander 0.99.1 otherwise changes every plan to ``Write Detailed=1``.
        # That can generate multi-gigabyte .bco files for calibration examples. The
        # final HDF still contains the compute messages used by verify=True.
        BcoMonitor.enable_detailed_logging = staticmethod(preserve_plan_logging_setting)
        record["forced_detailed_logging"] = False

        ras_object = init_ras_project(
            project_path,
            str(ras_exe),
            ras_object="new",
            load_results_summary=False,
            hide_intro=True,
            accept_tcu=False,
        )
        result = RasCmdr.compute_plan(
            plan_number,
            ras_object=ras_object,
            force_rerun=True,
            verify=True,
            dialog_watchdog=True,
        )
        record["success"] = bool(result)
        record["status"] = "success" if result else "verification_failed"
        exit_code = 0 if result else 2
    except Exception as exc:
        record["exception"] = f"{type(exc).__name__}: {exc}"
        record["traceback"] = traceback.format_exc()

    result_hdf = project_path.with_suffix(f".p{plan_number}.hdf")
    if result_hdf.is_file():
        record["result_hdf_path"] = str(result_hdf)
        record["result_hdf_size_bytes"] = result_hdf.stat().st_size
        record["result_hdf_sha256"] = sha256_file(result_hdf)
    record["changed_files"] = snapshot_recent_files(project_path.parent, started_epoch)
    record["ended_at"] = utc_now()
    record["duration_seconds"] = round(time.time() - started_epoch, 3)
    write_json_atomic(result_path, record)
    return exit_code


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Terminate a timed-out child and any HEC-RAS processes it launched."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    else:  # pragma: no cover - the course runtime is Windows.
        process.kill()


def running_ras_process_ids(ras_exe: Path) -> list[int]:
    """Return process IDs already using the selected HEC-RAS executable."""
    if os.name != "nt":  # pragma: no cover - the course runtime is Windows.
        return []
    environment = os.environ.copy()
    environment["HECRAS_RUNNER_TARGET_EXE"] = str(ras_exe.resolve())
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            "$target = $env:HECRAS_RUNNER_TARGET_EXE; "
            "Get-Process Ras -ErrorAction SilentlyContinue | "
            "Where-Object { $_.Path -eq $target } | "
            "Select-Object -ExpandProperty Id",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not inspect running HEC-RAS processes: {result.stderr.strip()}")
    return [int(line) for line in result.stdout.splitlines() if line.strip().isdigit()]


def load_batch(output_batch: Path) -> dict[str, Any]:
    """Load a prepared batch record."""
    output_batch = require_descendant(output_batch, OUTPUT_ROOT, "Output batch")
    return json.loads((output_batch / "batch.json").read_text(encoding="utf-8"))


def run_execution_batch(
    output_batch: Path,
    execution_batch_id: str,
    timeout_seconds: int,
    resume: bool,
    fail_fast: bool,
    only_plan: str | None,
) -> dict[str, Any]:
    """Run one project-aware execution batch and maintain a durable ledger."""
    if timeout_seconds < 1:
        raise ValueError("Per-plan timeout must be a positive number of seconds.")
    batch = load_batch(output_batch)
    corpus_copy = require_descendant(Path(batch["corpus_copy"]), WORK_ROOT, "Corpus copy")
    ras_exe = Path(batch["ras_exe"]).resolve()
    existing_ras_processes = running_ras_process_ids(ras_exe)
    if existing_ras_processes:
        process_list = ", ".join(str(process_id) for process_id in existing_ras_processes)
        raise RuntimeError(
            f"HEC-RAS is already running from {ras_exe} (PID {process_list}). "
            "Close it normally and save any interactive work before running a batch."
        )
    execution_manifest_path = output_batch / "execution_batches.json"
    if not execution_manifest_path.is_file():
        raise FileNotFoundError(
            f"Execution manifest not found: {execution_manifest_path}. Run plan-batches first."
        )
    execution_manifest = json.loads(execution_manifest_path.read_text(encoding="utf-8"))
    selected = next(
        (
            item
            for item in execution_manifest["batches"]
            if item["execution_batch_id"].casefold() == execution_batch_id.casefold()
        ),
        None,
    )
    if selected is None:
        available = ", ".join(item["execution_batch_id"] for item in execution_manifest["batches"])
        raise ValueError(f"Unknown execution batch {execution_batch_id!r}. Available: {available}")
    execution_batch_id = selected["execution_batch_id"]
    if only_plan is not None and not re.fullmatch(r"\d{2}", only_plan):
        raise ValueError("--only-plan must be a two-digit HEC-RAS plan number.")
    selected_plan_keys = {
        (project["project_relative_path"], plan["plan_number"])
        for project in selected["projects"]
        for plan in project["plans"]
        if only_plan is None or plan["plan_number"] == only_plan
    }
    if not selected_plan_keys:
        raise ValueError(
            f"Plan {only_plan!r} is not present in execution batch {execution_batch_id}."
        )
    run_dir = output_batch / "batch_runs" / execution_batch_id
    ledger_json = run_dir / "plan_ledger.json"
    ledger_csv = run_dir / "plan_ledger.csv"
    logs_dir = run_dir / "logs"
    per_plan_dir = run_dir / "per_plan"
    logs_dir.mkdir(parents=True, exist_ok=True)
    per_plan_dir.mkdir(exist_ok=True)

    existing_records: list[dict[str, Any]] = []
    if resume and ledger_json.is_file():
        existing_records = json.loads(ledger_json.read_text(encoding="utf-8"))["records"]
    successful_keys = {
        (record["project_relative_path"], record["plan_number"])
        for record in existing_records
        if record.get("success") is True
    }
    records_by_key = {
        (record["project_relative_path"], record["plan_number"]): record
        for record in existing_records
    }

    attempts_total = selected["plan_count"]
    attempted_this_run = 0
    for project in selected["projects"]:
        project_relative = project["project_relative_path"]
        project_path = corpus_copy / Path(project_relative)
        for plan in project["plans"]:
            key = (project_relative, plan["plan_number"])
            if key not in selected_plan_keys:
                continue
            if resume and key in successful_keys:
                continue
            attempted_this_run += 1
            safe_id = hashlib.sha256(
                f"{project_relative}|{plan['plan_number']}".encode()
            ).hexdigest()[:16]
            result_path = per_plan_dir / f"{safe_id}.json"
            log_path = logs_dir / f"{safe_id}.log"
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "run-one",
                "--project",
                str(project_path),
                "--plan",
                plan["plan_number"],
                "--ras-exe",
                str(ras_exe),
                "--result",
                str(result_path),
            ]
            started = time.time()
            started_at = utc_now()
            with log_path.open("w", encoding="utf-8", errors="replace") as log_stream:
                process = subprocess.Popen(
                    command,
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                )
                try:
                    return_code = process.wait(timeout=timeout_seconds)
                    timed_out = False
                except subprocess.TimeoutExpired:
                    timed_out = True
                    terminate_process_tree(process)
                    return_code = 124

            if result_path.is_file():
                child = json.loads(result_path.read_text(encoding="utf-8"))
            else:
                child = {
                    "status": "timeout" if timed_out else "child_failed",
                    "success": False,
                    "exception": (
                        f"Exceeded per-plan timeout of {timeout_seconds} seconds."
                        if timed_out
                        else "Child process exited without a result record."
                    ),
                }
            result_hdf_path = child.get("result_hdf_path")
            result_hdf_relative = None
            if result_hdf_path:
                result_hdf_relative = Path(result_hdf_path).relative_to(corpus_copy).as_posix()
            record = {
                "execution_batch_id": execution_batch_id,
                "category": selected["category"],
                "project_relative_path": project_relative,
                "project_title": project["project_title"],
                "plan_relative_path": plan["plan_relative_path"],
                "plan_number": plan["plan_number"],
                "status": child.get("status", "child_failed"),
                "success": child.get("success", False),
                "started_at": child.get("started_at", started_at),
                "ended_at": child.get("ended_at", utc_now()),
                "duration_seconds": child.get("duration_seconds", round(time.time() - started, 3)),
                "return_code": return_code,
                "result_hdf_relative_path": result_hdf_relative,
                "result_hdf_size_bytes": child.get("result_hdf_size_bytes"),
                "result_hdf_sha256": child.get("result_hdf_sha256"),
                "changed_files": child.get("changed_files", []),
                "exception": child.get("exception"),
                "traceback": child.get("traceback"),
                "log_relative_path": log_path.relative_to(output_batch).as_posix(),
            }
            records_by_key[key] = record
            records = [records_by_key[item] for item in sorted(records_by_key)]
            ledger = {
                "batch_id": batch["batch_id"],
                "execution_batch_id": execution_batch_id,
                "category": selected["category"],
                "updated_at": utc_now(),
                "expected_plan_count": attempts_total,
                "record_count": len(records),
                "success_count": sum(item["success"] is True for item in records),
                "failure_count": sum(item["success"] is not True for item in records),
                "records": records,
            }
            write_json_atomic(ledger_json, ledger)
            write_ledger_csv(ledger_csv, records)
            print(
                f"[{execution_batch_id} {len(records)}/{attempts_total}] {record['status']}: "
                f"{project_relative} plan {plan['plan_number']} "
                f"({record['duration_seconds']}s)",
                flush=True,
            )
            if fail_fast and record["success"] is not True:
                print(
                    f"[{execution_batch_id}] stopping after {record['status']} "
                    "because --fail-fast is enabled.",
                    flush=True,
                )
                break
        if fail_fast and records_by_key.get(key, {}).get("success") is not True:
            break

    final_ledger = (
        json.loads(ledger_json.read_text(encoding="utf-8"))
        if ledger_json.exists()
        else {
            "batch_id": batch["batch_id"],
            "execution_batch_id": execution_batch_id,
            "category": selected["category"],
            "expected_plan_count": attempts_total,
            "record_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "records": [],
        }
    )
    final_ledger["attempted_this_run"] = attempted_this_run
    final_ledger["completed_at"] = utc_now()
    write_json_atomic(ledger_json, final_ledger)
    return final_ledger


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_parser = commands.add_parser(
        "prepare", help="Copy, hash, and inventory the source corpus."
    )
    prepare_parser.add_argument("--batch-id", default=default_batch_id())
    prepare_parser.add_argument("--source", type=Path, default=SOURCE_ROOT)
    prepare_parser.add_argument("--ras-exe", type=Path, default=DEFAULT_RAS_EXE)

    plan_parser = commands.add_parser(
        "plan-batches", help="Create project-aware execution batches."
    )
    plan_parser.add_argument("--output-batch", type=Path, required=True)
    plan_parser.add_argument("--steady-cap", type=int, default=10)
    plan_parser.add_argument("--unsteady-cap", type=int, default=5)

    summary_parser = commands.add_parser(
        "summarize", help="Aggregate every execution ledger and verify coverage."
    )
    summary_parser.add_argument("--output-batch", type=Path, required=True)

    run_parser = commands.add_parser("run-batch", help="Run one execution batch.")
    run_parser.add_argument("--output-batch", type=Path, required=True)
    run_parser.add_argument("--execution-batch", required=True)
    run_parser.add_argument("--timeout-seconds", type=int, default=2700)
    run_parser.add_argument("--resume", action="store_true")
    run_parser.add_argument("--fail-fast", action="store_true")
    run_parser.add_argument("--only-plan")

    one_parser = commands.add_parser("run-one", help=argparse.SUPPRESS)
    one_parser.add_argument("--project", type=Path, required=True)
    one_parser.add_argument("--plan", required=True)
    one_parser.add_argument("--ras-exe", type=Path, required=True)
    one_parser.add_argument("--result", type=Path, required=True)
    return parser


def main() -> int:
    """Run the requested batch operation."""
    args = build_parser().parse_args()
    if args.command == "prepare":
        batch = prepare(args.batch_id, args.source, args.ras_exe)
        print(
            json.dumps(
                {
                    "batch_id": batch["batch_id"],
                    "corpus_copy": batch["corpus_copy"],
                    "output_batch": batch["output_batch"],
                    "copy_verified": batch["copy_verified"],
                    "project_count": batch["inventory"]["project_count"],
                    "runnable_project_count": batch["inventory"]["runnable_project_count"],
                    "no_plan_project_count": batch["inventory"]["no_plan_project_count"],
                    "plan_count": batch["inventory"]["plan_count"],
                },
                indent=2,
            )
        )
        return 0
    if args.command == "run-one":
        return run_one(args.project, args.plan, args.ras_exe, args.result)
    if args.command == "plan-batches":
        manifest = plan_batches(
            args.output_batch.resolve(),
            steady_cap=args.steady_cap,
            unsteady_cap=args.unsteady_cap,
        )
        print(
            json.dumps(
                {key: value for key, value in manifest.items() if key != "batches"}, indent=2
            )
        )
        return 0
    if args.command == "run-batch":
        ledger = run_execution_batch(
            args.output_batch.resolve(),
            args.execution_batch,
            args.timeout_seconds,
            args.resume,
            args.fail_fast,
            args.only_plan,
        )
        print(
            json.dumps({key: value for key, value in ledger.items() if key != "records"}, indent=2)
        )
        return 0 if ledger["failure_count"] == 0 else 2
    if args.command == "summarize":
        summary = summarize_runs(args.output_batch.resolve())
        print(
            json.dumps(
                {key: value for key, value in summary.items() if key != "records"},
                indent=2,
            )
        )
        return 0 if summary["complete_coverage"] else 2
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
