import json
import os
from pathlib import Path

import nbformat
import pytest

import notebook_runner
from notebook_runner import cli


def notebook(folder, *cells, name="notebook.ipynb"):
    """Writes a notebook of code cells: strings, or (source, tags) or (source, tags, id)."""
    nb = nbformat.v4.new_notebook()
    for cell in cells:
        source, tags, *id = cell if isinstance(cell, tuple) else (cell, [])
        code = nbformat.v4.new_code_cell(source, metadata={"tags": tags})
        if id:
            code.id = id[0]
        nb.cells.append(code)
    nb.cells.insert(0, nbformat.v4.new_markdown_cell("# A notebook"))
    path = folder / name
    nbformat.write(nb, path)
    return path


def test_the_report_says_which_notebook_ran_and_how(tmp_path):
    import hashlib
    import platform
    import sys

    path = notebook(tmp_path, "print(1)")
    report = notebook_runner.run(path, timeout=60, skip_tags={"slow"}, environment="the tests")
    assert report.notebook == str(path)
    assert report.title == "A notebook"  # its first heading
    assert report.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report.started_at.endswith("+00:00")
    assert report.started_at <= report.finished_at
    environment = report.environment
    assert environment.label == "the tests"
    assert (environment.python, environment.executable, environment.platform) == (
        platform.python_version(),
        sys.executable,
        platform.platform(),
    )
    assert environment.cpus >= 1 and environment.memory_bytes > 1e9
    assert set(environment.tools) == {"notebook-runner", "nbclient"}
    # The packages of the notebook's environment, with their versions.
    assert environment.packages["nbclient"] == environment.tools["nbclient"]
    assert "ipykernel" in environment.packages
    assert report.options["timeout"] == 60 and report.options["skip_cells"] == []
    assert report.options["skip_tags"] == ["skip-execution", "slow"]
    assert report.options["cwd"] == str(tmp_path)
    assert list(report.to_dict())[:7] == [
        "notebook",
        "title",
        "sha256",
        "started_at",
        "finished_at",
        "environment",
        "options",
    ]


def test_ci_is_recognised(monkeypatch):
    from notebook_runner import runner

    for variable in [*runner.CI_SERVICES, "CI"]:
        monkeypatch.delenv(variable, raising=False)
    assert runner._ci() is None
    monkeypatch.setenv("CI", "true")
    assert runner._ci() == "CI"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert runner._ci() == "GitHub Actions"


def test_a_notebook_given_as_an_object(tmp_path):
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell("# Generated"),
        nbformat.v4.new_code_cell("import os\nopen('out.txt', 'w').write(os.getcwd())"),
    ]
    executed = tmp_path / "executed.ipynb"
    report = notebook_runner.run(nb, executed=executed)
    assert report.ok
    assert (report.notebook, report.title) == ("<in memory>", "Generated")
    assert len(report.sha256) == 64
    # It ran in a new folder, removed afterwards; what it wrote there is reported.
    assert report.created == ["out.txt"]
    assert "notebook-runner-cwd-" in report.options["cwd"]
    assert not os.path.exists(report.options["cwd"])
    # The caller's notebook isn't modified: no outputs added.
    assert nb.cells[1].outputs == [] and nb.cells[1].execution_count is None
    assert nbformat.read(executed, as_version=4).cells[1].execution_count == 1
    # The same as a plain dict (e.g. from json.loads), and the same notebook gives the same hash.
    again = notebook_runner.run(json.loads(nbformat.writes(nb)))
    assert again.ok and again.sha256 == report.sha256


def test_no_cache(tmp_path):
    path = notebook(
        tmp_path,
        "import os\n"
        "print([os.environ.get(v) for v in ('PIP_NO_CACHE_DIR', 'UV_NO_CACHE')])\n"
        "print(os.path.isdir(os.environ['XDG_CACHE_HOME']), os.environ['CROISSANT_CACHE'])",
    )
    executed = tmp_path / "executed.ipynb"
    report = notebook_runner.run(path, no_cache=True, executed=executed)
    assert report.ok and report.options["no_cache"] is True
    lines = nbformat.read(executed, as_version=4).cells[1].outputs[0]["text"].splitlines()
    assert lines[0] == "['1', '1']"
    assert lines[1].startswith("True ") and "notebook-runner-cache-" in lines[1]
    # Without it, the caches are the usual ones.
    assert notebook_runner.run(path).options["no_cache"] is False


