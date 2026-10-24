# Course model files

## Distribution

Keep code, requirements, lesson instructions, and agent instructions in the repository.
Distribute model inputs as versioned ZIP assets attached to a GitHub Release. Give each
lesson a direct link to the required asset. Keep model inputs and computed results out of
Git source history.

Use one input package for each lesson model. Students extract the inputs and have their agent
run the selected plans in a disposable copy to produce lesson results. Students must not need
the complete example-project corpus to start the course. A separate reference-results download
can be added later as an optional fallback.

Keep each published package unchanged. Publish a new package version when its contents change.
Record these items in the repository before release:

- Package name, version, download link, byte size, and SHA-256 checksum.
- Model source, redistribution terms, and course changes to the original model.
- Required extraction location and project filename.
- Required HEC-RAS version, plan numbers, units, and lesson purpose.
- For reference results, the engine version, input-file hashes, run settings, and run logs.

See [MODEL_INPUTS.md](MODEL_INPUTS.md) for the selected models, package records, and run steps.

## Student folder layout

Students can keep the course in a local folder such as `C:\HECRAS-Course`. Open that folder
in the agent app. Download and extract the lesson files into its `data/` folder. Preserve
the paths expected by the lesson scripts. For example:

```text
C:\HECRAS-Course\
  AGENTS.md
  requirements.txt
  scripts\
  docs\
  data\
    Example_Projects_7_0\Pipes\Davis\DavisStormSystem.prj
    reference_results\davis\<package-version>\
  work\
    <unique-run-name>\Davis\
  outputs\
    <unique-run-name>\
```

The download location does not change the source-data rules in `AGENTS.md`. After extraction
and package verification, treat `data/` as fixed source material. Perform computations in a
complete copy under `work/`. Save exported tables, figures, reports, and run records under
`outputs/`. Native HEC-RAS result files remain with the model copy under `work/`.

The root `.gitignore` excludes `data/`, `work/`, `outputs/`, and release ZIP files. Keep package
download instructions and checksums in the repository.

## Package contents

An input package must contain the complete file set needed for the selected lesson plans.
Include terrain, boundary-condition data, projection data, and other referenced files when
the lesson needs them. Preserve relative paths. Resolve references to files outside the
package before release.

Do not select files only by extension. An HDF file can contain required geometry or terrain
information as well as computed results. HEC-RAS archive tools can help select plan files,
GIS data, and computed results. Check the extracted package on a clean path before release.
Run its selected plan and test each lesson task there.

## When students run HEC-RAS

| Lesson purpose | Supplied files | Student computation |
| --- | --- | --- |
| Inspect HDF data, export tables, or plot results | Complete model inputs | Run the selected plan once, then reuse its results |
| Learn to prepare and run a model | Complete model inputs and a reference run record | Run one selected plan |
| Change inputs and compare plans | Complete model inputs and baseline reference results | Run the changed plans and the baseline when required by the lesson |

Start with a short, tested model run after environment setup. Record measured run times and
disk-space needs with each package. Students can reuse the resulting files for later analysis
lessons. If reference results are supplied as a fallback, students must identify them as
supplied reference data.

## Agent instructions for one run

The following prompt is a starting instruction. Replace the bracketed fields with the
specific lesson values before giving it to a student:

```text
Read AGENTS.md and the instructions for [lesson].

Run plan [plan number] from [project path under data/] with HEC-RAS [version].
This request authorizes one computation of that plan in a new disposable copy.

Use the course Python environment. Check the installed HEC-RAS executable and version.
Verify the source package against the course manifest. Confirm that the plan and its
required files exist. If a required file, version, or setting is unclear, report it before
starting the computation.

Copy the complete required project file set to a new folder under work/. Verify that
the copy matches the source. Use the existing course runner and RAS Commander. Inspect
the runner before use. Keep the lesson's settings unchanged unless the lesson specifies
a change. Run only the selected plan. Use a bounded run time and preserve the run log.

Save a run record under outputs/ with the source and working paths, source hashes,
plan number, engine version, settings, start and end times, and result-file paths.
Check that the results belong to this run. Check the simulation time range, required
HDF datasets, and computation messages. Report warnings and incomplete checks.
Confirm that the source hashes did not change.

Report completion and computation-health evidence separately from engineering judgment.
If the run fails, retain its files and explain the failure. Do not change numerical
settings or start other plans to obtain a successful run.
```

The current `scripts/run_all_example_plans.py` has a single-plan execution command, and
`scripts/davis_output_interval.py` provides a lesson-specific prepare-and-run process.
These are useful starting points. The whole-corpus batch workflow is an instructor utility.
Before student release, provide a documented entry point for the selected lesson, configurable
paths, and a tested time limit.

A focused repository skill can later hold this procedure at
`.agents/skills/run-hec-ras-plan/SKILL.md`. It should call the reviewed runner and use the
lesson's explicit inputs. Keep source-data rules in `AGENTS.md`. Test the skill against a
successful run, a missing dependency, and a failed or timed-out run before course use.

## References

- [GitHub releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
  support downloadable assets associated with a repository release.
- [HEC-RAS Archive Project, version 6.3](https://www.hec.usace.army.mil/confluence/rasdocs/rasum/6.3/working-with-projects/archive-project)
  describes plan, GIS, and result-file archive options. Check the interface in the course version.
- [OpenAI skill guidance](https://learn.chatgpt.com/docs/build-skills)
  documents repository skills and the `SKILL.md` format.
