# fair2

Helpers for the datasets of the SENSCIENCE FAIR² Data Portal.

## Dataset cards

A dataset card tells what a dataset is, how to cite and use it, and what its record sets contain.
It is displayed by Jupyter when it is the last expression of a cell:

```python
import croissant_duckdb
import fair2

db = croissant_duckdb.connect("https://sen.science/doi/10.71728/senscience.f2na-3dct/fair2.json")
fair2.card(db)
```

The card has:

- **A header:** title, DOI, version, publication date and license, then authors, data article,
  data portal, the Croissant file the metadata was read from, "cite as", keywords, spatial and
  temporal coverage, and funders.
- **Responsible use**, folded: intended uses, limitations, biases, personal and sensitive
  information, ethical considerations, social impact, data collection, missing data, processing
  and maintenance. It covers the Croissant RAI properties
  and the FAIR² ones some datasets use instead (`potentialBiases`, `ethicalConsiderations`...).
  Sections without content aren't shown.
- **Record sets**, folded: for each one, its file, format, size, row count, number of fields,
  and DuckDB table, or why it has none.
- **Fields**, folded: one folded table per record set, with each field's type, unit and
  description, and its statistics when the metadata declares some (`statistics`: missing values,
  min and max, number of distinct values, most frequent values).
- **Other files**, folded, when the dataset has some: the files and file sets that no record set
  reads (a SQLite database, PDFs, images...), with their format, size and description. An
  archive that a record set reads a file of isn't listed.

The card only uses the metadata, which `croissant_duckdb.connect` (or `mlcroissant.Dataset`)
already read: it reads neither the Croissant file again nor the data. Row counts and statistics
are the ones the metadata declares, and are left out when it declares none. From a
`croissant_duckdb.Database`, it also takes the DuckDB table of each record set, or why it has none;
`fair2.card(dataset)` takes an `mlcroissant.Dataset` instead.

`card.html()` returns the card as an HTML fragment. Texts of the metadata are escaped, and only
http(s) URLs become links.

### Themes

The card has the Frontiers theme of FAIR² Discovery by default: the Brink colours, and Museo Sans
when it is installed (the fonts aren't downloaded). Colours switch to their dark values in dark
notebook themes (JupyterLab, VS Code, Colab). The styles are scoped to the card: the rest of the
notebook is unchanged. The Frontiers theme has no logo, since the notebooks show the Frontiers Data
logo at their top; a theme of your own can add one, embedded in the card, so it works offline.

```python
fair2.card(db, theme=None)  # plain HTML, which follows the notebook's look

fair2.card(
    db,
    theme=fair2.Theme(
        light={"link": "#0b6e4f", "badge": "#d8f3e8"},
        dark={"link": "#7ad3b0", "badge": "#0b3d2e"},
        logo=open("logo.svg").read(),  # inline SVG; parts filled with currentColor take "logo"
        logo_label="My lab",
    ),
)
```

The colours a theme can set are listed in `fair2.themes.COLORS`. In GitHub's notebook viewer, which
removes styles, the card is shown as plain HTML.

### Templates

The markup is a Jinja template, `src/fair2/templates/card.html.j2`, with autoescaping, and the
styles are `src/fair2/assets/card.css` and `card-themed.css`. `fair2.html` gives the template the
card and the formatting filters (numbers, sizes, ranges).

## SQL editor

`fair2.query_box(db, query)` is a SQL editor for notebooks, with a Run button (or Ctrl/Cmd+Enter)
and the result below it, at most 100 rows (`limit=`). `box.result` is the last result, as a pandas
DataFrame. It completes SQL keywords (DuckDB's included), the tables and views of the connection,
and the columns of the tables the query names, quoted when they need to be. Tables created by a
query are completed afterwards.

Once a query has a result, **Download CSV** and **Download Parquet** export the whole result, not
only the rows shown, written by DuckDB (`COPY`) without going through pandas. Up to 50 MB
(`max_download_bytes=`), the browser downloads the file. Larger, it is saved next to the notebook,
without overwriting a file, since big messages between the kernel and the browser are slow and
limited. `box.export("csv")` does the same from code.

```python
box = fair2.query_box(db, 'SELECT * FROM "participants" LIMIT 10')
box
```

It needs the `widgets` extra (`fair2[widgets]`: anywidget) and a running kernel: JupyterLab,
Notebook 7, VS Code, Colab. In JupyterLab, anywidget must be installed in the environment of
Jupyter itself before it starts. Where widgets can't be shown (GitHub, a saved notebook without a
kernel), the cell says how to run the query with `con.sql(...)` instead.

The editor is [CodeMirror 6](https://codemirror.net), in `js/`. Its bundle,
`src/fair2/static/query_box.js`, is committed, so installing fair2 needs no JavaScript build. After
changing `js/src`:

```
cd js
npm ci
npm test
npm run build
```

## Figures

`fair2.plot_style()` sets matplotlib's defaults to the Frontiers brand of FAIR² Discovery: series
in the Frontiers chart colours, recessive axes (no top and right borders, muted ticks, titles on the
left, light gridlines when asked for with `ax.grid(...)`), white gaps between touching bars, muted
box plots. It only sets defaults, so it works with any chart, and each can be overridden; use
`with fair2.plot_style():` for some figures only, and `fair2.plot_style({"figure.figsize": (8, 4)})`
to change some defaults. Figures keep a white background, readable in light and dark notebooks.

`fair2.colors` has the palettes, chosen by the job of the colour, all checked for colour-blind
readers and contrast:

| Job | Palette |
|---|---|
| One colour per series | `CATEGORICAL`, the default series colours: 6 colours in a fixed order. Up to 5 series are told apart by colour-blind readers; a 6th needs a legend or direct labels. |
| Ordered levels | `ordinal(n)`: one hue, light to dark, up to 4 levels (Brink's darker blues are too close beyond). |
| Continuous values | The `"fair2"` colormap (`SEQUENTIAL`), and `"fair2_diverging"` (`DIVERGING`) for values around a midpoint. |
| No category, missing | `NEUTRAL` |
| Text on a mark | `ink_on(color)`: white on dark marks, ink on light ones |

```python
fair2.plot_style()
palette = fair2.colors.ordinal(3) + [fair2.colors.NEUTRAL]
counts.plot.barh(stacked=True, color=palette)
```

## Install

Requires Python 3.12 or later. Until it is published on PyPI, from the `fair2-sdk` repository:

```
!pip install "git+https://github.com/senscience/fair2-sdk#subdirectory=packages/croissant-duckdb" "fair2[widgets] @ git+https://github.com/senscience/fair2-sdk#subdirectory=packages/fair2"
```