def test_the_kernel_is_shut_down_after_the_run(tmp_path):
    import time

    import psutil

    executed = tmp_path / "executed.ipynb"
    path = notebook(tmp_path, "import os\nprint(os.getpid())")
    report = notebook_runner.run(path, executed=executed)
    assert report.ok
    pid = int(nbformat.read(executed, as_version=4).cells[1].outputs[0]["text"])
    deadline = time.monotonic() + 10
    while psutil.pid_exists(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE


def test_a_notebook_that_completes(tmp_path):
    path = notebook(
        tmp_path,
        "import time\ntime.sleep(0.3)",
        "open('out.csv', 'w').write('a,b\\n')",
        "print('done')",
    )
    report = notebook_runner.run(path)
    assert report.ok and report.errors == notebook_runner.Errors(runtime=[], over_budget=[])
    # Markdown cells aren't listed; code cells keep their index in the notebook.
    assert [c.index for c in report.cells] == [1, 2, 3]
    assert report.cells[0].seconds >= 0.3
    assert report.seconds >= 0.3
    assert report.peak_memory_bytes > 10_000_000
    # The notebook ran in its folder, and wrote a file there.
    assert report.created == ["out.csv"] and report.modified == []
    assert report.downloads.total_bytes == 0
    # The notebook file isn't modified.
    assert nbformat.read(path, as_version=4).cells[1].outputs == []


def test_the_run_continues_after_errors_and_reports_them_all(tmp_path):
    path = notebook(
        tmp_path,
        "x = 1",
        "raise ValueError('wrong value')\ny = 2",
        "print(y)",
        "print(x)",
    )
    report = notebook_runner.run(path)
    assert not report.ok
    first, second = report.errors.runtime
    assert (first.cell, first.name, first.message, first.after_error) == (
        2,
        "ValueError",
        "wrong value",
        None,
    )
    # The traceback, without IPython's terminal colours.
    assert "ValueError" in first.traceback and "\x1b[" not in first.traceback
    # A consequence of the first error: y was never defined. It says which error came before.
    assert (second.cell, second.name, second.after_error) == (3, "NameError", 2)
    assert [c.error for c in report.cells] == [
        None,
        "ValueError: wrong value",
        "NameError: name 'y' is not defined",
        None,
    ]
    # The last cell ran.
    assert report.cells[3].seconds is not None and not report.cells[3].skipped


def test_stop_on_error(tmp_path):
    path = notebook(tmp_path, "x = 1", "raise ValueError('wrong value')", "print(x)")
    report = notebook_runner.run(path, stop_on_error=True)
    assert [e.cell for e in report.errors.runtime] == [2]
    assert report.cells[2].seconds is None
    assert report.cells[2].skipped
    assert report.cells[2].skip_reason == "not run: cell 2 failed"


# Short sleeps: on Windows, the interrupt only acts between them, not during a blocking call.
INTERRUPTIBLE = "import time\nwhile True:\n    time.sleep(0.1)"


def test_a_cell_that_times_out_is_interrupted(tmp_path):
    path = notebook(tmp_path, INTERRUPTIBLE, "print('next')")
    report = notebook_runner.run(path, timeout=2)
    assert [(e.cell, e.name) for e in report.errors.runtime] == [(1, "Timeout")]
    assert report.cells[0].seconds < 20
    assert report.cells[1].error is None and report.cells[1].seconds is not None


def test_a_timeout_is_reported_even_if_the_cell_ends_without_error(tmp_path):
    # The interrupt is caught, so the cell ends normally, but after the timeout.
    cell = "try:\n" + "\n".join("    " + line for line in INTERRUPTIBLE.splitlines())
    cell += "\nexcept KeyboardInterrupt:\n    pass"
    report = notebook_runner.run(notebook(tmp_path, cell), timeout=2)
    assert [(e.cell, e.name) for e in report.errors.runtime] == [(1, "Timeout")]
    assert not report.ok


def test_a_cell_that_the_interrupt_does_not_stop_stops_the_notebook(tmp_path, monkeypatch):
    # As time.sleep on Windows: here a cell ignoring the interrupt, on every system.
    monkeypatch.setattr(notebook_runner.runner, "GRACE", 2)
    cell = "import signal, time\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\ntime.sleep(60)"
    report = notebook_runner.run(notebook(tmp_path, cell, "print('next')"), timeout=2)
    assert [(e.cell, e.name, e.message) for e in report.errors.runtime] == [
        (1, "Timeout", "interrupted after 2 s, still running 2 s later")
    ]
    assert report.cells[0].seconds < 20  # not the 60 s of the cell
    assert report.cells[1].skipped
    assert report.cells[1].skip_reason == "not run: cell 1 could not be interrupted"
    assert report.environment.packages is None  # not asked to the stopped kernel


def test_a_display_in_an_output_widget_does_not_wait_for_the_timeout(tmp_path):
    # jupyter/nbclient#312 (zmq_wakeup): without the fix, nbclient waited for the kernel's reply
    # until the timeout, every time, for a py3Dmol view displayed in an Output (hw56-vj34).
    atom = "ATOM      1  CA  ALA A   1      11.104   6.134  -6.504  1.00  0.00           C"
    cell = (
        "import ipywidgets as widgets\n"
        "import py3Dmol\n"
        "from IPython.display import display\n"
        "output = widgets.Output()\n"
        "display(output)\n"
        "view = py3Dmol.view(width=400, height=300)\n"
        f"view.addModel({atom!r}, 'pdb')\n"
        "view.zoomTo()\n"
        "with output:\n"
        "    display(view)"
    )
    report = notebook_runner.run(notebook(tmp_path, cell), timeout=10)
    assert report.ok, report.errors
    assert report.seconds < 5


def test_the_jupyter_client_fix_is_applied_once():
    from jupyter_client import session

    from notebook_runner import zmq_wakeup

    zmq_wakeup.apply()
    send = session.Session.send
    zmq_wakeup.apply()
    assert session.Session.send is send
    # Unless jupyter_client has it: then the patch is no longer needed (and can be removed).
    if not hasattr(session, "_wake_async_socket"):
        assert send._wakes_async_socket


@pytest.mark.skipif(os.name == "nt", reason="no Unix sockets: TCP on Windows")
def test_the_kernel_communicates_through_unix_sockets(tmp_path, capfd):
    report = notebook_runner.run(notebook(tmp_path, "print(1)"))
    assert report.ok
    # ipykernel's warning about TCP: "Kernel is running over TCP without encryption"
    assert "without encryption" not in capfd.readouterr().err


def test_cells_without_ids_in_a_recent_notebook_are_read_without_warnings(tmp_path):
    # nbformat 4.5 notebooks whose cells have no id (bt07-sboc, k7f3-9xqm): nbformat gives them
    # random ones, with a MissingIDFieldWarning per cell.
    import warnings

    path = notebook(tmp_path, "print(1)", "print(2)")
    nb = json.loads(path.read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        del cell["id"]
    path.write_text(json.dumps(nb), encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = notebook_runner.run(path)
        assert cli.main([str(path)]) == 0
    assert report.ok
    assert [w.category.__name__ for w in caught if "MissingID" in w.category.__name__] == []


def test_skipping_cells_by_id_and_tag(tmp_path):
    path = notebook(
        tmp_path,
        "print('runs')",
        ("raise RuntimeError('needs a frontend')", ["skip-execution"]),
        ("raise RuntimeError('skipped by its id')", [], "pdb-viewer"),
        ("raise RuntimeError('slow')", ["slow"]),
    )
    report = notebook_runner.run(path, skip_cells={"pdb-viewer"}, skip_tags={"slow"})
    assert report.ok
    assert [c.skipped for c in report.cells] == [False, True, True, True]
    assert [c.skip_reason for c in report.cells] == [
        None,
        "tag skip-execution",
        "id",
        "tag slow",
    ]
    # Each cell's id is in the report, next to its index.
    assert report.cells[2].id == "pdb-viewer" and report.cells[2].index == 3
    assert all(c.id for c in report.cells)


def test_an_unknown_id_is_an_error(tmp_path):
    path = notebook(tmp_path, "print(1)")
    with pytest.raises(ValueError, match="No code cells with the ids \\['nope'\\]"):
        notebook_runner.run(path, skip_cells={"nope"})


def test_install_cells(tmp_path):
    path = notebook(
        tmp_path,
        "%pip install a-package-that-does-not-exist-anywhere",
        "import subprocess, sys\n"
        "subprocess.run([sys.executable, '-m', 'pip', 'install', 'nope-nope'], check=True)",
        "!sudo apt-get install graphviz",
        "print('analysis')",
    )
    report = notebook_runner.run(path, skip_install=True)
    assert report.ok
    assert [c.install for c in report.cells] == [True, True, False, False]
    # Shell lines are left out; an install from Python skips its cell.
    assert [c.skip_reason for c in report.cells] == [None, "install", None, None]


@pytest.fixture
def served(tmp_path):
    """A 100 kB file served over HTTP on 127.0.0.1: its URL."""
    import functools
    import http.server
    import threading

    folder = tmp_path / "served"
    folder.mkdir()
    (folder / "data.bin").write_bytes(b"x" * 100_000)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=folder)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/data.bin"
    server.shutdown()


def test_the_proxy_counts_what_it_forwards_per_host(served):
    import urllib.request

    from notebook_runner.measure import CountingProxy

    proxy = CountingProxy()
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy.url}))
        assert len(opener.open(served).read()) == 100_000
        downloads = proxy.downloads()
    finally:
        proxy.close()
    # The body and the response headers.
    assert 100_000 < downloads.total_bytes < 101_000
    assert list(downloads.by_host) == ["127.0.0.1"]


