"""Helpers for the datasets of the SENSCIENCE FAIR² Data Portal.

import croissant_duckdb
import fair2

db = croissant_duckdb.connect("https://sen.science/doi/10.71728/senscience.f2na-3dct/fair2.json")
fair2.card(db)  # displayed by Jupyter
fair2.query_box(db)  # a SQL editor, with the widgets extra
fair2.plot_style()  # the Frontiers colours for matplotlib figures (fair2.colors)
fair2.plotly_style()  # and for Plotly figures
fair2.table(db.sql("SELECT ..."), units=fair2.units(db))  # a query result as a table
"""

from fair2 import colors
from fair2.card import DatasetCard, card
from fair2.tables import Column, Kind, Table, table, units
from fair2.themes import FRONTIERS, Theme

__all__ = [
    "FRONTIERS",
    "Column",
    "DatasetCard",
    "Kind",
    "QueryBox",
    "Table",
    "Theme",
    "card",
    "colors",
    "plot_style",
    "plotly_style",
    "query_box",
    "table",
    "units",
]


def __getattr__(name):
    # Imported when used: the query box needs the widgets extra, the plot styles matplotlib or
    # plotly.
    if name in ("query_box", "QueryBox"):
        from fair2 import query

        return getattr(query, name)
    if name == "plot_style":
        from fair2 import plots

        return plots.plot_style
    if name == "plotly_style":
        from fair2 import plotly_theme

        return plotly_theme.plotly_style
    raise AttributeError(f"module 'fair2' has no attribute {name!r}")
