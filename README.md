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
Releases. They are not included in the repository. Use the Lesson 00 setup helper to verify and install the required packages under
`data/`, then compute a disposable copy under `work/` to produce results.

Download the checked [Beaver Creek and Davis input packages](https://github.com/aaronjnichols/llms-for-hecras-users/releases/tag/model-inputs-v0.1.1).
See [docs/MODEL_INPUTS.md](docs/MODEL_INPUTS.md) for installation and run steps, and
[docs/model_inputs_release.json](docs/model_inputs_release.json) for file lists and checksums.

See [docs/MODEL_DATA_WORKFLOW.md](docs/MODEL_DATA_WORKFLOW.md) for the model download layout
and student instructions for an agent-assisted model run.

## Start with Lesson 00

Use [Course setup and first model runs](docs/COURSE_SETUP.md). The student selects a local
Windows folder. Codex obtains the public course source ZIP. It records the exact revision.
It prepares Python and executes the course commands. Git and a GitHub account are not required.

Use standard 64-bit CPython 3.13.15 for the recorded environment. Compatible 3.13.x patch
releases are accepted. Use the explicit `.venv` executable for every course command.
The agent installs the environment with:

```powershell
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-dev.txt -c requirements-windows-py313.txt
.\.venv\Scripts\python.exe scripts/check_environment.py
.\.venv\Scripts\python.exe scripts/course_setup.py prepare
```

The setup helper verifies both published model packages before it installs either source.
It refuses partial or different existing source folders. The `run` command makes a complete
new work copy and requires HEC-RAS 7.0.1. The `check` command checks an explicit run folder.
Follow the guide for the sequential Beaver Creek and Davis prompts and native result review.
These checks do not establish engineering validity.

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
