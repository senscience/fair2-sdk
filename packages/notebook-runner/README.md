# notebook-runner

Run notebooks from scratch and measure them: whether they complete, how long each cell takes, the
kernel's peak memory, the data downloaded, the dependencies installed, and the files they write.
For CI: budgets make a run fail when a notebook gets too slow or too heavy.

```
notebook-runner 10.71728/*/notebook-duckdb.ipynb --fresh-env --python 3.13 \
    --report report.json --summary "$GITHUB_STEP_SUMMARY" --max-download-mb 500
```

```
…/senscience.f2na-3dct/notebook-duckdb.ipynb: ok (43.9 s, peak 349.4 MB, install 25.5 s, downloaded 1.3 MB (sen.science 692.3 kB, pypi.org 594.6 kB), dependencies 363.7 MB)
…/senscience.v9p2-k4m1/notebook-duckdb.ipynb: ok (63.4 s, peak 695.8 MB, install 23.6 s, downloaded 38.7 MB (sen.science 38.7 MB, pypi.org 5.8 kB), dependencies 359.2 MB, wrote 6 files)
```

The exit code is 1 when a notebook fails or goes over a budget. The notebook files are never
modified; `--executed <folder>` writes the executed copies, with their outputs (figures...).

## What is measured

| | How |
|---|---|
| **Completion** | The error and traceback of every cell that fails, in `errors.runtime`. The run continues after a failure, so that the report is complete; an error after a failure says which failing cell came before it (`after_error`), since it may be a consequence (a variable never defined). `--stop-on-error` stops at the first one. A cell that times out (`--timeout`, per cell) is interrupted and reported as a `Timeout`; if the kernel dies, the next cells are reported as not run. |
| **Time** | Per cell, and in total. Cells that install packages (`%pip install`, `!pip install`, or `pip install` from Python) are recognised, and their time is also given apart. |
| **Memory** | The peak resident memory of the kernel and the processes it starts (pip...), sampled every 0.2 s. |
| **Downloads** | Through a local proxy, per host: the kernel gets `HTTP_PROXY` and `HTTPS_PROXY` pointing to it, and the processes it starts inherit them. Python's HTTP clients (urllib, requests: mlcroissant, pandas...), DuckDB, pip, `!curl` and `!wget` go through it; HTTPS as an encrypted tunnel, counted without being read. Per host, so the data (e.g. `sen.science`) and the packages (`files.pythonhosted.org`) are told apart. Not counted: clients that ignore the proxy variables, such as aiohttp without `trust_env=True` (fsspec's HTTP file system). An existing proxy (`HTTPS_PROXY`) is used upstream. |
| **Dependencies** | With `--fresh-env`: the growth of the environment's site-packages folder, i.e. what the notebook installs. |
| **Files written** | Files created or changed in the notebook's folder (its working directory, as in Jupyter). |

