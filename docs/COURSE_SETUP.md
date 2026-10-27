# Course setup and first model runs

Use this lesson to prepare the course folder and compute the first model copies.
Use Windows and HEC-RAS 7.0.1.
Keep the lesson at draft stage until the instructor completes the checks at the end.

## Purpose and deliverables

Set up one local course folder. Ask Codex to install the Python environment. Then ask it to obtain the
checked model inputs. Finally, ask it to compute two working copies. You do not need to type Python code.

At the end, keep these items:

- The course source revision in `course-source.json`.
- The course Python environment in `.venv/` and its environment-check report.
- Verified Beaver Creek and Davis source files under `data/`.
- A complete working copy for each computation under `work/lesson00_<id>/<model>/`.
- Setup and run records, check results, and summaries under `outputs/lesson00_<id>/`.

A run record identifies the inputs and executable. A passing check confirms the listed
file and result checks. It does not establish that a model is suitable for design.

## Terms used in this lesson

| Term | Meaning |
| --- | --- |
| Agent | Software that can read files, execute commands, and report its work after your instruction. |
| Workspace | The local folder selected for the course. |
| Python environment | The Python executable and packages used by the course. `.venv` keeps these packages local. |
| Plan HDF | A HEC-RAS file that can contain model data and computed results. An input HDF can have no computed results. |
| SHA-256 | A file checksum used to detect a change in file bytes. It does not assess engineering quality. |
| Source revision | The exact GitHub commit used for the course code. A commit identifies one saved version. |
| Receipt | A saved record of a setup or run operation and its evidence. |
| Binary wheel | A Python package file ready for installation without a compiler. |
| Authenticode | A Windows signature that identifies a software publisher and checks signed file bytes. |
| Metadata | Values that describe a file, such as its software version. |
| Finite value | A numeric value that is neither infinity nor a missing numeric result. |

## Spoken opening

> We will start with a local folder and two small models. You will give the instructions.
> The agent will install the course Python environment and execute the course commands.
>
> We will keep the downloaded inputs separate from the working copies. Each run will leave
> a record of its inputs, software version, and results. We will then open the working
> projects in HEC-RAS and compare the results with that record.
>
> A successful command is one check. It does not replace your review of a hydraulic model.

## Install the app and select the folder

