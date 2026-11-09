"""What a run gives to read: the Markdown summary (`--summary`) and GitHub Actions annotations
(`--annotations`), from the reports.

The summary is the Jinja template `templates/summary.md.j2`: for each notebook, the result, the
totals (time, install, peak memory, downloads per host, dependencies, files written), the slowest
cells, the time of every cell (folded), the failing cells with their errors and tracebacks
(folded), and the environment; with several notebooks, a table of them first. It is written for
GitHub's Markdown (job summaries, comments), which folds `<details>` blocks.
"""

from __future__ import annotations

import functools
import html
import os

import jinja2

from notebook_runner.runner import IN_MEMORY, Budget, Cell, Error, Report, budget_checks

SLOWEST = 3
"""Cells listed as the slowest."""
FIRST_LINE = 70
"""Characters of a cell's first line shown."""
TRACEBACK_LINES = 40
"""The end of a traceback, where its cause is."""


def markdown(reports: list[Report]) -> str:
    """The summary of the runs."""
    return _template().render(reports=reports)


def annotations(reports: list[Report]) -> list[str]:
    """A GitHub Actions error annotation (workflow command) per failing cell that is a cause, on
    the notebook file: not the cells failing after another one, which may be consequences."""
    lines = []
    for report in reports:
        # "./10.71728/..." -> "10.71728/...": a path from the workspace, to link the file
        notebook = os.path.normpath(report.notebook)
        place = "" if report.notebook == IN_MEMORY else f"file={_property(notebook)},"
        for error in causes(report):
            title = f"Cell {error.cell}: {error.name}"
            lines.append(f"::error {place}title={_property(title)}::{_message(describe(error))}")
    return lines


def causes(report: Report) -> list[Error]:
    """The errors not following an earlier failure."""
    return [e for e in report.errors.runtime if e.after_error is None]


def consequences(report: Report) -> list[Error]:
    """The errors following an earlier failure: probably its consequences."""
    return [e for e in report.errors.runtime if e.after_error is not None]


def describe(error: Error) -> str:
    return f"{error.name}: {error.message}" if error.message else error.name


def result(report: Report) -> str:
    """'ok', or the failing cells and the limits exceeded, in one line."""
    results = []
    runtime, over_budget = report.errors.runtime, report.errors.over_budget
    if runtime:
        # The first errors; the ones after a failure may be its consequences.
        failed = ", ".join(f"{e.cell} ({e.name})" for e in runtime[:4])
        more = f", and {len(runtime) - 4} more" if len(runtime) > 4 else ""
        cells = "cell" if len(runtime) == 1 else "cells"
        results.append(f"failed in {cells} {failed}{more}")
    if over_budget:
        results.append("over budget: " + "; ".join(exceeded(report)))
    return "; ".join(results) or "ok"


def exceeded(report: Report) -> list[str]:
    """'time: 2.3 s > 1.0 s': the measured values, and the limits of the run's budget."""
    checks = budget_checks(report, Budget(**report.options["budget"]))
    return [
        f"{label}: {value:,.1f} {unit} > {limit:,.1f} {unit}"
        for field, label, value, limit, unit in checks
        if field in report.errors.over_budget
    ]


def size(n: int | None) -> str:
    if n is None:
        return "–"
    for unit in ("B", "kB", "MB", "GB"):
        if abs(n) < 1000 or unit == "GB":
            return f"{n:,} B" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1000


def duration(seconds: float | None) -> str:
    if seconds is None:
        return "–"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, rest = divmod(round(seconds), 60)
    return f"{minutes} min {rest:02d} s"


def _ran(report: Report) -> list[Cell]:
    return [c for c in report.cells if not c.skipped]


def _slowest(report: Report) -> list[Cell]:
    timed = [c for c in _ran(report) if c.seconds]
    return sorted(timed, key=lambda c: -c.seconds)[:SLOWEST]


def _status(cell: Cell, report: Report) -> str:
    if cell.skipped:
        return "⏭ skipped" + (f" ({_md(cell.skip_reason)})" if cell.skip_reason else "")
    error = next((e for e in report.errors.runtime if e.cell == cell.index), None)
    if error is None:
        return "✅"
    return "❌" if error.after_error is None else "❌ after an earlier failure"


def _cell(report: Report, index: int) -> Cell | None:
    return next((c for c in report.cells if c.index == index), None)


def _md(value: object) -> str:
    """Text for Markdown: HTML special characters escaped, and | (a table's separator)."""
    return html.escape(str(value), quote=False).replace("|", "\\|")


def _code(value: object, limit: int | None = None) -> str:
    """Text for inline code: shortened, without backticks, | escaped for tables."""
    text = str(value)
    if limit and len(text) > limit:
        text = text[: limit - 1] + "…"
    return text.replace("`", "'").replace("|", "\\|")


def _traceback(error: Error) -> str:
    """The end of the traceback, escaped for a <pre> block."""
    lines = error.traceback.strip().splitlines()[-TRACEBACK_LINES:]
    return html.escape("\n".join(lines), quote=False)


def _message(value: str) -> str:
    """A message escaped for a workflow command: %, carriage returns and newlines."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _property(value: str) -> str:
    """A property (file, title) escaped for a workflow command: also its separators : and ,."""
    return _message(value).replace(":", "%3A").replace(",", "%2C")


@functools.cache
def _template() -> jinja2.Template:
    environment = jinja2.Environment(
        loader=jinja2.PackageLoader("notebook_runner", "templates"),
        # Markdown, not HTML: texts are escaped by the filters, where they go.
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    environment.filters.update(
        md=_md, code=_code, size=size, duration=duration, traceback=_traceback
    )
    environment.globals.update(
        FIRST_LINE=FIRST_LINE,
        causes=causes,
        consequences=consequences,
        describe=describe,
        result=result,
        exceeded=exceeded,
        ran=_ran,
        slowest=_slowest,
        status=_status,
        cell=_cell,
    )
    return environment.get_template("summary.md.j2")
