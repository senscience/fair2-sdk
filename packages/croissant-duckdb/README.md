# croissant-duckdb

Expose the record sets of a [Croissant](https://mlcommons.org/croissant/) dataset as
[DuckDB](https://duckdb.org) tables and views, to query them with SQL without downloading the files
first.

```python
import croissant_duckdb

db = croissant_duckdb.connect("https://sen.science/doi/10.71728/senscience.k7f3-9xqm/fair2.json")

db.tables  # record set @id -> table or view name
db.skipped  # record set @id -> why it has no table

# Query with SQL: only the needed columns and row groups are downloaded.
samples_per_sweep = db.sql("""
    SELECT wave_name, count(*) AS n_samples FROM sweep_traces
    WHERE igor_file_name = 'MPG210604Th_A_1'
    GROUP BY wave_name ORDER BY wave_name
""").df()

# Small tables can be converted to pandas.
sweep_metadata = db.table("sweep_metadata").df()
```

`db.table()` accepts a record set `@id`, its name, or its table name. For a record set that doesn't
exist or was skipped, it raises `croissant_duckdb.TableNotFoundError` (a `KeyError`), whose `reason`
says why. `db.con` is the DuckDB connection and `db.dataset` the `mlcroissant.Dataset`.

## How record sets are mapped

Metadata is read with `mlcroissant`. A record set gets a table or a view when all its fields are
`column` extracts from the same CSV, TSV or Parquet `FileObject`, without transforms or sub-fields:

- **CSV and TSV files become tables.** They can't be read partially, so each file is read once into
  DuckDB's columnar storage, instead of once per query.
- **Parquet files become views.** Queries read them remotely with HTTP range requests and only fetch
  the footer, the columns and the row groups they need. `count(*)` is answered from the footer.
- Parquet files keep the types they store, without casts. CSV files are read with the types the
  fields declare: `sc:Text` as `VARCHAR`, `sc:Integer` as `BIGINT`, `sc:Float` as `DOUBLE`,
  `sc:Boolean`, `sc:Date`, `sc:DateTime`, `sc:Time`, and the sized types (`cr:Int32`, `cr:Float32`...).
  Text fields are read as text, so identifiers keep their leading zeros (`records()` loses them:
  `"007"` becomes `"7"` when the whole column looks numeric). A CSV file whose values don't match the
  declared types (e.g. `NA` in an `sc:Integer` column) is skipped with the reason.
- Only empty CSV cells become `NULL`. In text fields, values such as `NA`, `N/A` or `null` are
  kept as they are, while `records()` (pandas' defaults) turns them into missing values.
- Tables and columns are named after the record sets and fields: their `name`, or the suffix of
  their `@id` when they have none (`title` for `plain_text/title`), as they are. Names are quoted
  in SQL (`FROM "ML Cell Metadata"`), so any non-empty name is valid. DuckDB compares names
  case-insensitively: a record set whose name is already used, or with two fields of the same
  name, is skipped with the reason.
- Files are read in parallel. For remote files, the `httpfs` extension is loaded and its HTTP
  metadata cache is enabled.

Other record sets are listed in `db.skipped` with the reason (unsupported format, file inside an
archive, column missing from the file, file that can't be read...) and can still be read with
`db.dataset.records(...)`.

## Install

Requires Python 3.12 or later. Until it is published on PyPI, from the `fair2-sdk` repository:

```
!pip install "git+https://github.com/senscience/fair2-sdk#subdirectory=packages/croissant-duckdb"
```

For development, from the root of the repository (a uv workspace):

```
uv sync
uv run pytest packages/croissant-duckdb/tests
```