`--fresh-env` runs each notebook in a new virtual environment with only ipykernel, as on a first
visit (Colab, a new machine); `--python 3.13` chooses its Python (with [uv](https://docs.astral.sh/uv/),
which can fetch it). Without it, the notebook runs with the Python of the command, which then needs
a kernel: `pip install 'notebook-runner[local]'`.

## Install

Requires Python 3.11 or later.

`pip install notebook-runner` installs what drives the runs: nbclient, nbformat, jupyter-client and
psutil (about 13 MB, 18 packages). The kernel (ipykernel, with IPython: about 57 MB more) is only
needed where the notebooks run: the fresh environments install it, and `notebook-runner[local]`
adds it to run notebooks in the runner's own environment.

## Reports

`--report report.json` has one report per notebook. It starts with what ran: the notebook (path,
first heading, SHA-256 of the file), when (UTC), where (the Python and the packages of the
notebook's environment, as seen from the kernel at the end of the run; the machine's CPUs and
memory; the CI service, if any; how the environment was made), and the options of the run. For a notebook whose cell 2 reads a
missing file (tracebacks shortened):

```json
{
 "notebook": "demo.ipynb",
 "title": "Demo",
 "sha256": "3670b03d2dd1efe53a5247400086d031f37f962b65e7952224ec3313682ad04a",
 "started_at": "2026-10-21T13:07:20+00:00",
 "environment": {"label": "the environment of notebook-runner", "python": "3.12.11",
                 "executable": "…/.venv/bin/python3", "platform": "macOS-26.7.1-arm64-arm-64bit",
                 "cpus": 12, "memory_bytes": 34359738368, "ci": null,
                 "tools": {"notebook-runner": "0.1.0", "nbclient": "0.11.0"},
                 "packages": {"duckdb": "1.5.6", "ipykernel": "7.4.0", "…": "…"}},
 "options": {"cwd": "…/demo", "skip_cells": [], "skip_tags": ["skip-execution"], "skip_install": false, "timeout": 600, "stop_on_error": false,
             "count_downloads": true, "budget": null},
 "ok": false,
 "seconds": 0.42,
 "install_seconds": 0,
 "peak_memory_bytes": 146391040,
 "downloads": {"total_bytes": 0, "by_host": {}},
 "dependencies_bytes": null,
 "created": [],
 "modified": [],
 "errors": {
  "runtime": [
   {"cell": 2, "name": "IOException", "message": "IO Error: No files found that match the pattern \"missing.csv\"",
    "traceback": "…", "after_error": null},
   {"cell": 3, "name": "NameError", "message": "name 'tables' is not defined",
    "traceback": "…", "after_error": 2}
  ],
  "over_budget": []
 },
 "cells": [
  {"index": 1, "id": "a1b2c3d4", "first_line": "import duckdb", "seconds": 0.08, "install": false, "skipped": false, "skip_reason": null, "error": null},
  {"index": 2, "id": "e5f6a7b8", "first_line": "tables = con.sql('FROM read_csv(\"missing.csv\")').df()", "seconds": 0.04, "install": false, "skipped": false, "skip_reason": null,
   "error": "IOException: IO Error: No files found that match the pattern \"missing.csv\""},
  {"index": 3, "id": "c9d0e1f2", "first_line": "tables.describe()", "seconds": 0.01, "install": false, "skipped": false, "skip_reason": null,
   "error": "NameError: name 'tables' is not defined"},
  {"index": 4, "id": "a3b4c5d6", "first_line": "con.sql('SELECT 42 AS answer').df()", "seconds": 0.3, "install": false, "skipped": false, "skip_reason": null, "error": null},
  {"index": 5, "id": "e7f8a9b0", "first_line": "from IPython.display import display", "seconds": null, "install": false,
   "skipped": true, "skip_reason": "tag skip-execution", "error": null}
 ]
}
```

The command prints one line per notebook, and `--summary` writes a Markdown table of them:

```
demo.ipynb: failed in cells 2 (IOException), 3 (NameError) (0.4 s, peak 146.4 MB, downloaded 0 B, skipped cells e7f8a9b0)
```

## First visits

`--no-cache` (`no_cache=True`) runs a notebook as on a first visit: pip and uv without their
caches (`PIP_NO_CACHE_DIR`, `UV_NO_CACHE`), and mlcroissant's cache (`CROISSANT_CACHE`) and the XDG
cache folder in an empty temporary folder. With `--fresh-env`, the downloads then include the
packages: for `senscience.f2na-3dct`, 86.2 MB instead of 1.3 MB with pip's cache
(`files.pythonhosted.org` 80.9 MB, `pypi.org` 4.6 MB, `sen.science` 692.3 kB), and an install of
35.5 s instead of 25.5 s.

## Skipping cells

- Cells tagged `skip-execution` (the convention of nbclient and nbmake), e.g. widgets that need a
  frontend: always skipped. In JupyterLab, cell tags are in the property inspector (the gear icon
  of the right sidebar); in VS Code, "Add Cell Tag" in the cell's menu.
- `--skip-tag slow` (repeatable): the cells with other tags.
- `--skip-cells pdb-viewer,3f2a9c1e`: by cell id, the `id` of each cell in the notebook file
  (nbformat 4.5), which doesn't change when cells are added or moved, unlike their position. An id
  that isn't in the notebook is an error. The report gives each cell's `id` next to its `index`.
- `--skip-install`: leaves out the install lines, and skips the cells that install from Python,
  for an environment that already has the dependencies.
- Colab-only lines (`!sudo`, `!apt-get`) are always left out: they would block or fail elsewhere.

## Budgets

`--max-seconds`, `--max-memory-mb`, `--max-download-mb`, `--max-dependencies-mb`: above them, the
run fails even if the notebook completes, so that CI notices a notebook getting heavier. The
limits exceeded are listed by name in `errors.over_budget` (e.g. `["max_seconds"]`): their values
are in `options.budget`, and the measured values in the report.

## From Python

```python
import notebook_runner

with notebook_runner.fresh_environment("3.13") as python:
    report = notebook_runner.run(
        "notebook.ipynb", python=python, budget=notebook_runner.Budget(max_seconds=300)
    )
report.ok, report.seconds, report.downloads.total_bytes, report.created
```

`run()` also takes the notebook itself, as a dict (an `nbformat` NotebookNode, or `json.loads`
of a notebook), e.g. one generated in memory. It isn't modified. The report's `notebook` is then
`"<in memory>"`, its `sha256` is that of nbformat's serialization of the notebook, and the notebook
runs in a new empty folder, removed after the run (or in `cwd=`); the files it writes there are
still listed in the report.

```python
report = notebook_runner.run(generated, python=python, budget=budget, environment="sandbox")
```

## Untrusted notebooks

notebook-runner measures notebooks, it doesn't isolate them: a notebook runs with the rights of the
user running it, can read its files and environment variables, and reach the network. A fresh
environment separates the packages, not the process. To run notebooks you didn't write (generated
by an LLM, contributed), run notebook-runner in a sandbox: a container without credentials, with
CPU, memory and time limits and, if possible, network access limited to the data hosts.

