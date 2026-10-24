# LLMs for HEC-RAS Users

This repository supports a student-facing course about using ChatGPT and the Codex app
to build small tools and perform reviewable agentic tasks around HEC-RAS.

## Priorities

1. Protect model data and preserve provenance.
2. Prefer code a HEC-RAS user can read, run, and explain.
3. Keep setup consistent across student machines.
4. Make engineering evidence visible; never replace engineering judgment with an AI claim.

## Supported stack

- Target Windows and 64-bit CPython 3.13. Use Python 3.13.15 for the recorded course
  environment and accept only Python 3.13.x in course exercises.
- Use `.venv\Scripts\python.exe` for course commands. Do not silently use another Python
  installation.
- Use Python for course tools unless a lesson explicitly documents a justified exception.
- Use Streamlit for browser-based interfaces. Do not introduce a JavaScript or Node build
  system for a course exercise.
- Use RAS Commander for supported HEC-RAS project operations instead of rebuilding its
  functionality in one-off scripts. Keep calls small enough for students to inspect.
- Use GeoPandas/Shapely/PyProj for vector and coordinate-reference-system work, and Rasterio
  for raster work. Make units and CRS explicit before calculating distance, area, or volume.
- Use the standard library first. Direct third-party dependencies must be pinned in
  `requirements.txt`; development-only dependencies belong in `requirements-dev.txt`.
- Do not add packages opportunistically. Explain the student-facing need, check Python 3.13
  and Windows support, pin the version, and update `docs/TECHNICAL_BASELINE.md`.
- This course uses the ChatGPT and Codex apps only. Do not add OpenAI SDKs, LLM API clients,
  model IDs, API keys, token accounting, or API-billing instructions.

## HEC-RAS data safety

- Treat everything under `data/` as immutable source material. Read it; never edit, rename,
  delete, recompute, or overwrite it.
- Put disposable model copies in `work/` and generated tables, figures, reports, or exports in
  `outputs/`. Both locations are intentionally ignored by version control.
- Before changing any model input, copy the complete required project file set to a uniquely
  named directory under `work/`. Preserve the source filenames and record the source path.
- Open HDF files read-only by default (`h5py.File(path, "r")`). Modes `r+`, `a`, and `w` are
  prohibited for files under `data/`.
- Never launch a HEC-RAS computation against the source corpus. A run must use a disposable
  copy and must state the HEC-RAS version used.
- Any RAS Commander call capable of changing project files, launching HEC-RAS, or creating
  model-side outputs must target a disposable project under `work/`, never `data/`.
- Do not call a parser, script, launcher, or successful process exit an engineering
  validation. Report what was checked, what was not checked, and where the evidence came from.

## Course code conventions

- Favor small functions, `pathlib.Path`, type hints, and explicit inputs and outputs.
- Keep lesson inputs configurable. Do not depend on an instructor's dated working folder or
  machine-specific installation path.
- Keep lesson code local and linear before extracting abstractions. Avoid frameworks,
  inheritance, or configuration layers that do not directly help the lesson.
- Use clear domain names and include units in variable or column names when ambiguity is
  possible, such as `flow_cfs` or `elevation_ft`.
- Fail with actionable messages. Do not use bare `except`, silent fallbacks, or fabricated
  values to keep a demo running.
- Keep secrets out of source files, notebooks, logs, screenshots, and examples. Course
  exercises must not require LLM service credentials.
- Every generated artifact must be reproducible from committed code plus identified source
  data. Record source paths, relevant HDF dataset paths, and assumptions in the output or its
  accompanying summary.

## Agent workflow

1. Inspect the relevant files and nearby lesson material before proposing or editing code.
2. State assumptions when HEC-RAS version, units, plan, geometry, or result context is unclear.
3. Make the smallest change that completes the lesson objective.
4. Preserve student-written work and unrelated changes.
5. Verify with the commands below and report any check that could not run.
6. For engineering interpretations, separate extracted facts, calculated results, assumptions,
   and recommendations.

## Verification

From the repository root, use the course environment:

```powershell
.\.venv\Scripts\python.exe scripts/check_environment.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
```

For a Streamlit lesson, also start the documented app and test its primary workflow with the
lesson's disposable sample copy. Do not treat a page load alone as functional verification.

## Repository skills

Reusable course workflows belong at `.agents/skills/<skill-name>/SKILL.md`. Keep each skill
focused on one recognizable student task. Put stable repository-wide rules here in
`AGENTS.md`; do not duplicate them in every skill.
