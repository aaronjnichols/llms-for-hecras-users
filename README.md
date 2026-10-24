# LLMs for HEC-RAS Users

This repository is the working home for a student-facing add-on module to Ben Cary and Chris
Goodell's HEC-RAS On-Demand course. The module uses ChatGPT and the Codex app to help HEC-RAS
users inspect model artifacts, build small Python tools, and carry out evidence-backed agentic
workflows.

The course is Windows-first because HEC-RAS is a Windows application. Course code is Python,
and Streamlit is the default choice when an exercise needs a user interface.

## Technical baseline

- 64-bit CPython 3.13.15 (course exercises accept Python 3.13.x)
- Exact direct dependency versions in `requirements.txt`
- RAS Commander plus HDF, tabular, vector GIS, raster, plotting, and Excel libraries
- Streamlit for simple browser interfaces
- `pytest` for tests and Ruff for formatting/linting
- No LLM APIs, SDKs, API keys, model IDs, or API billing

ChatGPT and Codex are the course's working environments. Python programs created in the course
remain ordinary local tools; they do not call an LLM service themselves.

See [docs/TECHNICAL_BASELINE.md](docs/TECHNICAL_BASELINE.md) for package choices and the update
policy.

HEC-RAS model inputs are separate downloads distributed as versioned ZIP assets through GitHub
Releases. They are not included in the repository. Extract the required lesson package under
`data/`, then compute a disposable copy under `work/` to produce results. Model packages have
not been published yet.

See [docs/MODEL_DATA_WORKFLOW.md](docs/MODEL_DATA_WORKFLOW.md) for the model download layout
and student instructions for an agent-assisted model run.

## Windows setup

Install the 64-bit Python 3.13.15 release from Python.org, then run these commands in PowerShell
from the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\check_environment.py
```

Use `.\.venv\Scripts\python.exe` in place of `python` if the virtual environment is not
activated. The environment check validates both pinned versions and real imports, including the
compiled GIS libraries.

## Repository layout

| Path | Purpose |
| --- | --- |
| `data/` | Downloaded HEC-RAS model inputs; read-only after extraction and not committed |
| `docs/` | Course-wide technical decisions and supporting notes |
| `scripts/` | Setup utilities, lesson analysis tools, and controlled model runners |
| `tests/` | Automated checks for reusable Python code |
| `.agents/skills/` | Future repo-scoped Codex skills for repeatable student workflows |
| `work/` | Disposable model copies; generated locally and not committed |
| `outputs/` | Generated reports, tables, plots, and exports; not committed |

## Safety boundary

Files under `data/` are source evidence, not a scratch area. Exercises that change model inputs
or launch HEC-RAS must first make a complete disposable copy under `work/`. Generated results
belong under `outputs/`. Full rules for both humans and Codex are in [AGENTS.md](AGENTS.md).
