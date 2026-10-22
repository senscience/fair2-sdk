"""Runs a notebook from its first cell to its last, and measures it.

The report says whether the notebook completes, and otherwise the error of every cell that fails
(the run continues after a failure, unless asked to stop). It also gives how long each cell
takes, the install cells included, the peak memory of the kernel and its subprocesses, the data
downloaded (`measure`: through a local proxy, per host), the size of the installed dependencies,
and the files the notebook creates or changes in its folder. Budgets make a run fail when it gets
too heavy.

The notebook file is never modified.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

import nbformat
import psutil
from jupyter_client.kernelspec import KernelSpecManager
from jupyter_client.manager import AsyncKernelManager
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError, CellTimeoutError, DeadKernelError

from notebook_runner import measure
from notebook_runner.environment import site_packages_size

# The tag of the cells not to run (nbclient's and nbmake's convention): always honoured.
SKIP_TAG = "skip-execution"
# Cells that install packages: `%pip install`, `!pip install`, or from Python
# (`subprocess.run([... 'pip', 'install'...`).
INSTALL = re.compile(r"\bpip\b['\"]?\s*,?\s*['\"]?install\b|\buv\b\s+pip\s+install\b")
# Lines that only work on Colab, and would block or fail elsewhere (`!sudo` waits for a password).
COLAB_ONLY = ("!sudo", "!apt-get", "!apt ")
# Shell install lines, left out with skip_install.
INSTALL_LINES = ("!pip", "%pip", "!uv", "%uv")
# What the kernel says about its Python, and the packages of its environment.
KERNEL_INFO = r"""
import json as _json, platform as _platform, sys as _sys
print(_json.dumps({"python": _platform.python_version(), "executable": _sys.executable,
                   "platform": _platform.platform()}))
"""
PACKAGES = r"""
import importlib.metadata as _metadata, json as _json
print(_json.dumps({d.metadata["Name"]: d.version for d in _metadata.distributions()
                   if d.metadata["Name"]}))
