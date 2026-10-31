# Course setup instructor notes

The student procedure is [Course setup and first model runs](COURSE_SETUP.md). It uses two root launchers. The old four-prompt procedure is superseded. Its historical results below apply to that earlier procedure, not to a test of the new launchers.

## Launcher implementation and current test status

`Setup Course.cmd` runs the built-in Windows PowerShell 5.1 script `scripts/setup_course.ps1`. This is a bootstrap exception to the course Python rule because Python can be absent. The `-ExecutionPolicy Bypass` argument applies only to this process. It does not change the saved machine or user execution policy. Both CMD files accept `--no-pause` for agent use and retain failure exit codes.

Setup checks the course root, plain paths, Windows x64, registered Python installations, installed-program records, PATH candidates, and interpreter details. Registry checks help detect an existing Python installation before an installer can replace or upgrade it. Setup accepts standard x64 CPython 3.13.x with the GIL. It rejects incompatible or inaccessible Python 3.13 installations. Python 3.13.15 is the recording target.

If Python is absent, setup downloads only:

`https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe`

The fixed SHA-256 is `edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403`. Setup requires a valid Authenticode signature with the Python Software Foundation organization. It installs into a new unique current-user folder under `%LOCALAPPDATA%/Programs/Python/`. It uses no PATH change, launcher, file association, shortcuts, or all-users installation. It retains the installer log. See the [Python release page](https://www.python.org/downloads/release/python-31315/) and [Windows installer documentation](https://docs.python.org/3.13/using/windows.html).

All later course commands use `.venv/Scripts/python.exe`. Setup installs binary wheels from `requirements-dev.txt` with `requirements-windows-py313.txt`, runs the environment check, then calls `course_setup.py prepare`. It isolates pip from inherited Python and pip environment settings and disables pip configuration files for the setup process only. It requires package installation into the virtual environment. It verifies both versioned model packages before source installation. Direct package pins remain unchanged. Archive source revision comes from `.git_archival.txt` export substitution, or Git in a checkout.

`Run Models.cmd` calls `course_setup.py run-all`. The helper runs and checks Beaver Creek plan 01, then Davis plan 02, with a 900-second limit per model. It retains unique work copies and model records. It writes `run-all.json` and `FIRST_RUN_RESULTS.txt` under a unique `outputs/lesson00_<id>/` folder. The text file reports PASS or FAIL and exact project, result, and evidence paths. Setup logs use `outputs/setup_<id>/setup.log`.

The published launcher test passed on October 30, 2026, at revision `f7f0b579316aba034bddb1d629bc85b92c84271c`. The public ZIP export substitution supplied the exact source revision without Git. All 44 course source files and both source models remained unchanged. The environment check, Ruff, format check, pip consistency check, and all 109 tests passed. Pytest reported 39.85 seconds. Evidence is in `outputs/lesson00_simple_20261030/public-rehearsal.md` and `public-rehearsal.json`.

| Public test operation | Duration, seconds | Result |
| --- | ---: | --- |
| Setup launcher | 227.535 | Passed |
| Repeat setup | 11.564 | Passed |
| Model launcher, both models and checks | 303.774 | Passed |
| Beaver Creek plan 01 run | 17.434 | Passed |
| Davis plan 02 run | 274.033 | Passed |

The test removed Python and Git from PATH and supplied invalid inherited Python and pip settings. Setup reused registered standard x64 CPython 3.13.5. The supplied pip target did not redirect installation, and setup did not create the target folder. The completion message identified `FIRST_RUN_RESULTS.txt`. These command tests used `--no-pause`. No new native GUI review or manual double-click screenshot was made. No Python installer ran. A clean Windows test and a complete installer test remain open, so the lesson remains a draft. Optional Codex setup is not required for the two-button procedure. Computation and file checks do not establish engineering validity.

## Native result review details from the earlier procedure

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


## Preserved instructor history

The following dated evidence is retained from the prior guide. Earlier named-node facts remain superseded where stated.

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
