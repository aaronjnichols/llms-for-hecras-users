# Course setup and first model runs

Use Windows x64 with HEC-RAS 7.0.1 installed. Open HEC-RAS once. Complete its first-use steps, then close it. This lesson prepares two model copies and checks their first results. You do not need Git, Python knowledge, or an agent to complete setup.

This lesson is a draft. See [Instructor notes](COURSE_SETUP_INSTRUCTOR.md) for test status and limits.

## 1. Download the course folder

Open the [course repository](https://github.com/aaronjnichols/llms-for-hecras-users). Select **Code > Download ZIP**. In File Explorer, select **Extract All**. Open the extracted folder that contains `Setup Course.cmd` and `Run Models.cmd`.

Put this folder outside OneDrive. Use a short full path, with 80 characters or fewer. For example, use `C:\HECRAS-Course` if you can write there. Do not run the files from inside the ZIP. If you already use Git, you can clone the repository instead.

The repository ZIP contains the course code. It does not contain the model inputs. Setup downloads the separate model input release for you. You do not need to find or extract model ZIPs.

## 2. Open Setup Course.cmd

Double-click `Setup Course.cmd`. Keep the window open while setup works. Setup finds a suitable Python installation. If none exists, it installs the course Python for your Windows user. It creates the local course environment, installs the fixed course libraries, and downloads and checks the Beaver Creek and Davis inputs.

Wait for this message:

```text
SETUP COMPLETE. Next, open Run Models.cmd.
```

Setup saves a log under `outputs/setup_<id>/setup.log`. It puts checked source models under `data/`. Do not edit these files. Setup does not compute a model.

## 3. Open Run Models.cmd and review the results

Double-click `Run Models.cmd`. It computes Beaver Creek plan 01, then Davis plan 02. Each run uses a new complete copy under `work/`. Each model has a 900-second time limit. The tool stops if a run or result check fails.

Wait for `Models complete. Read` and the printed file path. Open that `FIRST_RUN_RESULTS.txt` file under `outputs/lesson00_<id>/`. Confirm that it says `PASS`. The file gives the exact working project, result HDF, and evidence paths for both models. Keep this file.

Open each listed working project in HEC-RAS 7.0.1. Check the project path. For Beaver Creek, select plan 01 and review the May '74 flood profile and cross-section results. For Davis, select plan 02 and review computation messages, volume accounting, and stage and flow plots. Compare the results with the saved check summaries. Close without saving changes.

Keep the Beaver Creek work folder and its `BEAVCREK.p01.hdf` for Lesson 04. Use the exact result path from your summary. A passing check does not establish that a model is suitable for design.

## If a step fails

- For a folder or path error, extract a new copy to a short folder outside OneDrive.
- For a download error, keep the log, check network access, then try setup again.
- For a Python, package, or source-file conflict, keep the files and send the setup log to the instructor.
- For a model error, keep the work folder and result summary. Ask the instructor to check the HEC-RAS version and failure record. Do not change model inputs to force success.

## Optional Codex instruction

Open this course folder in Codex. Use this prompt:

```text
Read AGENTS.md. Run "Setup Course.cmd" --no-pause.
If it passes, run "Run Models.cmd" --no-pause.
Report the setup log and FIRST_RUN_RESULTS.txt paths.
Stop on failure. Preserve all source files under data/.
```