These steps use the [official OpenAI app guide](https://learn.chatgpt.com/docs/app) and
[Windows guide](https://learn.chatgpt.com/docs/app/windows), checked on October 26, 2026.
The current download is named ChatGPT desktop app. It includes the Codex workspace used
in this course. Earlier course recordings can show a separate Codex app name.

1. Open the official Windows guide. Follow its ChatGPT desktop app link to Microsoft Store.
   Select the store's install control. Follow your organization's software policy.
2. Open the installed app. Sign in with your ChatGPT account. Complete sign-in yourself.
   Do not send passwords or sign-in codes to the agent.
3. In File Explorer, open your Windows user folder. Create `HEC-RAS Course` there. For example,
   `%USERPROFILE%\HEC-RAS Course` is outside the usual OneDrive Documents folder. Check the
   actual full path. Use a course root path of 80 characters or fewer. Do not use a folder that OneDrive synchronizes.
4. In the app, open that local folder as the work location. Select Codex. Select `New chat`.
   Use a local Windows session with PowerShell. No WSL setup is required.
5. Select `Ask for approval` beneath the composer. Keep the folder boundary active.
   Paste Prompt 1 below.

The official guide establishes the work-location and chat steps. It does not establish a
stable label for every folder-picker control. Use the control that opens a local folder.
Check the selected full path before you send the prompt. Do not select a cloud-only project.

You need HEC-RAS 7.0.1 for computation. Obtain it from the
[official HEC-RAS download page](https://www.hec.usace.army.mil/software/hec-ras/download.aspx).
Install it under your organization's policy. Open HEC-RAS yourself once. Review its terms.
Complete its first-run setup. Close it before the agent starts a run. If you cannot
install this version, stop before the model-run prompts and ask the instructor.

## Prompt 1: obtain the source and prepare Python

Copy the whole prompt into the selected local Codex chat. The agent must do the command work.

```text
Set up this empty local folder for the LLMs for HEC-RAS Users course on Windows.
Work only in this folder.
The only exception is the current-user Python installation described below.
Do not require Git or a GitHub account.
Do not require a code editor, Node, WSL, or LLM service credentials.
Do not change system PATH, the Python launcher, or global Python packages.

Resolve the current main commit of https://github.com/aaronjnichols/llms-for-hecras-users using public GitHub metadata.
Record its full commit SHA.
Download the public source ZIP for that exact SHA, not a moving main ZIP.
Inspect ZIP members before extraction.
Reject absolute paths, parent traversal, links, and duplicate or colliding paths.
Save the archive and its SHA-256 in a uniquely named setup evidence folder.
Find the single repository root in the ZIP.
Copy its contents into the selected folder.
Copy a file only if its destination is absent.
Do not overwrite existing files.
Stop if the folder is occupied or the archive layout differs.
Do not retain the GitHub SHA-named directory as an extra folder level.
Before package installation, check the full course root path.
It must have 80 characters or fewer.
It must be outside OneDrive.
Stop if either check fails.
Do not change Windows registry, security settings, or policy to bypass path limits.
Keep these items at the course root: AGENTS.md, requirements-dev.txt, requirements.txt, requirements-windows-py313.txt, docs/, scripts/, and tests/.
Do not add another repository directory level.

Save course-source.json at the course root.
Set repository_url to https://github.com/aaronjnichols/llms-for-hecras-users.
Set revision to the exact full commit SHA that you resolved.
Also record the archive URL and checksum in the setup evidence.
Read AGENTS.md and docs/COURSE_SETUP.md before proceeding.
Stop if required files or the tested Windows constraints file are absent.

Detect installed standard 64-bit CPython 3.13.x interpreters.
Inspect Windows Python registration.
Inspect installed-program records, PATH, and known executable locations.
A restricted PATH does not prove Python is absent.
Check the executable directly, including implementation, version, pointer width, and free-threaded status.
Do not accept a Store alias, Conda environment, free-threaded build, or another Python minor version.
Use an existing compatible interpreter if available.
Do not silently use a different interpreter.

Stop if an existing Python 3.13 installation is incompatible.
Also stop if you cannot inspect it.
Report the condition.
Do not start an installer that can repair, replace, or upgrade it.
Proceed only if no Python 3.13 installation exists.
Obtain the standard Python 3.13.15 Windows installer (64-bit) from https://www.python.org/downloads/release/python-31315/.
Download only from the official Python site.
Verify its bytes against the official release checksum.
Verify its Authenticode signature before execution.
The signature must be valid and identify the Python Software Foundation.
Save the source URLs, expected and actual checksums, and signature details.
Stop if either verification cannot be completed or differs.
Install for the current user into a new explicit location.
Use InstallAllUsers=0, PrependPath=0, Include_launcher=0, Include_test=0, and Include_pip=1.
Do not replace another Python install.
Inspect the installer log before accepting any elevation or upgrade request.
Stop if it detects a related installation or proposes an upgrade.
This rule also applies with InstallAllUsers=0 and a separate TargetDir.
Show the installer command and target in your report.
If an installer step requires my action, explain that step.
Wait for me to complete it.
Do not request blanket full access.

Use the verified executable to create .venv.
Do not use inherited system packages.
Then use only .\.venv\Scripts\python.exe for course commands.
Install with -m pip install --only-binary=:all: -r requirements-dev.txt -c requirements-windows-py313.txt.
Use binary wheels only.
Stop if a required wheel is unavailable.
Do not install compilers or upgrade or change the pinned dependencies to bypass an error.
Run scripts/check_environment.py.
Stop on any failure.
Save a short setup report.
Include exact paths, Python version, source revision, commands, verification results, and limits.
Do not download models or run HEC-RAS yet.
```

The [Python release page](https://www.python.org/downloads/release/python-31315/) identifies
the recorded Python release. The [Python Windows guide](https://docs.python.org/3.13/using/windows.html)
documents the installer options. The agent must verify the actual installer before use.
Python 3.13.15 is the recorded target, not a claim that it is the newest Python release.

Read the setup report. Confirm the selected folder, source revision, and `.venv` executable.
A download or package-install request can need specific network permission. Approve only the
identified source and operation. If the agent cannot explain a permission request, stop and
ask the instructor. Never send an instruction to bypass security software.

## Prompt 2: verify and install model inputs

```text
Read AGENTS.md.
Use .\.venv\Scripts\python.exe scripts/course_setup.py prepare from the course root.
The command must obtain both committed v0.1.1 input packages.
It must verify package sizes and SHA-256 values.
It must verify exact members and model-file hashes before it installs either source model.
Keep download and extraction work under work/.
Install only absent model folders under data/.
Reuse an existing exact matching source folder read-only.
Stop on a partial folder, conflict, extra file, unsafe ZIP member, download error, or checksum error.
Never delete, repair, or overwrite data/ to make setup pass.

Report the setup receipt path, source revision, verified package hashes, and both project paths.
Do not run HEC-RAS yet.
Explain any failure and retain its evidence.
```

Expected source project paths are:

```text
data/Example_Projects_7_0/Applications Guide/Example 2 - Beaver Creek/BEAVCREK.prj
data/Example_Projects_7_0/Pipes/Davis/DavisStormSystem.prj
```

The setup receipt is `outputs/lesson00_<id>/setup.json`. The published packages contain
inputs, not computed plan results. Baxter is a separate packaging gap for Lesson 05.
Do not assume that Prompt 2 installs Baxter.

## Prompt 3: compute and check Beaver Creek

```text
Read AGENTS.md.
Identify HEC-RAS 7.0.1 from the executable release metadata.
Retain the raw Windows version separately.
Do not infer the release from its folder name.
The 7.0.1 executable can report raw Windows versions 7.0.0.1 and 7.00.0001.
Check its release description.
Retain the complete metadata.
Confirm the computed HDF release after the run.
Use .\.venv\Scripts\python.exe scripts/course_setup.py run --model beaver-creek.
If HEC-RAS has a non-default installation location, identify its actual Ras.exe path.
Supply --ras-exe with that quoted path.
Do not guess a path or accept another HEC-RAS version.
Keep the default 900-second time limit unless I approve a specific change.

The tool must copy the complete verified Beaver Creek source folder into a new work/lesson00_<id>/beaver-creek/ folder.
It must compute plan 01 there through the existing runner.
Never compute under data/.
If the run succeeds, read the exact output run folder printed by the command.
Use .\.venv\Scripts\python.exe scripts/course_setup.py check --run "<actual output run folder>".
Do not type the placeholder literally.
Stop on a run or check failure.

Show the run.json and summary.md paths.
Show the work project and result HDF paths.
Report source hashes, executable version, completion messages, units, and check results.
Check the May '74 flood profile at all 14 cross sections.
Confirm that water-surface elevation and total velocity are finite.
Record the dataset paths and units.
Report what these checks do not establish.
Do not change numerical inputs to force success.
Do not run Davis yet.
```

The result HDF is `BEAVCREK.p01.hdf` in the reported working copy. The output run folder is
`outputs/lesson00_<id>/beaver-creek/`. Keep its `run.json` and `summary.md` with the model.
A new run uses a new identifier. Use the actual printed paths, not a previous instructor path.

## Prompt 4: compute and check Davis

Send this prompt only after the Beaver Creek checks pass.

```text
Read AGENTS.md.
Use .\.venv\Scripts\python.exe scripts/course_setup.py run --model davis with the verified HEC-RAS 7.0.1 executable.
Supply --ras-exe only if needed for its actual install location.
Keep the default 900-second time limit.
Compute only plan 02 in the new complete work copy.
Never compute under data/.

After a successful run, read the exact output run folder printed by the command.
Use .\.venv\Scripts\python.exe scripts/course_setup.py check --run "<actual output run folder>".
Stop on a run or check failure.
Do not type the placeholder literally.

Report run.json, summary.md, work project, and result HDF paths.
Check the 36-hour time range and 217 rows at 10-minute intervals.
Check finite selected series for Pipe 67, node O14-DMH047, all 133 inlet series, and pump values.
Record HDF dataset paths and units.
Use /Geometry/Pipe Networks/Davis/Node Indices to map global node rows to network result columns.
Use /Geometry/Pipe Networks/Davis/Conduit Indices for conduit columns.
Record both indices and map paths.
O14-DMH047 is global row 76 and result column 67.
Pipe 67 is global row 65 and result column 65.
Equal counts do not prove equal order.
Preserve and report missing node O13-DI020 and instantaneous Pipe 14 series.
Do not replace missing values with zeros.
Extract volume accounting and computation messages.
Report them without invented acceptance limits.
Confirm that source-file hashes remain unchanged.
Explain that these checks do not establish engineering validity.
```

The working project is `DavisStormSystem.prj`. Its plan 02 result is
`DavisStormSystem.p02.hdf`. The output run folder is `outputs/lesson00_<id>/davis/`.
Run time depends on the computer. The 900-second limit is a stop condition, not a prediction.

## Review the working projects in HEC-RAS

Open the exact `.prj` path from each successful run record in HEC-RAS 7.0.1.
Check the window's project path before you open editors. Do not open the source project.

1. For Beaver Creek, select plan 01. Review its computation messages. Open a profile plot
   and a cross-section result table for `May '74 flood`. Compare one water-surface elevation
   and one total velocity with the check output. Confirm feet and feet per second.
2. For Davis, select plan 02. Review computation messages and volume accounting.
   Use **View > Stage and Flow Hydrographs** to open RasPlotDriver.
   Set NodeType to **Pipe Conduit Ends**. Select row **67** for Pipe 67 endpoint flows.
   Do not select **Pipe Conduits** for these Stage and Flow time series.
   Set NodeType to **Pipe Nodes**. Select **O14-DMH047** for its water surface.
   The tested 10-minute output shows 39.89 ft maximum at 19:30.
   Compare the plotted time range with the 36-hour result record.
   Review the reported missing-series limits.
3. Close editors without saving. Do not change model settings during this review.
4. Ask the agent to record which native results you checked and any difference. Retain a
   screenshot with the plan and result labels visible. A screenshot of an empty app is insufficient.

## Reuse the result in Lesson 04

Keep the Beaver Creek work folder. Ask the agent to locate `BEAVCREK.p01.hdf` from its
successful `run.json`. Ask it to repeat the result check. Ask it to record the current checksum. Use that
exact HDF as the read-only input in Lesson 04. Supply its full path to the extraction prompt.
Do not search for an arbitrary file with the same name. Do not copy an instructor's HDF hash
into your report. Result files can have different hashes even when the checked values agree.

## Recovery

| Problem | Required action |
| --- | --- |
| Python is absent | Let Prompt 1 verify and install the official current-user interpreter. Stop if checksum or signature verification fails. |
| Python is incompatible | Use a verified standard x64 CPython 3.13.x executable. If an existing 3.13 install is incompatible, stop for instructor review. Do not repair or upgrade it automatically. |
| Installer detects another Python install | Stop. A current-user target can still cause an upgrade plan. Preserve the log and reuse an existing compatible 3.13.x interpreter. |
| Permission is denied | Read the exact operation and path. Approve only a required bounded action or ask the instructor. |
| Download or package installation fails | Keep the error and download evidence. Check network access. Do not change pins or security settings. |
| Package install reports a path-length error | Preserve the log. Use a new course root with a full path of 80 characters or fewer. Keep the archive contents at that root. Do not change Windows registry or policy. |
| Source ZIP has an extra folder level | Stop before setup. Select the folder with AGENTS.md at its root, or ask the agent to correct only the new extraction. |
| Existing data is partial or different | Stop. Preserve it. Use a new course folder or ask the instructor to inspect the conflict. |
| HEC-RAS is absent or the version differs | Install approved 7.0.1 or supply its actual executable path. Do not change version metadata. |
| First-run HEC-RAS terms appear | Review and complete them yourself. The agent must not accept terms for you. |
| A run times out | Keep the work copy and logs. Read the failure record before deciding whether to retry with a new copy. |
| A check fails or a result is missing | Keep the failure. Do not substitute old HDFs, zeros, or edited numerical inputs. |

## Instructor verification status

This document describes the required procedure. It does not claim a completed clean-Windows
student test. Record fresh Python bootstrap, constrained package installation, both model
runs, public-ZIP rehearsal, and native result review before course release. Keep their paths,
checksums, durations, screenshots, and limits in the lesson evidence.

Actual app installation and account sign-in have not been independently tested for this
lesson. Automated computer use cannot operate the ChatGPT or Codex app in this session.
A File Explorer folder screenshot can verify a folder path, but cannot verify app folder
selection or sign-in. A genuine clean Windows VM test remains pending.

The first fresh Python 3.13.15 package-install attempt failed because a Streamlit asset path
exceeded the Windows path limit in a deep folder with the GitHub SHA directory still present.
The failed log is `outputs/lesson00_20261026/fresh-install.log` in the instructor evidence.
The procedure now requires a short course root and archive flattening before installation.
The short-folder retry passed with fresh CPython 3.13.15. Package installation took 199.367
seconds and the environment check took 4.321 seconds. That historical candidate test suite passed all 72 tests in 6.539 seconds.
The setup helper downloaded, verified, and installed both model inputs. Its log is
`outputs/lesson00_20261026/candidate-prepare.log` in the instructor evidence.
These observations do not claim that the interactive Python installer succeeded. That test
stopped when the installer proposed an upgrade of an existing all-users installation.
The historical local candidate record is `outputs/lesson00_20261026/candidate-rehearsal.json`.
It reports `success: true`. The candidate used public revision
`4c1535384d9c21ef707656ea8a249029f74686a6` with local support files added after installation.
The record identifies those local files by checksum. This was a local candidate test.
It was not a test of the final public support files alone.

| Historical candidate operation | Duration, seconds | Result |
| --- | ---: | --- |
| Environment check | 4.120 | Passed |
| All 72 tests | 6.539 | Passed |
| Prepare inputs | 1.443 | Passed |
| Beaver Creek run command | 7.853 | Passed |
| Beaver Creek result check | 3.163 | Passed |
| Davis run command | 231.075 | Passed |
| Davis result check | 3.379 | Passed |

Ruff, format checks, and `pip check` also passed. Both run records report unchanged source
files. Both result HDF checks returned success at that stage.
The later index audit supersedes their named-node extraction facts.
The original records remain available. They do not establish corrected node identification.
These durations measure commands on the instructor computer. They are not student time limits.

The executable check retained raw Windows version `7.0.0.1` and release `7.0.1` separately.
A native Windows junction test confirmed rejection of the linked directory. Native file
symlink creation was unavailable in the test session. That native test remains unverified.

The native check confirmed the selected 10-minute node maximum as 39.89 ft at 19:30.
Screenshots are under `outputs/lesson00_20261026/screenshots/`.
The first public-source agent test passed all four prompts and 72 tests.
Its report is `work/L00 Public/outputs/rehearsal-report.md`.
Its named-node facts used the old reader. The index correction supersedes those facts.
The final public-source checks with the corrected reader passed. See the final test record below.

### Final public-source test

The corrected support code was tested at public revision
`69395ffaeaec85d4ccd2d4f01835bf80cd719e79`.
The source ZIP SHA-256 was
`add5afa0d15357f84ae01ed6815dcbe8d4585f3b016d4920ef961917e95e07ac`.
The release correction JSON and Markdown files are public and verified.
The eight original release assets remain unchanged.

A fresh agent completed all four prompts in `work/L00 Final/`.
It used a new `.venv` with registered standard CPython 3.13.5 x64.
No Python installer ran. This follows the rule to reuse a compatible installed Python 3.13.x.
All 37 downloaded source files matched the ZIP and their initial checksums after the test.
No downloaded course code changed.

The final reports are `work/L00 Final/outputs/rehearsal-report.md` and
`work/L00 Final/outputs/rehearsal-report.json`.

| Final public operation | Duration, seconds | Result |
| --- | ---: | --- |
| Binary-wheel package installation | 216.887 | Passed |
| Environment check | 22.971 | Passed |
| All 89 tests, complete command | 8.400 | Passed |
| Prepare inputs | 1.803 | Passed |
| Beaver Creek run command | 7.018 | Passed |
| Beaver Creek result check | 3.065 | Passed |
| Davis run command | 146.296 | Passed |
| Davis result check | 2.962 | Passed |

Pytest reported 7.18 seconds for its internal test run. The complete command took 8.400 seconds.
Ruff, format checks, and `pip check` passed.
Both model runs and corrected result checks passed. Sources remained unchanged.
Davis had 217 rows over 36 hours at 600-second intervals.
The mapped `O14-DMH047` maximum was 39.88738 ft at 19:30 on January 10, 2000.
All 133 inlet series, pump values, and selected node and pipe series passed finite-value checks.
The check retained 217 missing values at `O13-DI020` and 217 at instantaneous Pipe 14.
It did not replace missing values with zeros.
Volume accounting reported 0.1845 acre-feet and 0.1296 percent error. No acceptance limit was added.

A separate 1-second timeout test returned the expected failure exit code 1 in 1.689 seconds.
Its run record reports `TimeoutExpired` and unchanged sources.
It retained its log and separate working copy under
`work/L00 Final/outputs/lesson00_20261027T003841Z_86f2333b/beaver-creek/`.
That failure does not change the successful model records.

The first restricted environment attempt failed in ensurepip. A scoped permission retry passed.
The first public metadata request failed to resolve its host. A scoped network retry passed.
The report preserves both failures. These retries did not require blanket full access.

The October 26 index audit found the missing node was `O13-DI020`.
It has global row 94 and network result column 119.
`O13-DMH024` has global row 119 and result column 2. Its water-surface series is finite.
The former 42.385-ft selected-node values belonged to `O12-DMH009`.
Use the explicit index maps and corrected checks. Do not retain the former named-node claims.
Independent evidence is `outputs/lesson00_20261026/index-audit/independent-results.json`.
The original HDF files and receipts remain unchanged.
App installation, sign-in, app folder selection, and clean-Windows checks also remain pending.
Keep the lesson at draft stage.
