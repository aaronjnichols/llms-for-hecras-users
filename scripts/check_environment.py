"""Verify the active Python and the repository's direct dependency pins."""

from __future__ import annotations

import importlib
import importlib.metadata
import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PYTHON = (3, 13)
IMPORT_NAMES = {
    "pillow": "PIL",
    "pywin32": "win32api",
}


def load_pins(requirements_path: Path, seen: set[Path] | None = None) -> dict[str, str]:
    """Load exact pins, including local ``-r`` requirement files."""
    resolved_path = requirements_path.resolve()
    visited = set() if seen is None else seen
    if resolved_path in visited:
        raise ValueError(f"Circular requirements include: {resolved_path}")
    visited.add(resolved_path)

    pins: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        resolved_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line:
            continue
        if line.startswith("-r "):
            nested_path = resolved_path.parent / line[3:].strip()
            pins.update(load_pins(nested_path, visited))
            continue
        if "==" not in line:
            raise ValueError(
                f"Expected an exact package pin in {resolved_path}:{line_number}: {raw_line}"
            )
        name, version = (part.strip() for part in line.split("==", maxsplit=1))
        if not name or not version:
            raise ValueError(f"Invalid package pin in {resolved_path}:{line_number}: {raw_line}")
        pins[name] = version

    visited.remove(resolved_path)
    return pins


def check_environment() -> list[str]:
    """Return human-readable problems; return an empty list when the environment matches."""
    problems: list[str] = []
    if sys.version_info[:2] != REQUIRED_PYTHON:
        problems.append(
            "Python 3.13.x is required; "
            f"the active interpreter is {platform.python_version()} at {sys.executable}."
        )
    if platform.python_implementation() != "CPython":
        problems.append(
            f"CPython is required; the active implementation is {platform.python_implementation()}."
        )
    is_gil_enabled = getattr(sys, "_is_gil_enabled", None)
    if callable(is_gil_enabled) and is_gil_enabled() is False:
        problems.append("Use the standard GIL-enabled CPython build, not free-threaded Python.")

    for package, expected_version in load_pins(REPO_ROOT / "requirements-dev.txt").items():
        try:
            installed_version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{package}=={expected_version} is not installed.")
            continue
        if installed_version != expected_version:
            problems.append(
                f"{package}=={expected_version} is required; found {installed_version}."
            )
            continue

        import_name = IMPORT_NAMES.get(package.lower(), package.replace("-", "_"))
        try:
            importlib.import_module(import_name)
        except Exception as exc:  # Import failures can include native-library loader errors.
            problems.append(
                f"{package}=={expected_version} is installed but cannot be imported: "
                f"{type(exc).__name__}: {exc}"
            )

    return problems


def main() -> int:
    """Print a concise environment report and return a process exit code."""
    problems = check_environment()
    print(f"Python: {platform.python_version()} ({sys.executable})")
    if problems:
        print("Environment check: FAIL")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("Environment check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
