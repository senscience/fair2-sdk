"""Run notebooks from scratch and measure them: do they complete, how long they take, how much
memory, data and dependencies they need, and which files they write.

    import notebook_runner

    report = notebook_runner.run("notebook.ipynb", budget=notebook_runner.Budget(max_seconds=300))
    report.ok, report.seconds, report.downloads.total_bytes

    with notebook_runner.fresh_environment("3.13") as python:  # as on a first visit
        report = notebook_runner.run("notebook.ipynb", python=python)
        report.dependencies_bytes, report.install_seconds

Or the `notebook-runner` command (`notebook_runner.cli`).
"""

from notebook_runner.environment import fresh_environment
from notebook_runner.measure import Downloads
from notebook_runner.runner import Budget, Cell, Environment, Error, Errors, Report, run

__all__ = [
    "Budget",
    "Cell",
    "Downloads",
    "Environment",
    "Error",
    "Errors",
    "Report",
    "fresh_environment",
    "run",
]