"""
# Environment variables of CI services, and their names.
CI_SERVICES = {
    "GITHUB_ACTIONS": "GitHub Actions",
    "GITLAB_CI": "GitLab CI",
    "TF_BUILD": "Azure Pipelines",
    "CIRCLECI": "CircleCI",
    "JENKINS_URL": "Jenkins",
    "BUILDKITE": "Buildkite",
}
# Terminal colours in IPython's tracebacks.
ANSI = re.compile(r"\x1b\[[0-9;]*m")
# Not reported as files written by the notebook.
IGNORED = {".ipynb_checkpoints", "__pycache__", ".git", ".virtual_documents"}


@dataclasses.dataclass(frozen=True)
class Budget:
    """Limits above which a run fails, even if the notebook completes. None for no limit."""

    max_seconds: float | None = None
    max_memory_mb: float | None = None
    max_download_mb: float | None = None
    max_dependencies_mb: float | None = None


@dataclasses.dataclass(frozen=True)
class Cell:
    index: int
    """Position in the notebook, from 0, Markdown cells included."""
    id: str | None
    """The cell's id (nbformat 4.5): stable across edits, unlike the index. None in older
    notebooks."""
    first_line: str
    seconds: float | None = None
    """None when the cell was skipped."""
    install: bool = False
    skipped: bool = False
    skip_reason: str | None = None
    """Why it wasn't run: its index was given, its tag, install cells were skipped, an earlier
    cell failed (with stop_on_error), or the kernel died."""
    error: str | None = None
    """"NameError: name 'x' is not defined" when it failed (details in Report.errors.runtime)."""


@dataclasses.dataclass(frozen=True)
class Error:
    cell: int
    name: str
    message: str
    traceback: str
    after_error: int | None = None
    """The previous cell that failed, if any: this error may be a consequence of it (a variable
    it didn't define...)."""


@dataclasses.dataclass(frozen=True)
class Errors:
    runtime: list[Error]
    """Of every cell that failed, in order (timeouts and a dead kernel included)."""
    over_budget: list[str]
    """The limits exceeded: names of `Budget` fields ("max_seconds"...), whose values are in
    options["budget"]; the measured values are in the report."""

    def __bool__(self) -> bool:
        return bool(self.runtime or self.over_budget)


@dataclasses.dataclass(frozen=True)
class Environment:
    """Where the notebook ran. The Python and the packages are seen from inside the kernel."""

    label: str | None
    """How the environment was made, as given to run(): "fresh Python 3.13 environment"..."""
    python: str | None
    executable: str | None
    platform: str | None
    """Operating system and architecture."""
    cpus: int | None
    memory_bytes: int | None
    """Of the machine."""
    ci: str | None
    """The CI service ("GitHub Actions"...), or None outside CI."""
    tools: dict[str, str]
    """Versions of notebook-runner and nbclient."""
    packages: dict[str, str] | None
    """Name -> version of every package of the notebook's environment, at the end of the run
    (the install cells included). None if the kernel died."""


@dataclasses.dataclass(frozen=True)
class Report:
    notebook: str
    title: str | None
    """The notebook's first Markdown heading."""
    sha256: str
    """Of the notebook file: which version of it ran."""
    started_at: str
    """When the run started, in UTC, ISO 8601."""
    finished_at: str
    """When it finished, in UTC, ISO 8601."""
    environment: Environment
    options: dict
    """The options of the run: skipped cells, timeout, budget..."""
    seconds: float
    """From the first cell to the end of the last one run, install cells included."""
    install_seconds: float
    peak_memory_bytes: int
    """Of the kernel and the processes it starts (pip, subprocesses)."""
    downloads: measure.Downloads | None
    dependencies_bytes: int | None
    """Growth of the kernel's site-packages folder: meaningful in a fresh environment."""
    created: list[str]
    modified: list[str]
    """Files created or changed in the notebook's folder (its working directory)."""
    errors: Errors
    cells: list[Cell]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {**dataclasses.asdict(self), "ok": self.ok}


# The notebook field of reports of notebooks given as objects rather than files.
IN_MEMORY = "<in memory>"


def run(
    notebook: str | Path | dict,
    *,
    cwd: str | Path | None = None,
    no_cache: bool = False,
    **options,
) -> Report:
    """Runs a notebook and measures it.

    Args:
        notebook: The .ipynb file, or the notebook itself: a dict, e.g. an `nbformat`
            NotebookNode or the result of `json.loads`. It isn't modified.
        cwd: The kernel's working directory. By default: the notebook's folder, as in Jupyter, or
            for a notebook given as an object, a new empty folder, removed after the run.
        no_cache: Run as on a first visit: pip and uv without their caches, and mlcroissant's
            and the XDG cache folder in an empty temporary folder.
        options: See `_execute`: python, skip_cells, skip_tags, skip_install, timeout,
            count_downloads, budget, executed, stop_on_error, environment.
    """
    if isinstance(notebook, dict):
        # A copy, as JSON: the caller's notebook isn't modified, and it gets upgraded to v4.
        content = json.dumps(notebook, sort_keys=True).encode()
        name, folder = IN_MEMORY, None
    else:
        path = Path(notebook)
        content = path.read_bytes()
        name, folder = str(path), path.resolve().parent
    nb = nbformat.reads(content.decode("utf-8"), as_version=4)
    if name == IN_MEMORY:
        # nbformat's serialization of it: the same notebook has the same hash, whether it is a
        # NotebookNode or a plain dict.
        content = nbformat.writes(nb).encode()
    with contextlib.ExitStack() as temporary:
        if cwd is None:
            cwd = folder or temporary.enter_context(
                tempfile.TemporaryDirectory(prefix="notebook-runner-cwd-")
            )
        env = {}
        if no_cache:
            cache = temporary.enter_context(
                tempfile.TemporaryDirectory(prefix="notebook-runner-cache-")
            )
            env = {
                "PIP_NO_CACHE_DIR": "1",
                "UV_NO_CACHE": "1",
                "CROISSANT_CACHE": str(Path(cache) / "croissant"),
                "XDG_CACHE_HOME": cache,
            }
        return _execute(
            nb,
            name=name,
            sha256=hashlib.sha256(content).hexdigest(),
            cwd=Path(cwd),
            env=env,
            no_cache=no_cache,
            **options,
        )


def _execute(
    nb,
    *,
    name: str,
    sha256: str,
    cwd: Path,
    env: dict[str, str],
    no_cache: bool,
    python: str | Path | None = None,
    skip_cells: frozenset[str] | set[str] = frozenset(),
    skip_tags: frozenset[str] | set[str] = frozenset(),
    skip_install: bool = False,
    timeout: int = 1800,
    count_downloads: bool = True,
    budget: Budget | None = None,
    executed: str | Path | None = None,
    stop_on_error: bool = False,
    environment: str | None = None,
) -> Report:
    """Runs a notebook, read already, in cwd, with these environment variables for the kernel.

    Args:
        python: The kernel's Python (e.g. of `environment.fresh_environment()`), with ipykernel.
            The Python running this function by default.
        skip_cells: Ids of cells not to run. An id that isn't in the notebook is an error.
        skip_tags: Tags of cells not to run, besides `skip-execution`, which is always honoured.
        skip_install: Don't run the install lines (`%pip install`...): for an environment that
            already has the dependencies.
        timeout: Per cell, in seconds.
        count_downloads: Count the data downloaded, through a local proxy (`measure`).
        budget: Limits above which the run fails.
        executed: Where to write the executed copy of the notebook (with its outputs).
        stop_on_error: Stop at the first failing cell. By default, the next cells are run too, and
            every error is reported: an error after a failure says which (`after_error`).
        environment: How the environment was made, for the report: "fresh Python 3.13
            environment", "sandbox container"...
    """
    started_at = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    options = {
        "cwd": str(cwd),
        "no_cache": no_cache,
        "skip_cells": sorted(skip_cells),
        "skip_tags": sorted({SKIP_TAG, *skip_tags}),
        "skip_install": skip_install,
        "timeout": timeout,
        "stop_on_error": stop_on_error,
        "count_downloads": count_downloads,
        "budget": dataclasses.asdict(budget) if budget else None,
    }
    title = _title(nb)
    cells, plan = _plan(nb, set(skip_cells), {SKIP_TAG, *skip_tags}, skip_install)

    with tempfile.TemporaryDirectory(prefix="notebook-runner-kernel-") as kernels:
        client = NotebookClient(
            nb,
            km=_kernel_manager(python, Path(kernels)),
            timeout=timeout,
            # A cell that times out is interrupted, so that the next ones can run.
            interrupt_on_timeout=True,
            resources={"metadata": {"path": str(cwd)}},
        )
        before_files = _files(cwd)
        before_packages = site_packages_size(python) if python else None
        peak = _PeakMemory()
        errors, downloads, dead = [], None, False
        # The kernel, and the processes it starts (pip, curl), go through the counting proxy.
        proxy = measure.CountingProxy() if count_downloads else None
        kernel_env = {"env": {**os.environ, **env, **(proxy.environment() if proxy else {})}}
        start = time.perf_counter()
        try:
            with client.setup_kernel(**kernel_env):
                peak.watch(client.km.provisioner.process.pid)
                kernel = _json_output(_run_hidden(client, nb, KERNEL_INFO)) or {}
                start = time.perf_counter()
                for position, (index, cell) in enumerate(plan):
                    cell_start = time.perf_counter()
                    error = None
                    previous = errors[-1].cell if errors else None
                    try:
                        client.execute_cell(cell, index)
                        if time.perf_counter() - cell_start >= timeout:
                            # Interrupted at the timeout, but the cell ended without an error:
                            # it caught the interrupt, or nbclient was still waiting for the
                            # kernel's reply (py3Dmol in an ipywidgets Output, without a browser).
                            error = Error(
                                index, "Timeout", f"interrupted after {timeout} s", "", previous
                            )
                    except CellExecutionError as e:
                        if (
                            e.ename == "KeyboardInterrupt"
                            and time.perf_counter() - cell_start >= timeout
                        ):
                            # Interrupted at the timeout (interrupt_on_timeout).
                            error = Error(
                                index, "Timeout", f"interrupted after {timeout} s", "", previous
                            )
                        else:
                            traceback = ANSI.sub("", str(e))[-3000:]
                            error = Error(index, e.ename, e.evalue, traceback, previous)
                    except CellTimeoutError as e:
                        error = Error(index, "Timeout", str(e).splitlines()[0], "", previous)
                    except DeadKernelError as e:
                        error = Error(index, "DeadKernelError", str(e), "", previous)
                        dead = True
                    cells[index] = dataclasses.replace(
                        cells[index],
                        seconds=round(time.perf_counter() - cell_start, 2),
                        error=f"{error.name}: {error.message}" if error else None,
                    )
                    if error:
                        errors.append(error)
                    if dead or (error and stop_on_error):
                        why = "the kernel died" if dead else f"cell {index} failed"
                        for rest, _ in plan[position + 1 :]:
                            cells[rest] = dataclasses.replace(
                                cells[rest], skipped=True, skip_reason=f"not run: {why}"
                            )
                        break
                seconds = time.perf_counter() - start
                packages = None if dead else _json_output(_run_hidden(client, nb, PACKAGES))
        finally:
            if proxy:
                downloads = proxy.downloads()
                proxy.close()
        peak.stop()

    finished_at = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    after_files = _files(cwd)
    if executed:
        nbformat.write(nb, executed)
    dependencies = (
        site_packages_size(python) - before_packages if before_packages is not None else None
    )
    ordered = [cells[i] for i in sorted(cells)]
    report = Report(
        notebook=name,
        title=title,
        sha256=sha256,
        started_at=started_at,
        finished_at=finished_at,
        environment=Environment(
            label=environment,
            python=kernel.get("python"),
            executable=kernel.get("executable"),
            platform=kernel.get("platform"),
            cpus=os.cpu_count(),
            memory_bytes=psutil.virtual_memory().total,
            ci=_ci(),
            tools={name: _version(name) for name in ("notebook-runner", "nbclient")},
            packages=dict(sorted(packages.items(), key=lambda p: p[0].lower()))
            if packages
            else None,
        ),
        options=options,
        seconds=round(seconds, 2),
        install_seconds=round(sum(c.seconds or 0 for c in ordered if c.install), 2),
        peak_memory_bytes=peak.bytes,
        downloads=downloads,
        dependencies_bytes=dependencies,
        created=sorted(set(after_files) - set(before_files) - _executed(executed, cwd)),
        modified=sorted(
            f for f in set(after_files) & set(before_files) if after_files[f] != before_files[f]
        ),
        errors=Errors(runtime=errors, over_budget=[]),
        cells=ordered,
    )
    # Against what the run measured.
    return dataclasses.replace(report, errors=Errors(errors, _over_budget(report, budget)))


def _plan(nb, skip_cells: set[str], skip_tags: set[str], skip_install: bool):
    """The cells of the report, and the (index, cell) to run, with their lines to leave out.

    Raises:
        ValueError: An id of skip_cells isn't the id of a code cell of the notebook.
    """
    unknown = skip_cells - {c.get("id") for c in nb.cells if c.cell_type == "code"}
    if unknown:
        raise ValueError(f"No code cells with the ids {sorted(unknown)} in the notebook")
    cells, plan = {}, []
    for index, cell in enumerate(nb.cells):
        if cell.cell_type != "code":
            continue
        source = cell.source
        install = bool(INSTALL.search(source))
        first_line = source.strip().splitlines()[0][:100] if source.strip() else ""
        reason = None
        tags = [t for t in cell.get("metadata", {}).get("tags", []) if t in skip_tags]
        if cell.get("id") in skip_cells:
            reason = "id"
        elif tags:
            reason = f"tag {tags[0]}"
        shell_install = any(line.lstrip().startswith(INSTALL_LINES) for line in source.splitlines())
        if not reason and skip_install and install and not shell_install:
            # Installs from Python (subprocess.run([... 'pip', 'install'...])): the whole cell.
            reason = "install"
        cells[index] = Cell(
            index,
            cell.get("id"),
            first_line,
            install=install,
            skipped=reason is not None,
            skip_reason=reason,
        )
        if reason:
            continue
        leave_out = COLAB_ONLY + (INSTALL_LINES if skip_install else ())
        cell.source = "\n".join(
            f"# [left out by notebook-runner] {line}"
            if line.lstrip().startswith(leave_out)
            else line
            for line in source.splitlines()
        )
        plan.append((index, cell))
    return cells, plan


def _title(nb) -> str | None:
    """The text of the notebook's first Markdown heading."""
    for cell in nb.cells:
        if cell.cell_type == "markdown":
            for line in cell.source.splitlines():
                if match := re.match(r"\s*#+\s+(.+)", line):
                    return match.group(1).strip()
    return None


def _json_output(output: str) -> dict | None:
    """The JSON object printed by a hidden cell, or None if it didn't run."""
    try:
        value = json.loads(output.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    return value if isinstance(value, dict) else None


def _ci() -> str | None:
    for variable, name in CI_SERVICES.items():
        if os.environ.get(variable):
            return name
    return "CI" if os.environ.get("CI") else None


def _version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _kernel_manager(python: str | Path | None, kernels: Path) -> AsyncKernelManager:
    """The default python3 kernel, or one running the given Python."""
    if python is None:
        if importlib.util.find_spec("ipykernel") is None:
            raise RuntimeError(
                "Running a notebook in notebook-runner's own environment needs ipykernel"
                " (pip install 'notebook-runner[local]'), or give the Python of the notebook's"
                " environment (python=..., or --fresh-env)"
            )
        # Async, as nbclient's own: with a blocking one, its timeouts don't apply.
        return AsyncKernelManager(kernel_name="python3")
    spec = kernels / "kernels" / "notebook-runner"
    spec.mkdir(parents=True)
    argv = [str(python), "-m", "ipykernel_launcher", "-f", "{connection_file}"]
    (spec / "kernel.json").write_text(
        json.dumps({"argv": argv, "display_name": "notebook-runner", "language": "python"})
    )
    return AsyncKernelManager(
        kernel_name="notebook-runner",
        kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(spec.parent)]),
    )


