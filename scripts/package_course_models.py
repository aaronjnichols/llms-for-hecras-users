"""Stage, test, and package the two input-only course models.

ZIP creation requires a separate review tied to the staged-file hashes and successful
fresh computations. Source files under data/ are never changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import h5py
import numpy as np

REPO = Path(__file__).resolve().parents[1]
VERSION = "v0.1.1"
MODELS = {
    "beaver-creek": {
        "directory": "Example_Projects_7_0/Applications Guide/Example 2 - Beaver Creek",
        "stem": "BEAVCREK",
        "plans": ["01"],
        "files": [
            "BEAVCREK.prj",
            "BEAVCREK.p01",
            "BEAVCREK.g01",
            "BEAVCREK.g01.hdf",
            "BEAVCREK.f01",
            "BEAVCREK.rasmap",
            "BCREEK.BMP",
        ],
        "purpose": "May 1974 steady-profile cross-section export and plotting.",
    },
    "davis": {
        "directory": "Example_Projects_7_0/Pipes/Davis",
        "stem": "DavisStormSystem",
        "plans": ["02"],
        "files": [
            "DavisStormSystem.prj",
            "DavisStormSystem.p02",
            "DavisStormSystem.g02",
            "DavisStormSystem.g02.hdf",
            "DavisStormSystem.u01",
            "DavisStormSystem.u01.hdf",
            "DavisStormSystem.rasmap",
            "GIS/2871.prj",
            "Terrain/Terrain (1).hdf",
            "Terrain/Terrain (1).Davis_terrain2.tif",
            "Terrain/Terrain (1).vrt",
            "Features/Profile Lines.shp",
            "Features/Profile Lines.shx",
            "Features/Profile Lines.dbf",
            "Features/Profile Lines.prj",
        ],
        "purpose": "Pipe results, pump flows, reporting intervals, design storms, and GIS inputs.",
    },
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def below(path: Path, directory: str) -> Path:
    resolved = path.resolve()
    root = (REPO / directory).resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError(f"Choose a new directory below {root}: {resolved}")
    return resolved


def prune_mapper(path: Path) -> None:
    """Remove layers whose input files are not in the selected model package."""
    tree = ET.parse(path)
    for parent in list(tree.iter()):
        for element in list(parent):
            filename = element.get("Filename")
            if filename:
                relative = Path(filename.replace("\\", "/"))
                if relative.is_absolute() or not (path.parent / relative).is_file():
                    parent.remove(element)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def check_model_files(root: Path, model: dict[str, Any]) -> None:
    expected = set(model["files"])
    actual = set(file_hashes(root))
    if actual != expected:
        raise ValueError(
            f"Input file selection differs: missing={expected - actual}, extra={actual - expected}"
        )
    # Check actual project and plan references, not only the file allowlist.
    for path in [*root.glob("*.prj"), *root.glob("*.p[0-9][0-9]")]:
        for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"Current Plan", "Plan File", "Geom File", "Flow File"}:
                dependency = root / f"{path.stem}.{value.strip()}"
                if not dependency.is_file():
                    raise ValueError(
                        f"Missing project or plan input: {path.name}: {dependency.name}"
                    )
    for path in root.rglob("*.hdf"):
        with h5py.File(path, "r") as hdf:
            if "Results" in hdf:
                raise ValueError(f"Computed results are prohibited in input packages: {path}")
    for path in root.glob("*.rasmap"):
        for element in ET.parse(path).iter():
            filename = element.get("Filename")
            if filename and not (root / filename.replace("\\", "/")).is_file():
                raise ValueError(f"Missing Mapper input: {filename}")


def stage_inputs(stage_root: Path, ras_exe: Path) -> None:
    from ras_commander import RasPlan, init_ras_project

    stage_root = below(stage_root, "work")
    if stage_root.exists():
        raise FileExistsError(f"Use a new staging directory: {stage_root}")
    if not ras_exe.is_file():
        raise FileNotFoundError(f"HEC-RAS executable not found: {ras_exe}")
    stage_root.mkdir(parents=True)
    source_hashes = {}
    packages = {}
    for model_id, model in MODELS.items():
        source = REPO / "data" / model["directory"]
        original = file_hashes(source)
        if not original:
            raise FileNotFoundError(f"Model input directory is empty or absent: {source}")
        source_hashes[model_id] = original
        curation = stage_root / "curation" / model_id
        shutil.copytree(source, curation)
        if file_hashes(curation) != original:
            raise RuntimeError(f"The complete source copy differs: {model_id}")
        if model_id == "beaver-creek":
            ras = init_ras_project(
                curation / "BEAVCREK.prj",
                str(ras_exe),
                ras_object="new",
                load_results_summary=False,
                hide_intro=True,
                accept_tcu=False,
            )
            for number in ["02", "03", "04"]:
                RasPlan.delete_plan(number, ras_object=ras)
                RasPlan.delete_geom(number, ras_object=ras)
            RasPlan.delete_steady("02", ras_object=ras)
        package = stage_root / "inputs" / model_id
        destination = package / model["directory"]
        destination.mkdir(parents=True)
        for filename in model["files"]:
            target = destination / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(curation / filename, target)
        prune_mapper(destination / f"{model['stem']}.rasmap")
        check_model_files(destination, model)
        selected = file_hashes(destination)
        changed = [name for name, digest in selected.items() if digest != original[name]]
        allowed_changes = {f"{model['stem']}.rasmap"}
        if model_id == "beaver-creek":
            allowed_changes.add("BEAVCREK.prj")
        if set(changed) != allowed_changes:
            raise RuntimeError(f"Unexpected source transformations: {model_id}: {changed}")
        metadata = {
            "package_version": VERSION,
            "model": model_id,
            "purpose": model["purpose"],
            "source": f"data/{model['directory']}",
            "engine_for_checks": "HEC-RAS 7.0.1",
            "upstream": "USACE HEC-RAS example-project corpus supplied in the course workspace.",
            "upstream_original_archive_sha256": None,
            "source_information": "https://www.hec.usace.army.mil/software/hec-ras/download.aspx",
            "distribution_policy": "https://www.hec.usace.army.mil/software/distribution_policy.aspx",
            "terms": "https://www.hec.usace.army.mil/software/terms_and_conditions.aspx",
            "plans": model["plans"],
            "units": "US Customary",
            "extract_under": "data/",
            "files": selected,
            "original_file_sha256": {name: original[name] for name in selected},
            "changed_files": changed,
            "changes": [
                "Remove unused Beaver project plan, geometry, and flow references with RAS Commander."
                if model_id == "beaver-creek"
                else "Keep the original project, plan, geometry, and flow inputs.",
                "Remove Mapper layers for files excluded from this input-only package.",
            ],
            "excluded_source_files": sorted(set(original) - set(selected)),
            "limitations": [
                "This is a course selection, not an official USACE distribution.",
                "The original upstream archive checksum was not recorded in the source workspace.",
                "Computation checks are not calibration or engineering design validation.",
            ],
        }
        metadata_name = f"{model_id}-PACKAGE.json"
        save_json(package / metadata_name, metadata)
        (package / f"{model_id}-README.txt").write_text(
            f"{model_id} course model inputs {VERSION}\n"
            "Extract this archive under the course data/ folder.\n"
            f"Project: {model['directory']}/{model['stem']}.prj\n"
            f"Plans: {', '.join(model['plans'])}. Use HEC-RAS 7.0.1.\n"
            "Copy the complete model folder to a new work/ directory before a run.\n"
            f"Computed result files are not included. See {metadata_name} for hashes and source changes.\n",
            encoding="utf-8",
        )
        packages[model_id] = file_hashes(package)
    save_json(
        stage_root / "staging_manifest.json",
        {
            "package_version": VERSION,
            "source_hashes": source_hashes,
            "packages": packages,
        },
    )
    print(stage_root / "staging_manifest.json")


def check_staging(stage_root: Path) -> dict[str, Any]:
    stage_root = below(stage_root, "work")
    manifest = read_json(stage_root / "staging_manifest.json")
    for model_id, model in MODELS.items():
        if file_hashes(REPO / "data" / model["directory"]) != manifest["source_hashes"][model_id]:
            raise RuntimeError(f"Source files changed: {model_id}")
        package = stage_root / "inputs" / model_id
        if file_hashes(package) != manifest["packages"][model_id]:
            raise RuntimeError(f"Staged package files changed: {model_id}")
        check_model_files(package / model["directory"], model)
    return manifest


def verify_runs(stage_root: Path, evidence: Path, ras_exe: Path, timeout: int) -> None:
    check_staging(stage_root)
    input_file_hashes = {
        model_id: file_hashes(stage_root / "inputs" / model_id / model["directory"])
        for model_id, model in MODELS.items()
    }
    evidence = below(evidence, "outputs")
    if evidence.exists() or (stage_root / "run_checks").exists():
        raise FileExistsError("Use fresh run-check and evidence directories.")
    evidence.mkdir(parents=True)
    runs = []
    for model_id, model in MODELS.items():
        run_directory = stage_root / "run_checks" / model_id
        shutil.copytree(stage_root / "inputs" / model_id / model["directory"], run_directory)
        project = run_directory / f"{model['stem']}.prj"
        for plan in model["plans"]:
            receipt = evidence / f"{model_id}_p{plan}.json"
            with (evidence / f"{model_id}_p{plan}.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        str(REPO / "scripts/run_all_example_plans.py"),
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
                    cwd=REPO,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    returncode = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired as exc:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=True)
                    process.wait(timeout=30)
                    raise RuntimeError(
                        f"Run exceeded {timeout} seconds: {model_id}, plan {plan}"
                    ) from exc
            if returncode or not receipt.is_file() or not read_json(receipt).get("success"):
                raise RuntimeError(f"Fresh computation failed. Inspect {receipt} and its log.")
            hdf_path = project.with_suffix(f".p{plan}.hdf")
            with h5py.File(hdf_path, "r") as hdf:
                engine = hdf.attrs.get("File Version", b"")
                engine = engine.decode() if isinstance(engine, bytes) else str(engine)
                if "7.0.1" not in engine or "Results" not in hdf:
                    raise ValueError(f"Result engine or Results group differs: {hdf_path}")
                if model_id == "beaver-creek":
                    root = "Results/Steady/Output/Output Blocks/Base Output/Steady Profiles"
                    names = [value.decode().strip() for value in hdf[f"{root}/Profile Names"][:]]
                    if "May '74 flood" not in names:
                        raise ValueError(f"Missing course profile in {hdf_path}")
                    required = f"{root}/Cross Sections/Water Surface"
                else:
                    required = "Results/Unsteady/Output/Output Blocks/Base Output/Unsteady Time Series/Time"
                values = hdf[required][:]
                if not values.size or not np.isfinite(values).all():
                    raise ValueError(f"Empty or non-finite course dataset: {required}")
                runs.append(
                    {
                        "model": model_id,
                        "plan": plan,
                        "success": True,
                        "engine": engine,
                        "result_sha256": sha256(hdf_path),
                        "dataset": required,
                        "dataset_shape": list(values.shape),
                        "receipt": receipt.relative_to(REPO).as_posix(),
                        "duration_seconds": read_json(receipt)["duration_seconds"],
                    }
                )
    check_staging(stage_root)
    save_json(
        evidence / "run_checks.json",
        {
            "success": True,
            "stage_manifest_sha256": sha256(stage_root / "staging_manifest.json"),
            "input_file_hashes": input_file_hashes,
            "runs": runs,
            "limitations": "Fresh computation and data-access checks, not engineering validation.",
        },
    )
    print(evidence / "run_checks.json")


def require_approval(stage_root: Path, evidence: Path) -> None:
    check_staging(stage_root)
    digest = sha256(stage_root / "staging_manifest.json")
    review = read_json(evidence / "independent_review.json")
    checks = read_json(evidence / "run_checks.json")
    if review.get("approved") is not True or review.get("stage_manifest_sha256") != digest:
        raise ValueError("An independent approval for the current staged files is required.")
    current_inputs = {
        model_id: file_hashes(stage_root / "inputs" / model_id / model["directory"])
        for model_id, model in MODELS.items()
    }
    if checks.get("success") is not True or checks.get("input_file_hashes") != current_inputs:
        raise ValueError("Successful fresh computations for these staged files are required.")
    expected = {(model_id, plan) for model_id, model in MODELS.items() for plan in model["plans"]}
    actual = {(run["model"], run["plan"]) for run in checks["runs"] if run.get("success")}
    if actual != expected:
        raise ValueError("Run checks do not cover all packaged plans.")


def build_archives(stage_root: Path, evidence: Path, destination: Path) -> None:
    require_approval(stage_root, evidence)
    destination = below(destination, "outputs")
    destination.mkdir(parents=True, exist_ok=False)
    archives = []
    for model_id, model in MODELS.items():
        package = stage_root / "inputs" / model_id
        archive = destination / f"{model_id}-inputs-{VERSION}.zip"
        with ZipFile(archive, "x", compression=ZIP_DEFLATED) as zipped:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    info = ZipInfo(path.relative_to(package).as_posix(), (2026, 1, 1, 0, 0, 0))
                    info.compress_type = ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    zipped.writestr(info, path.read_bytes())
        with ZipFile(archive) as zipped:
            if zipped.testzip() is not None:
                raise RuntimeError(f"ZIP integrity check failed: {archive}")
            for name, digest in file_hashes(package).items():
                if hashlib.sha256(zipped.read(name)).hexdigest() != digest:
                    raise RuntimeError(f"ZIP member differs: {name}")
        archives.append(
            {
                "name": archive.name,
                "bytes": archive.stat().st_size,
                "sha256": sha256(archive),
                "model_files": len(model["files"]),
            }
        )
    save_json(
        destination / "release_manifest.json",
        {
            "version": VERSION,
            "created_utc": datetime.now(UTC).isoformat(),
            "archives": archives,
            "stage_manifest_sha256": sha256(stage_root / "staging_manifest.json"),
        },
    )
    for name in ["independent_review.json", "run_checks.json"]:
        shutil.copy2(evidence / name, destination / name)
    (destination / "SHA256SUMS.txt").write_text(
        "".join(f"{item['sha256']}  {item['name']}\n" for item in archives),
        encoding="ascii",
    )
    print(destination / "release_manifest.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["stage", "verify-runs", "check", "build"])
    parser.add_argument("--stage-root", type=Path, required=True)
    parser.add_argument("--ras-exe", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    stage_root = below(args.stage_root, "work")
    if args.command in {"stage", "verify-runs"} and args.ras_exe is None:
        parser.error("--ras-exe is required for staging or computation checks")
    if args.command in {"verify-runs", "build"} and args.evidence is None:
        parser.error("--evidence is required for computation checks or archive creation")
    if args.command == "stage":
        stage_inputs(stage_root, args.ras_exe.resolve())
    elif args.command == "verify-runs":
        verify_runs(stage_root, args.evidence, args.ras_exe.resolve(), args.timeout_seconds)
    elif args.command == "check":
        check_staging(stage_root)
        print("Source and staged file checks: PASS")
    elif args.command == "build":
        if args.destination is None:
            parser.error("--destination is required for archive creation")
        build_archives(stage_root, args.evidence, args.destination)


if __name__ == "__main__":
    main()
