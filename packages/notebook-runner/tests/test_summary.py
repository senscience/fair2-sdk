import os

import nbformat

import notebook_runner
from notebook_runner import cli, summary


def notebook(folder, *cells, name="notebook.ipynb"):
    """Writes a notebook of code cells, after a Markdown heading (cell 0)."""
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_markdown_cell("# A notebook")]
    nb.cells += [nbformat.v4.new_code_cell(source) for source in cells]
    path = folder / name
    nbformat.write(nb, path)
    return path


def test_the_summary_of_a_notebook_that_runs(tmp_path):
    report = notebook_runner.run(notebook(tmp_path, "import time\ntime.sleep(0.2)", "print(1)"))
    text = summary.markdown([report])
    assert "### A notebook" in text
    assert "✅ **All 2 cells ran**, without errors." in text
    assert "| **Time** |" in text and "| **Peak memory** |" in text
    assert "Slowest cells:" in text
    assert "<details><summary>Time per cell</summary>" in text
    assert "| 1 | `import time` |" in text
    assert "Environment: " in text and "notebook-runner " in text
    assert "| Notebook |" not in text  # the table of notebooks is for several
    assert summary.annotations([report]) == []


def test_the_summary_of_a_failing_notebook(tmp_path):
    path = notebook(tmp_path, "1 / 0", "print(undefined)", "print(1)")
    report = notebook_runner.run(path)
    text = summary.markdown([report])
    assert "❌ **Failed**: 1 failing cell (1 more failing after them), of 3 cells run." in text
    # The cause, with its error and traceback
    assert "**❌ cell 1**: `1 / 0`\n\n> ZeroDivisionError: division by zero" in text
    assert "<details><summary>Traceback</summary>" in text
    # The error after it, probably a consequence
    assert "- cell 2 (after cell 1): NameError: name 'undefined' is not defined" in text
    assert "| 2 | `print(undefined)` |" in text and "❌ after an earlier failure |" in text
    # An annotation for the cause only, on the notebook file
    assert summary.annotations([report]) == [
        f"::error file={os.path.normpath(str(path)).replace(':', '%3A')},"
        "title=Cell 1%3A ZeroDivisionError::ZeroDivisionError: division by zero"
    ]


def test_texts_are_escaped(tmp_path):
    report = notebook_runner.run(notebook(tmp_path, 's = "a|b`c"\nraise ValueError("x|y <z>")'))
    text = summary.markdown([report])
    # Inline code: | escaped for tables, no backticks; quoted texts: HTML escaped too
    assert '`s = "a\\|b\'c"`' in text
    assert "> ValueError: x\\|y &lt;z&gt;" in text


def test_annotations_are_escaped(tmp_path):
    report = notebook_runner.run(notebook(tmp_path, 'raise ValueError("50%\\nnext, line")'))
    (line,) = summary.annotations([report])
    # Newlines and % in the message; also : and , in the properties
    assert line.endswith("::ValueError: 50%25%0Anext, line")
    assert "title=Cell 1%3A ValueError::" in line


def test_the_summary_of_a_notebook_over_budget(tmp_path):
    path = notebook(tmp_path, "import time\ntime.sleep(0.3)")
    report = notebook_runner.run(path, budget=notebook_runner.Budget(max_seconds=0.1))
    text = summary.markdown([report])
    assert "❌ **Failed**: over budget: time: " in text and ", of 1 cells run." in text


def test_several_notebooks_start_with_a_table(tmp_path):
    good = notebook_runner.run(notebook(tmp_path, "print(1)", name="good.ipynb"))
    bad = notebook_runner.run(notebook(tmp_path, "1 / 0", name="bad.ipynb"))
    text = summary.markdown([good, bad])
    assert text.startswith("| Notebook | Result |")
    # The failed one first, in the table and the sections
    table = text.split("\n\n")[0]
    assert table.index(bad.notebook) < table.index(good.notebook)
    assert f"| `{bad.notebook}` | ❌ failed in cell 1 (ZeroDivisionError) |" in table
    assert f"| `{good.notebook}` | ✅ ok |" in table
    assert text.index("### A notebook") < text.index("<details><summary>✅")
    # The failed one in full, the one that ran fine folded
    assert text.count("### A notebook") == 1
    assert f"<details><summary>✅ <code>{good.notebook}</code>: A notebook (" in text
    assert "✅ **All 1 cells ran**" in text
    # Both sections complete, with their environment
    assert text.count("Environment: ") == 2


def test_several_notebooks_with_the_same_file_name_are_named_by_their_folder(tmp_path):
    reports = []
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        reports.append(notebook_runner.run(notebook(tmp_path / folder, "print(1)")))
    text = summary.markdown(reports)
    assert f"| `{tmp_path / 'a'}` | ✅ ok |" in text
    assert f"<code>{tmp_path / 'b'}</code>" in text
    # The full path is still in each section
    assert f"`{tmp_path / 'a' / 'notebook.ipynb'}`" in text


def test_a_single_notebook_is_not_folded(tmp_path):
    report = notebook_runner.run(notebook(tmp_path, "print(1)"))
    text = summary.markdown([report])
    assert text.startswith("### A notebook")
    assert "<details><summary>✅" not in text


def test_the_command_prints_annotations(tmp_path, capsys):
    bad = notebook(tmp_path, "1 / 0", name="bad.ipynb")
    assert cli.main([str(bad), "--annotations"]) == 1
    assert "::error file=" in capsys.readouterr().out