def _run_hidden(client: NotebookClient, nb, source: str) -> str:
    """Runs code in the kernel outside the notebook's cells, and returns its output."""
    # nbclient keeps the outputs in nb.cells[index]: a cell added at the end, then removed.
    nb.cells.append(nbformat.v4.new_code_cell(source))
    try:
        # Out of the history: the notebook's cells keep their execution counts (1, 2...).
        client.execute_cell(nb.cells[-1], len(nb.cells) - 1, store_history=False)
        return "".join(o.get("text", "") for o in nb.cells[-1].outputs)
    except CellExecutionError:
        return ""
    finally:
        nb.cells.pop()


class _PeakMemory:
    """The peak resident memory of a process and its children, sampled every 0.2 s."""

    def __init__(self):
        self.bytes = 0
        self._stop = threading.Event()

    def watch(self, pid: int) -> None:
        def poll():
            process = psutil.Process(pid)
            while not self._stop.is_set():
                try:
                    tree = [process, *process.children(recursive=True)]
                    self.bytes = max(self.bytes, sum(p.memory_info().rss for p in tree))
                except psutil.Error:
                    pass
                time.sleep(0.2)

        threading.Thread(target=poll, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def _files(folder: Path) -> dict[str, tuple[int, int]]:
    """Relative path -> (size, modification time) of the files under a folder."""
    files = {}
    for path in folder.rglob("*"):
        if any(part in IGNORED for part in path.relative_to(folder).parts) or not path.is_file():
            continue
        stat = path.stat()
        files[str(path.relative_to(folder))] = (stat.st_size, stat.st_mtime_ns)
    return files


def _executed(executed: str | Path | None, cwd: Path) -> set[str]:
    """The executed copy, when written in the notebook's folder: not a file of the notebook."""
    if not executed:
        return set()
    try:
        return {str(Path(executed).resolve().relative_to(cwd.resolve()))}
    except ValueError:
        return set()


def budget_checks(
    report: Report, budget: Budget
) -> list[tuple[str, str, float | None, float | None, str]]:
    """(Budget field, what it limits, measured value, limit, unit) for each limit of a budget."""
    downloads = report.downloads.total_bytes / 1e6 if report.downloads else None
    dependencies = (
        report.dependencies_bytes / 1e6 if report.dependencies_bytes is not None else None
    )
    return [
        ("max_seconds", "time", report.seconds, budget.max_seconds, "s"),
        ("max_memory_mb", "memory", report.peak_memory_bytes / 1e6, budget.max_memory_mb, "MB"),
        ("max_download_mb", "downloads", downloads, budget.max_download_mb, "MB"),
        ("max_dependencies_mb", "dependencies", dependencies, budget.max_dependencies_mb, "MB"),
    ]


def _over_budget(report: Report, budget: Budget | None) -> list[str]:
    if budget is None:
        return []
    return [
        field
        for field, _, value, limit, _ in budget_checks(report, budget)
        if limit is not None and value is not None and value > limit
    ]
