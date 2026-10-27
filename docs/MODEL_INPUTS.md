# Course model input downloads

The current examples use two models from the local USACE HEC-RAS example-project corpus.
The input packages contain no computed plan results. Use HEC-RAS 7.0.1 for the checked course
runs. Preserve all source files under `data/`. Compute a complete copy under `work/`.

| Package | Plans to compute | Course use |
| --- | --- | --- |
| Beaver Creek | 01, Press/Weir Method | Export and plot the May 1974 cross-section results |
| Davis storm system | 02, Full System ROM with Pump | Inspect pipe and pump results; prepare reporting-interval, storm, and GIS exercises |

The whole-corpus runner is an instructor utility. Students do not need the other example
projects to use the current course scripts. The Davis storm and reporting-interval scripts
create their new lesson plans in working copies. Those generated plans are not package inputs.

## Install the inputs

1. Open the course repository folder in the agent app.
2. Download the required model ZIP from the model-inputs release. Use the links, byte sizes,
   and SHA-256 values recorded in `model_inputs_release.json` beside this document.
3. Verify the ZIP checksum before extraction. PowerShell can read it with
   `Get-FileHash -Algorithm SHA256 <downloaded-zip>`.
4. Extract the ZIP under the repository's `data/` folder. Preserve its folder structure.
   Do not extract over an existing model folder. Use a fresh course folder for a new package
   version so that the old source files remain unchanged.
5. Check each extracted model file against its package JSON. It contains the file hashes.

Expected project paths after extraction:

```text
data/Example_Projects_7_0/Applications Guide/Example 2 - Beaver Creek/BEAVCREK.prj
data/Example_Projects_7_0/Pipes/Davis/DavisStormSystem.prj
```

Each package has unique metadata filenames at the extraction root. Both packages can be
installed under the same `data/` folder without overwriting each other's metadata.

## Produce lesson results

Ask the agent to read `AGENTS.md`, verify the package, and copy the complete selected model
folder into a new directory under `work/`. Each plan must run against that copy. Record the
source path, source-file hashes, plan number, executable path and version, run times, logs,
and result-file locations under `outputs/`.

The existing runner accepts one selected plan. For example, after a verified copy to
`work/beaver_first_run/` and after checking the installed executable path:

```powershell
.\.venv\Scripts\python.exe scripts/run_all_example_plans.py run-one `
  --project 'work/beaver_first_run/BEAVCREK.prj' `
  --plan 01 `
  --ras-exe 'C:\Program Files (x86)\HEC\HEC-RAS\7.0.1\Ras.exe' `
  --result 'outputs/beaver_first_run/plan01.json'
```

For Beaver Creek, compute plan 01 only. For Davis, select plan 02 from
the copied `DavisStormSystem.prj`. An agent that calls the runner must use a time limit and
retain the log. The packaging check uses a 900-second limit per plan. This limit is not a
prediction of run time on a student's computer.

Use the result HDFs from that new working copy as explicit inputs to the plotting and export
scripts. Some older scripts still have instructor-specific working-folder defaults. Do not
create that old folder structure to satisfy a default. Supply the lesson's actual paths or
update the script inputs as part of the lesson.

## What the packages retain

- Beaver Creek contains one selected plan, its geometry text and HDF files, its
  steady-flow file, the project and Mapper files, and the bridge photograph referenced
  by the geometry. The source has no defined CRS. Preserve its coordinates; do not assign a
  guessed EPSG code or use them for geographic distance or area calculations.
- Davis contains the selected plan, project, geometry text and HDF, unsteady-flow text and
  event HDF, Mapper file, terrain HDF/GeoTIFF/VRT, projection, and profile-line shapefile set.
  The event HDF is an input. It is not a computed plan-result file.

The fresh Davis check found missing result series at node `O13-DI020` and at Pipe `14`.
That pipe uses the instantaneous modeling approach and has no pipe-cell results. The pipe
screening script reports this condition. Preserve missing values and their coverage flags.
Do not replace them with zeros.
Read `/Geometry/Pipe Networks/Davis/Node Indices` before selecting node result columns.
Read `/Geometry/Pipe Networks/Davis/Conduit Indices` before selecting conduit result columns.
These maps connect network columns to global geometry rows. Equal counts do not prove equal order.
The selected `O14-DMH047` is global row 76 and result column 67.
The missing `O13-DI020` is global row 94 and result column 119.
`O13-DMH024` is global row 119 and result column 2. Its results are finite.
An October 26, 2026 extraction correction replaced the former missing-node attribution.
It did not change model inputs or package hashes. See the release record's correction link. The selected lesson node `O14-DMH047` and all 133 inlet-flow
series have finite values in the checked run. These checks do not establish design suitability.

The package JSON lists every retained file and its source hash. It also lists exclusions.
Source transformations remove unused Beaver project references and Mapper layers for excluded
files. Selected plan, flow, geometry, terrain, and event data remain byte-for-byte copies of
the local source files. No software executables are included.

## Instructor reproduction and review

The package script has separate stages. Use a new staging folder and a new evidence folder
for each candidate. The first command copies complete source projects before it changes
project or Mapper references in disposable copies:

```powershell
.\.venv\Scripts\python.exe scripts/package_course_models.py stage `
  --stage-root work/model_inputs_candidate `
  --ras-exe 'C:\Program Files (x86)\HEC\HEC-RAS\7.0.1\Ras.exe'

.\.venv\Scripts\python.exe scripts/package_course_models.py verify-runs `
  --stage-root work/model_inputs_candidate `
  --evidence outputs/model_inputs_checks `
  --ras-exe 'C:\Program Files (x86)\HEC\HEC-RAS\7.0.1\Ras.exe'
```

An independent reviewer must inspect the source selection, staged references, hashes,
computation receipts, and lesson data checks before archive creation. The reviewer writes
`independent_review.json` in the evidence folder. It must contain `approved: true` and the
SHA-256 of `staging_manifest.json` as `stage_manifest_sha256`. Do not approve a candidate only
because a process returned success. Retain the reviewer's name, checks, warnings, and limits.

After that review:

```powershell
.\.venv\Scripts\python.exe scripts/package_course_models.py build `
  --stage-root work/model_inputs_candidate `
  --evidence outputs/model_inputs_checks `
  --destination outputs/model_inputs_release
```

The build checks the source and staged hashes again. It requires successful fresh runs for
all selected plans and the independent approval. It verifies ZIP members against the staged
file hashes and writes archive checksums. It excludes the run-check folders from the ZIPs.

The source archive's original upstream checksum was not recorded in this workspace. Package
provenance therefore starts at the identified local source files. See the package JSON for
USACE source and terms links. These are course selections, not official USACE releases.
Computation and file-access checks do not establish model calibration or design suitability.
