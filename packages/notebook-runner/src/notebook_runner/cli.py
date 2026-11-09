"""The `notebook-runner` command: runs notebooks, prints a summary, writes the reports.

    notebook-runner 10.71728/*/notebook-duckdb.ipynb --fresh-env --python 3.13 \\
        --report report.json --summary summary.md --max-download-mb 500

The exit code is 1 when a notebook fails or goes over a budget, for CI. The summary and the
annotations are made in `summary`.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

import nbformat

from notebook_runner import summary
from notebook_runner.environment import fresh_environment
from notebook_runner.runner import Budget, Report, run
from notebook_runner.summary import result, size


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="notebook-runner", description="Run notebooks from scratch and measure them."
    )
    parser.add_argument("notebooks", nargs="+", type=Path)
    parser.add_argument(
        "--fresh-env",
        action="store_true",
        help="run each notebook in a new environment, to measure its install",
    )
    parser.add_argument("--python", help="Python version of the fresh environments (with uv)")
    parser.add_argument(
        "--skip-cells",
        default="",
        help="comma-separated ids of cells not to run (their `id` in the notebook)",
    )
    parser.add_argument(
        "--skip-tag",
        action="append",
        default=[],
        metavar="TAG",
        help="don't run the cells with this tag (repeatable); skip-execution always applies",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="don't run the install lines (the environment has the dependencies)",
    )
    parser.add_argument("--timeout", type=int, default=1800, help="per cell, in seconds")
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="stop at the first failing cell (by default, run them all)",
    )
    parser.add_argument("--no-downloads", action="store_true", help="don't count downloads")
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="run as on a first visit: pip, uv and mlcroissant without their caches",
    )
    parser.add_argument("--cwd", type=Path, help="working directory (default: the notebook's)")
    parser.add_argument("--report", type=Path, help="JSON report of every notebook")
    parser.add_argument(
        "--summary",
        type=Path,
        help="Markdown summary: results, times, downloads, errors (e.g. $GITHUB_STEP_SUMMARY)",
    )
    parser.add_argument(
        "--annotations",
        action="store_true",
        help="print a GitHub Actions error annotation per failing cell",
    )
    parser.add_argument("--executed", type=Path, help="folder for the executed copies")
    for name, unit in (
        ("seconds", "s"),
        ("memory-mb", "MB"),
        ("download-mb", "MB"),
        ("dependencies-mb", "MB"),
    ):
        parser.add_argument(f"--max-{name}", type=float, help=f"fail above this ({unit})")
    args = parser.parse_args(argv)

    budget = Budget(
        args.max_seconds, args.max_memory_mb, args.max_download_mb, args.max_dependencies_mb
    )
    skip = {i.strip() for i in args.skip_cells.split(",") if i.strip()}
    # An id belongs to one notebook: each one gets its own, and an id in none of them is an error.
    ids = {notebook: _ids(notebook) for notebook in args.notebooks}
    unknown = skip - set().union(*ids.values())
    if unknown:
        parser.error(f"--skip-cells: no code cells with the ids {sorted(unknown)}")
    if args.executed:
        args.executed.mkdir(parents=True, exist_ok=True)

    reports = []
    for notebook in args.notebooks:
        environment = (
            fresh_environment(args.python) if args.fresh_env else contextlib.nullcontext(None)
        )
        with environment as python:
            executed = None
            if args.executed:
                executed = args.executed / f"{notebook.resolve().parent.name}-{notebook.stem}.ipynb"
            report = run(
                notebook,
                cwd=args.cwd,
                python=python,
                skip_cells=skip & ids[notebook],
                no_cache=args.no_cache,
                skip_tags=set(args.skip_tag),
                skip_install=args.skip_install,
                timeout=args.timeout,
                count_downloads=not args.no_downloads,
                budget=budget,
                executed=executed,
                stop_on_error=args.stop_on_error,
                environment=(
                    f"fresh Python {args.python or 'default'} environment"
                    if args.fresh_env
                    else "the environment of notebook-runner"
                ),
            )
        reports.append(report)
        print(summary_line(report), flush=True)

    if args.report:
        args.report.write_text(json.dumps([r.to_dict() for r in reports], indent=1) + "\n")
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(summary.markdown(reports))
    if args.annotations:
        for line in summary.annotations(reports):
            print(line, flush=True)
    return 0 if all(r.ok for r in reports) else 1


def _ids(notebook: Path) -> set[str]:
    """The ids of the code cells of a notebook."""
    cells = nbformat.read(notebook, as_version=4).cells
    return {c.get("id") for c in cells if c.cell_type == "code" and c.get("id")}


def summary_line(report: Report) -> str:
    parts = [f"{report.seconds:.1f} s", f"peak {size(report.peak_memory_bytes)}"]
    if report.install_seconds:
        parts.append(f"install {report.install_seconds:.1f} s")
    if report.downloads:
        # The largest hosts: the data, and the package index for the installs.
        hosts = ", ".join(f"{h} {size(n)}" for h, n in list(report.downloads.by_host.items())[:3])
        parts.append(
            f"downloaded {size(report.downloads.total_bytes)}" + (f" ({hosts})" if hosts else "")
        )
    if report.dependencies_bytes is not None:
        parts.append(f"dependencies {size(report.dependencies_bytes)}")
    skipped = [c.id or str(c.index) for c in report.cells if c.skipped]
    if skipped:
        parts.append(f"skipped cells {', '.join(skipped)}")
    if report.created or report.modified:
        written = len(report.created) + len(report.modified)
        parts.append(f"wrote {written} file{'s' if written != 1 else ''}")
    return f"{report.notebook}: {result(report)} ({', '.join(parts)})"


if __name__ == "__main__":
    sys.exit(main())
