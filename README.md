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

## Start with Lesson 00

Use Windows x64 with HEC-RAS 7.0.1 installed.

1. On this GitHub repository, select **Code > Download ZIP**, then **Extract All**. Use the folder that contains `Setup Course.cmd`. Keep its full path short and outside OneDrive. Git users can clone instead.
2. Double-click `Setup Course.cmd`. Wait for `SETUP COMPLETE. Next, open Run Models.cmd.`
3. Double-click `Run Models.cmd`. Open the printed `FIRST_RUN_RESULTS.txt` path, confirm `PASS`, and review the listed working projects in HEC-RAS.

The repository contains course code. Setup downloads and verifies the separate Beaver Creek
and Davis [model input release](https://github.com/aaronjnichols/llms-for-hecras-users/releases/tag/model-inputs-v0.1.1).
It prepares Python and the pinned libraries. You do not need Git, Python commands, or an agent.
Model runs use disposable copies under `work/`. Source models under `data/` remain unchanged.

Read [Course setup and first model runs](docs/COURSE_SETUP.md) for the complete short lesson.
The lesson remains a draft. See [Instructor notes](docs/COURSE_SETUP_INSTRUCTOR.md) for test
status, implementation details, and earlier evidence. See [Model inputs](docs/MODEL_INPUTS.md)
for package details and optional manual work. Result checks do not establish engineering validity.

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