def test_closing_the_proxy_leaves_no_connection_pending(served, caplog):
    # Connections left open (kept alive by pip, requests...) were destroyed later with the
    # proxy's loop, during the next notebook: "Event loop is closed", "Task was destroyed".
    import gc
    import socket
    import sys
    from urllib.parse import urlsplit

    from notebook_runner.measure import CountingProxy

    unraisable = []
    hook, sys.unraisablehook = sys.unraisablehook, unraisable.append
    try:
        proxy = CountingProxy()
        client = socket.create_connection(("127.0.0.1", proxy.port))
        client.sendall(f"CONNECT {urlsplit(served).netloc} HTTP/1.1\r\n\r\n".encode())
        assert client.recv(100).startswith(b"HTTP/1.1 200")  # a tunnel, left open
        proxy.close()
        del proxy
        gc.collect()
        client.close()
    finally:
        sys.unraisablehook = hook
    assert [u.exc_value for u in unraisable] == []
    assert not [r for r in caplog.records if "Task was destroyed" in r.getMessage()]


def test_downloads_of_the_kernel_and_of_its_shell_commands(tmp_path, served):
    import shutil

    cells = [
        # Python's HTTP clients read the proxy variables the kernel gets.
        "import os, urllib.request\n"
        "proxy = urllib.request.ProxyHandler({'http': os.environ['HTTP_PROXY']})\n"
        f"urllib.request.build_opener(proxy).open('{served}').read()",
    ]
    if shutil.which("curl"):  # a program started by the kernel inherits them
        cells.append(f"!curl -s --noproxy '' -o /dev/null {served}")
    report = notebook_runner.run(notebook(tmp_path, *cells))
    assert report.ok
    assert report.downloads.total_bytes > 100_000 * len(cells)
    assert set(report.downloads.by_host) == {"127.0.0.1"}


