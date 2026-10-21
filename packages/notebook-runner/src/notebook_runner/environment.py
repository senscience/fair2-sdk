"""Fresh Python environments, to run a notebook as on a first visit (Colab, a new machine).

The environment only has ipykernel: what the notebook's install cell installs is measured, as the
growth of its site-packages folder.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path


@contextlib.contextmanager
def fresh_environment(python: str | None = None) -> Iterator[Path]:
    """A new virtual environment with ipykernel, removed afterwards. Yields its Python.

    Args:
        python: The Python version (e.g. "3.13") with uv, which can fetch it; without uv, the
            current Python is used.
    """
    with tempfile.TemporaryDirectory(prefix="notebook-runner-") as folder:
        venv = Path(folder) / "venv"
        uv = shutil.which("uv")
        if uv:
            version = ["--python", python] if python else []
            subprocess.run([uv, "venv", "--quiet", "--seed", *version, str(venv)], check=True)
            executable = _executable(venv)
            subprocess.run(
                [uv, "pip", "install", "--quiet", "--python", str(executable), "ipykernel"],
                check=True,
            )
        else:
            if python:
                raise RuntimeError("Choosing the Python version of a fresh environment needs uv")
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
            executable = _executable(venv)
            subprocess.run(
                [str(executable), "-m", "pip", "install", "--quiet", "ipykernel"], check=True
            )
        yield executable


def _executable(venv: Path) -> Path:
    windows = venv / "Scripts" / "python.exe"
    return windows if windows.exists() else venv / "bin" / "python"


def site_packages_size(python: Path | str) -> int:
    """The size in bytes of the site-packages folder of a Python: what is installed in it."""
    folder = subprocess.run(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return sum(
        f.stat().st_size for f in Path(folder).rglob("*") if f.is_file() and not f.is_symlink()
    )
