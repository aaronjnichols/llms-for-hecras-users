## Example 3: can an output interval hide the peak?

> So far we have extracted a steady-flow profile. There was no time axis in those results. Now I want to show you why the time axis matters when we move to an unsteady model.
>
> We are going to use the Davis storm-drain example. It has a pipe network connected to 2D surface-flow areas. We will start with an hourly hydrograph report, find its peak discharge, and then ask whether that report captured the peak the model produced.
>
> This is a controlled reporting experiment. The rainfall, geometry, simulation window, and computation time step stay the same. We change the interval at which HEC-RAS saves the hydrograph.

### The model and the two locations

The source project is `data/Example_Projects_7_0/Pipes/Davis/DavisStormSystem.prj`. Start from plan `p02`, **Full System ROM with Pump**, using geometry `g02` and unsteady-flow file `u01`.

The [course input download](MODEL_INPUTS.md) contains 15 Davis model files. It excludes the
original backup files and computed outputs. The historical run evidence below refers to the
earlier 26-file source folder. New runs must record hashes for the installed input package.
The selected plan, geometry, flow, event, and terrain inputs are unchanged in that package.

This is a coupled 2D and pipe-network unsteady model. The fresh HEC-RAS 7.0.1 computation identifies 2,705 computational cells in `area2`, 11 in `DS Channel`, and 133 pipe-network nodes. Both 2D areas use the diffusion-wave equation set. It is not a 1D-only pipe exercise.

Use the original hypothetical rainfall. We are not using the separate Davis design-storm comparison, and this example does not establish a design frequency for the rainfall.

| Location | What we extract | Why use it |
| --- | --- | --- |
| Davis Pipe `67`, from `O14-DMH047` to `O14-DMH037` | Discharge at the downstream end, cfs | Its hydrograph has a short peak that hourly output misses |
| Upstream node `O14-DMH047` | Water-surface elevation, ft | Its water-level maximum occurs later than the pipe's discharge maximum |
| `DS Normal`, the external boundary of the 2D `DS Channel` area | Outflow, cfs, and boundary stage, ft | Its broad peak gives us a comparison within the same model |

Pipe 67 is a circular pipe with a 2-ft diameter. Positive pipe discharge follows the modeled upstream-to-downstream direction. Keep negative values in the full hydrograph because this run includes a period of reverse flow. Here, "peak discharge" means the largest signed positive discharge, not the largest absolute value.

*On screen, locate Pipe 67 and the DS Normal boundary in the disposable model. Identify the selected ends of the pipe before showing any results.*

### Three settings that we should keep separate

> The computation interval tells HEC-RAS how often to advance its solution. The Hydrograph Output Interval controls the saved hydrograph samples we will read here. The Mapping Output Interval controls the saved mapping snapshots.
>
> Those settings serve different purposes. If I increase the computation step, I may change the numerical solution. That would answer a different question. Today I want to isolate what happens when I keep fewer hydrograph samples.

| Setting | Value in this experiment |
| --- | --- |
| Computation interval | 12 seconds in every plan |
| Hydrograph output interval | 1 hour, 15 minutes, 5 minutes, and 1 minute |
| Mapping output interval | 10 minutes in every plan |
| Detailed output interval | The source setting, `Max Profile` |
| Simulation window | 10 Jan 2000 at 12:00 through 12 Jan 2000 at 00:00, 36 hours |
| Geometry, flow file, rainfall, solver settings, and starting conditions | Same as the source plan |

The text plan represents the end of the window as `11JAN2000,2400`. That is the same instant as midnight starting 12 January.

For this fixed-step plan, the selected reporting intervals are integer multiples of the 12-second computation step. The 1-minute series is the finest fully completed reporting interval in this comparison. Its sampled peak is our reference; we do not claim that it is the exact maximum across every computation step.