def test_without_ipykernel_the_error_says_what_to_install(tmp_path, monkeypatch):
    from notebook_runner import runner

    find_spec = runner.importlib.util.find_spec
    monkeypatch.setattr(
        runner.importlib.util,
        "find_spec",
        lambda name, *args: None if name == "ipykernel" else find_spec(name, *args),
    )
    with pytest.raises(RuntimeError, match=r"notebook-runner\[local\]"):
        notebook_runner.run(notebook(tmp_path, "print(1)"))


def test_budgets(tmp_path):
    path = notebook(tmp_path, "import time\ntime.sleep(0.5)")
    report = notebook_runner.run(path, budget=notebook_runner.Budget(max_seconds=0.1))
    assert not report.ok and report.errors.runtime == []
    # The exceeded limit, by name: its value is in the options, the measure in the report.
    assert report.errors.over_budget == ["max_seconds"]
    assert report.options["budget"]["max_seconds"] == 0.1 and report.seconds > 0.1
    assert "over budget: time: " in cli.summary_line(report)


def test_the_command(tmp_path, capsys):
    good = notebook(tmp_path, "print(1)", name="good.ipynb")
    bad = notebook(tmp_path, "1 / 0", name="bad.ipynb")
    code = cli.main(
        [
            str(good),
            str(bad),
            "--report",
            str(tmp_path / "r.json"),
            "--summary",
            str(tmp_path / "s.md"),
        ]
    )
    assert code == 1  # a notebook failed
    reports = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert [r["ok"] for r in reports] == [True, False]
    assert reports[1]["errors"]["runtime"][0]["name"] == "ZeroDivisionError"
    assert reports[1]["errors"]["over_budget"] == []
    table = (tmp_path / "s.md").read_text(encoding="utf-8")
    assert "| `" + str(good) + "` | ✅ ok |" in table
    assert "failed in cell 1 (ZeroDivisionError)" in table
    assert "good.ipynb: ok (" in capsys.readouterr().out


