# Technical baseline

This baseline supports the common course tasks: HEC-RAS project operations, HDF inspection,
tabular and multidimensional analysis, vector and raster GIS, plots, Excel output, and simple
user interfaces. It remains a curated teaching stack rather than a general-purpose GIS or web
development environment.

## Python

Use 64-bit CPython 3.13.15 as the target environment for recording and final course validation.
Course code may run on another 3.13 patch release, but exercises should reject Python 3.12,
3.14, free-threaded Python builds, Conda-specific assumptions, and alternative Python
implementations unless a lesson explicitly expands support.

Python 3.13 is a deliberate middle path: it is a maintained Windows release, while the selected
scientific and Streamlit packages support it. Python 3.14 is not the course target even though
it is the newest feature series.

## Direct runtime dependencies

| Package | Pinned version | Course use |
| --- | ---: | --- |
| NumPy | 2.5.2 | Numeric arrays and calculations |
| pandas | 3.0.5 | Tables, time series, CSV, and Excel-oriented workflows |
| SciPy | 1.18.0 | Interpolation, statistics, and scientific calculations |
| Xarray | 2026.7.0 | Labeled multidimensional and time-indexed result data |
| h5py | 3.16.0 | Read-only inspection of HEC-RAS HDF files |
| RAS Commander | 0.99.1 | HEC-RAS project inspection and controlled automation |
| pywin32 | 312 | Windows COM access for native HEC-RAS plot automation |
| GeoPandas | 1.1.4 | Vector GIS data and spatial tables |
| Shapely | 2.1.2 | Geometry construction and spatial operations |
| PyProj | 3.7.2 | CRS definitions and coordinate transformations |
| Rasterio | 1.5.1 | Terrain and other geospatial raster data |
| Matplotlib | 3.11.1 | Static, exportable engineering plots |
| Pillow | 12.3.0 | Render native HEC-RAS enhanced metafiles onto PDF pages |
| Plotly | 6.9.0 | Interactive plots in Streamlit |
| Streamlit | 1.61.1 | Python-only browser interfaces |
| openpyxl | 3.1.5 | `.xlsx` reading and writing through pandas or directly |

## Development dependencies

| Package | Pinned version | Course use |
| --- | ---: | --- |
| pytest | 9.1.1 | Small automated tests and regression checks |
| Ruff | 0.16.2 | One fast formatter and linter instead of multiple tools |

`requirements.txt` and `requirements-dev.txt` are the installation sources of truth. The table
above explains the pins but does not replace them.

The direct requirement files pin the packages used by course code. The Windows constraints
file, `requirements-windows-py313.txt`, records the resolved package versions for the tested
64-bit CPython 3.13 environment. Install with both files:

```powershell
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements-dev.txt -c requirements-windows-py313.txt
```

See [COURSE_SETUP.md](COURSE_SETUP.md) for the agent-assisted setup and HEC-RAS 7.0.1 run
procedure. A resolved package list does not prove that every lesson works. Keep fresh-install,
lesson-run, and clean-Windows test coverage separate in the release evidence.

## Packages not in the baseline

- RAS Commander installs additional implementation dependencies such as Rasterstats, Rtree,
  and Pyogrio. They are available transitively but are not course-level APIs unless a lesson
  imports them directly and adds an explicit pin here.
- GDAL's standalone Python bindings are not part of the baseline. Use the binary wheels and
  higher-level interfaces provided by Rasterio, PyProj, and GeoPandas unless a specific lesson
  proves that direct GDAL access is necessary.
- OpenAI SDKs, LangChain, other agent frameworks, and all LLM APIs are out of scope. Students
  use the ChatGPT and Codex apps directly; the Python tools they build remain ordinary local
  programs with no LLM service credentials or model configuration.
- Jupyter is optional. Prefer ordinary `.py` files for Codex-driven exercises because their
  diffs, tests, and execution paths are easier for students to inspect.

## Dependency update rule

Update dependencies as a reviewed batch, not during a lesson. For each proposed update:

1. Confirm Python 3.13 and 64-bit Windows support from the package's official metadata.
2. Install into a clean virtual environment.
3. Run the environment check, Ruff, pytest, and every affected lesson.
4. Test Streamlit workflows interactively when UI behavior is affected.
5. Record intentional behavior or output changes before changing the pinned version.