HEC recommends choosing a hydrograph output interval that preserves hydrograph shape, peak, and volume. Its manual distinguishes this setting from the computation and mapping intervals. [HEC-RAS computation settings](https://www.hec.usace.army.mil/confluence/rasdocs/rasum/latest/performing-a-1d-unsteady-flow-analysis/performing-unsteady-flow-calculations/unsteady-flow-computation-settings)

### Result extraction correction, October 26, 2026

The former 42.385-ft node values belonged to `O12-DMH009`, not `O14-DMH047`.
The extraction used global geometry order directly as network result order.
The corrected extraction uses the explicit network index maps.
No hydraulic inputs changed. No new historical model runs were made for this correction.
The original receipts, HDFs, figures, and tables remain available as historical evidence.
Use the corrected figures and tables in `outputs/lesson04_davis_reporting_20261026_index_corrected/`.
The independent check is `outputs/lesson00_20261026/index-audit/independent-results.json`.
It checks mapped water surface minus depth against the global node invert elevation.
The maximum mapped residual was 0.000003815 ft. Direct global indexing gave errors up to 17.740002 ft.
This check supports the map direction. It does not establish hydraulic adequacy.

### Find the right time axis in the HDF

*On screen, open the hourly plan HDF and expand `Results/Unsteady/Output/Output Blocks`.*

> Notice that this HDF has more than one output block. For this example, we want `DSS Hydrograph Output`. We are reading that group inside the plan HDF; we do not need to parse the separate DSS file.
>
> The pipe results also appear in `Base Output`, but that block still has 10-minute samples. If we read that copy after changing the Hydrograph Output Interval, we would be testing the wrong data. A plausible dataset name is not enough. We have to identify its output block and its time axis.

Use this prefix for the hydrograph datasets:

```text
/Results/Unsteady/Output/Output Blocks/DSS Hydrograph Output/Unsteady Time Series
```

The following paths are relative to that prefix:

| Dataset | Meaning |
| --- | --- |
| `Time` | Elapsed time in days; multiply by 24 for the plotted hours |
| `Time Date Stamp` | Dates and times to check against the numeric axis |
| `Pipe Networks/Davis/Pipes/Pipe Flow DS` | Rows are times; columns are pipe conduits; units are ft³/s |
| `Pipe Networks/Davis/Nodes/Water Surface` | Rows are times; columns are pipe nodes; units are ft |
| `2D Flow Areas/DS Channel/Boundary Conditions/DS Normal` | Rows are times; the `Columns` attribute identifies Stage followed by Flow, in ft and cfs |

Find Pipe 67 by `Name` and `System Name` in `/Geometry/Pipe Conduits/Attributes`.
Read its `US Node`. Find that node by name and system in `/Geometry/Pipe Nodes/Attributes`.
These geometry tables use global row numbers. Network results use a separate column order.
Use `/Geometry/Pipe Networks/Davis/Conduit Indices` to find each conduit result column.
Use `/Geometry/Pipe Networks/Davis/Node Indices` to find each node result column.
Each map value identifies the global geometry row for that network result column.
Equal counts do not prove equal order. Use zero-based indices throughout.

| Item | Global geometry row | Network result column |
| --- | ---: | ---: |
| Pipe 67 | 65 | 65 |
| O14-DMH047, selected upstream node | 76 | 67 |
| O13-DI020, missing water-surface series | 94 | 119 |
| O13-DMH024, finite water-surface series | 119 | 2 |

Result column 76 belongs to `O12-DMH009`. Do not use it for `O14-DMH047`.
Find the records by name and follow the maps. Do not use these observed indices as a substitute.

The 36-hour hydrographs contain 37 hourly rows, 145 rows at 15 minutes, 433 at 5 minutes, and 2,161 at 1 minute. These counts include both endpoints. Each plan's Base Output time axis still has 217 rows at 10-minute intervals.

### Prompt 3

> This prompt gives the agent permission to run HEC-RAS, so I want the file boundary to be explicit. It must create a complete disposable copy before changing a plan. I also want a record of exactly what changed.

```text
Add a reporting-interval experiment for the Davis 2D and pipe-network example.

Source project: data/Example_Projects_7_0/Pipes/Davis/DavisStormSystem.prj
Template plan: p02, Full System ROM with Pump
Required engine: installed HEC-RAS 7.0.1

Treat data/ as immutable. Hash every file in the Davis source folder, copy the complete project folder to a new uniquely named directory under work/, and verify the copy before editing anything. Save scripts in scripts/ and generated evidence in a matching directory under outputs/.

Use the active course Python 3.13 environment and RAS Commander for plan cloning, interval updates, and computations. Clone four plans with Hydrograph Output Intervals of 1HOUR, 15MIN, 5MIN, and 1MIN. Apart from plan names and identifiers, change only Output Interval. Keep the 12SEC computation interval, 10MIN mapping interval, Max Profile detailed-output setting, g02 geometry, u01 flow file, complete 36-hour window, and all numerical settings unchanged. Do not change rainfall or shift the simulation start to exaggerate a sampling effect.

Run the disposable plans. Inspect the actual computation messages, full result time windows, and volume-accounting results. Stop and report any failed computation. A process exit or an HDF filename alone is not sufficient evidence.

Read the plan HDFs with h5py in read-only mode. Use the DSS Hydrograph Output/Unsteady Time Series block and its own Time and Time Date Stamp datasets. Do not substitute the Base Output time axis.

Extract Davis Pipe 67's Pipe Flow DS, the Water Surface of its upstream node O14-DMH047, and Stage and Flow at the DS Normal boundary of DS Channel. Identify the pipe and node by their geometry attributes. Map their global rows to network result columns with Conduit Indices and Node Indices. Record both indices and map paths. Inspect units and column metadata. Validate dimensions and timestamps. Preserve signed flows, including reverse flow.

Save the actual time series and a peak-comparison CSV. Find each variable's maximum and its own time of maximum. Use the maximum of the 1-minute reported samples as the sampling reference. For discharge, calculate peak shortfall in cfs and as a percentage of that reference. For water-surface elevation, show the difference in feet, not a percentage of elevation.

Plot the full Pipe 67 discharge hydrograph and upstream water level. Make a second figure zoomed around the short discharge peak, with separate panels for 1-hour, 15-minute, 5-minute, and 1-minute reporting. Show saved samples with markers, join them with straight lines, and label each reported peak. Include the 1-minute reference. Make a third figure showing outflow and stage at DS Normal.

Compare each run with the 1-minute output at identical timestamps. Also compare the fixed 10-minute mapping water-surface arrays for both 2D areas and the pipe nodes. Report any differences. Record source and result HDF hashes, plan settings, engine version, exact dataset paths, units, row counts, and computation-health evidence. Recheck the complete source hashes at the end.

Use only actual HEC-RAS outputs for the plan comparison. Do not average samples, fit a smooth curve, or generate coarse hydrographs in Python and call them rerun results. The 1-minute reference is a sampled hydrograph peak. Keep it distinct from an exact computation-step maximum, a measured real-world peak, or proof that the computation step is sufficiently small.
```

*Paste the full prompt. Start the discussion with the hourly result, then reveal the finer intervals in order.*

### Review the pipe hydrograph

> Here is the hourly result. Its largest saved discharge is 6.66 cfs. If we exported those values and took the maximum in Excel, that is the answer we would get.
>
> Now add the finer output. The peak in the 1-minute output is 10.00 cfs. The hourly report is 33.4% lower. The model passed through that higher discharge between the saved hourly points.

![Pipe 67 peak detail](../outputs/lesson04_davis_reporting_20261026_index_corrected/lesson04_davis_peak_detail.png)

All peak times in this table are on 10 Jan 2000. The percentage denominator is the peak from the 1-minute output.

| Hydrograph interval | Reported peak, cfs | Time of reported peak | Shortfall, cfs | Shortfall, % |
| --- | ---: | --- | ---: | ---: |
| 1 hour | 6.655 | 15:00:00 | 3.343 | 33.44% |
| 15 minutes | 9.543 | 15:30:00 | 0.456 | 4.56% |
| 5 minutes | 9.968 | 15:40:00 | 0.030 | 0.30% |
| 1 minute, reference | 9.999 | 15:41:00 | 0.000 | 0.00% |

```text
Peak shortfall (%) = 100 × (reference peak − reported peak) / reference peak
```

> Look at the dots in the hourly panel. The line between them is a plotting choice. It does not contain another saved result at the hidden peak. Fitting a smoother curve through those same hourly points would not recover the missing model output.
>
> Five-minute output comes close here, and one-minute output comes closer. The 5-minute peak is about 0.30% below the 1-minute peak. That is a result for this location, storm, and reporting clock. It is not proof that the 1-minute series captured the exact computation-step maximum, or a rule that one minute is sufficient everywhere.

### Review the water level and the outlet

![Pipe 67 full hydrograph and upstream water level](../outputs/lesson04_davis_reporting_20261026_index_corrected/lesson04_davis_pipe_event.png)

> The full hydrograph also shows flow reversal after the first peak. Keep the sign when you export it. Taking absolute values would change the meaning of the result.
>
> Now look at the water level. The upstream node reaches 39.887424 ft at 19:28:00, while the discharge peaks at 15:41:00. Those are different times. We find each maximum independently instead of reporting the water level at the discharge peak as the maximum water level.

| Hydrograph interval | Upstream node peak WSE, ft | WSE shortfall, ft | Outlet peak, cfs | Outlet peak shortfall, % | Outlet peak stage, ft |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 hour | 39.876392 | 0.011032 | 67.538 | 0.015% | 39.50625 |
| 15 minutes | 39.887379 | 0.000046 | 67.543 | 0.008% | 39.50631 |
| 5 minutes | 39.887379 | 0.000046 | 67.548 | 0.000% | 39.50637 |
| 1 minute, reference | 39.887424 | 0.000000 | 67.548 | 0.000% | 39.50637 |

Water-surface differences are expressed in feet. A percentage of elevation would depend on the elevation datum and is not a useful reporting-error measure here.

![DS Normal outflow and stage](../outputs/lesson04_davis_reporting_20261026_index_corrected/lesson04_davis_boundary.png)

> At the downstream boundary, the peak is broad. Hourly output reports 67.538 cfs, compared with 67.548 cfs in the 1-minute output. The shortfall is only 0.015%.
>
> So the same hourly setting gives us a reasonable peak at this outlet and misses about a third of the pipe peak. We need to check the reporting interval at the location we intend to evaluate.

### What we checked before using the example

The values above come from four completed HEC-RAS 7.0.1 runs made for this example, not from deleting points in Python. The verified project is in `work/lesson04_davis_reporting_20260905_verified/Davis/`. The source text plan declares version 6.60; the fresh result HDFs identify HEC-RAS 7.0.1 June 2026.

- All four runs finished the full 36-hour window and reported an overall volume-accounting error of 0.1296%, or 0.1845 acre-ft.
- Every recorded computation step in the selected HDF time series was 12 seconds. The reported maximum 2D water-surface corrections were 0.009974 ft in `area2` and 0.009990 ft in `DS Channel`.
- All selected discharge and stage values were finite, and date stamps agreed with the numeric time axes. Each output block had the expected row count.
- For all four extracted variables, the maximum absolute difference between each coarser run and the 1-minute reference at shared times was exactly zero in the stored arrays.
- The 10-minute mapping water surfaces for both 2D areas had zero differences. The pipe-node mapping arrays had identical finite values and identical missing-value locations. Node O13-DI020 had 217 missing mapping values in every run; it is not the selected lesson node. This provides an additional control on the hydraulic solution while the hydrograph reporting interval changes.
- The working geometry and flow text files still matched their source hashes. All 26 source files in the Davis folder retained their original hashes.

The result HDF hashes, exact paths, settings, computation messages, and comparison arrays are documented in `outputs/lesson04_davis_reporting_20261026_index_corrected/verification.json` and the accompanying CSV files. The unsuccessful 30-second and 12-second diagnostics are retained separately as `run_30SEC.json` and `run_12SEC.json`; neither contributes values to these figures or tables.

These checks support the reporting-interval comparison. They are not calibration, mesh-convergence testing, computation-step sensitivity testing, or a design-capacity assessment of the Davis system. The figures use actual HDF samples. A later native check confirmed the 10-minute selected-node maximum as 39.89 ft at 19:30. Native screenshots remain separate from these Python figures.

> The result I would carry into my own work is the review habit. Choose the location and variable that matter, inspect how quickly they change, reduce the reporting interval, and compare the peak and its timing. A reporting interval that works at the model outlet can still miss a short event in a pipe or structure upstream.
>
> We checked reporting sensitivity here. We did not establish that the 12-second computation step, mesh, pipe representation, or rainfall is adequate for a design study. Those need their own checks.

### Instructor reproduction

The implementation is in `scripts/davis_output_interval.py` and `scripts/report_davis_output_interval.py`. It uses the pinned course packages and adds no dependencies. The run script uses the existing RAS Commander runner in `scripts/run_all_example_plans.py`.

The four-interval workflow uses supported RAS Commander plan operations. During preparation, a 30-second diagnostic was rejected because it is not an integer multiple of the computation step. A 12-second diagnostic reached the end of the hydraulic calculation but failed during DSS export with an invalid-time-interval error. Neither diagnostic is used in the comparison. Keep the lesson's distinction between a sampled peak and an exact computation-step maximum explicit.

From the course repository root, with the course environment active, choose a new output directory name for each experiment:

```powershell
python scripts/davis_output_interval.py prepare --output outputs/lesson04_davis_reporting_demo

foreach ($reportInterval in @('1HOUR', '15MIN', '5MIN', '1MIN')) {
    python scripts/davis_output_interval.py run --output outputs/lesson04_davis_reporting_demo --interval $reportInterval
    if ($LASTEXITCODE -ne 0) { throw "Stop and inspect the failed HEC-RAS run." }
}

python scripts/report_davis_output_interval.py --output outputs/lesson04_davis_reporting_demo
```

The generated `experiment.json` records the assigned plan numbers. Use those assignments instead of assuming clone numbers. `verification.json`, `peak_comparison.csv`, the four `hydrographs_*.csv` files, `compute_messages_*.txt`, and the run receipts accompany the figures.

For native inspection in HEC-RAS 7.0.1, open the working project.
Use **View > Stage and Flow Hydrographs**. This opens RasPlotDriver.
Set NodeType to **Pipe Conduit Ends**. Select row **67** to show Pipe 67 endpoint flows.
Do not select **Pipe Conduits** for these Stage and Flow time series. That selection is incompatible.
Set NodeType to **Pipe Nodes**. Select **O14-DMH047** for its water surface.
The tested 10-minute output shows a maximum of **39.89 ft at 19:30**.
Select the matching plans and confirm the saved sample times in the native table.
For the outlet, select **Boundary Condition Lines** and **DS Normal**.
The native evidence screenshots are under `outputs/lesson00_20261026/screenshots/`.
[HEC-RAS stage and flow hydrographs](https://www.hec.usace.army.mil/confluence/rasdocs/rasum/latest/viewing-results/stage-and-flow-hydrographs)

The supplied figures are Python plots of the actual HDF samples, not screenshots of the native HEC-RAS plotting window.