def test_the_command_gives_each_notebook_its_own_ids(tmp_path, capsys):
    first = notebook(tmp_path, ("raise RuntimeError", [], "broken"), name="first.ipynb")
    second = notebook(tmp_path, "print(2)", name="second.ipynb")
    # "broken" is only in the first notebook: skipped there, ignored in the second.
    assert cli.main([str(first), str(second), "--skip-cells", "broken"]) == 0
    assert "first.ipynb: ok (" in capsys.readouterr().out
    # An id in none of the notebooks is an error.
    with pytest.raises(SystemExit) as exit:
        cli.main([str(second), "--skip-cells", "nowhere"])
    assert exit.value.code == 2
    assert "no code cells with the ids ['nowhere']" in capsys.readouterr().err


@pytest.mark.skipif(
    not os.environ.get("NOTEBOOK_RUNNER_FRESH_ENV"),
    reason="creates an environment and installs packages: NOTEBOOK_RUNNER_FRESH_ENV=1",
)
def test_a_fresh_environment(tmp_path):
    path = notebook(tmp_path, "%pip install --quiet six", "import six")
    with notebook_runner.fresh_environment() as python:
        report = notebook_runner.run(path, python=python)
    assert report.ok
    assert report.install_seconds > 0
    assert report.dependencies_bytes > 10_000  # six


@pytest.mark.skipif(
    not os.environ.get("NOTEBOOK_RUNNER_FRESH_ENV"),
    reason="creates an environment and installs packages: NOTEBOOK_RUNNER_FRESH_ENV=1",
)
def test_a_shell_pip_installs_into_the_notebook_environment(tmp_path):
    # !pip runs in a shell: the environment's pip, not the first one (or none) on the runner's PATH
    path = notebook(tmp_path, "!pip install --quiet six", "import six")
    with notebook_runner.fresh_environment() as python:
        report = notebook_runner.run(path, python=python)
    assert report.ok, report.errors.runtime


def test_a_notebook_environment_comes_first_on_the_path(tmp_path):
    import venv

    from notebook_runner.runner import _activated

    venv.create(tmp_path / "venv", with_pip=False)
    python = next(p for p in (tmp_path / "venv").glob("*/python*") if p.is_file())
    runner_path = os.pathsep.join(["/usr/local/bin", "/usr/bin"])

    variables = _activated(python, runner_path)

    first, *rest = variables["PATH"].split(os.pathsep)
    assert Path(first) == python.parent  # bin/ or Scripts/
    assert rest == runner_path.split(os.pathsep)
    assert Path(variables["VIRTUAL_ENV"]).resolve() == (tmp_path / "venv").resolve()


def test_a_python_outside_a_virtual_environment_is_not_activated():
    import sys

    from notebook_runner.runner import _activated

    base = sys._base_executable  # the Python the runner's own environment was made from
    if not Path(base).is_file():
        pytest.skip("no base Python to run")
    variables = _activated(base, "")
    assert "VIRTUAL_ENV" not in variables
    assert variables["PATH"]  # its scripts folder
