# fair2-sdk

Python packages for working with the datasets of the SENSCIENCE FAIR² Data Portal.

| Package | Description |
|---|---|
| [`croissant-duckdb`](packages/croissant-duckdb) | Expose the record sets of a Croissant dataset as DuckDB tables and views |
| [`fair2`](packages/fair2) | Dataset cards, a SQL editor with completion and export, and a figure style, for the notebooks of the FAIR² datasets |

## Development

The repository is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/): each
package lives in `packages/<name>` with its own `pyproject.toml` and version.

```
uv sync
uv run pytest packages/croissant-duckdb/tests packages/fair2/tests
```

Code is linted and formatted with [Ruff](https://docs.astral.sh/ruff/), configured in the root
`pyproject.toml` for every package:

```
uv run ruff check          # add --fix to apply the automatic fixes
uv run ruff format         # or --check to only report
```
