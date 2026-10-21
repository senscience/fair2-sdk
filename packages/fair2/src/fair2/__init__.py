"""Helpers for the datasets of the SENSCIENCE FAIR² Data Portal.

import croissant_duckdb
import fair2

db = croissant_duckdb.connect("https://sen.science/doi/10.71728/senscience.f2na-3dct/fair2.json")
fair2.card(db)  # displayed by Jupyter
fair2.query_box(db)  # a SQL editor, with the widgets extra
fair2.plot_style()  # the Frontiers colours for matplotlib figures (fair2.colors)
"""

from fair2 import colors
from fair2.card import DatasetCard, card
from fair2.themes import FRONTIERS, Theme

__all__ = [
    "FRONTIERS",
    "DatasetCard",
    "QueryBox",
    "Theme",
    "card",
    "colors",
    "plot_style",
    "query_box",
]


def __getattr__(name):
    # Imported when used: the query box needs the widgets extra, the plot style matplotlib.
    if name in ("query_box", "QueryBox"):
        from fair2 import query

        return getattr(query, name)
    if name == "plot_style":
        from fair2 import plots

        return plots.plot_style
    raise AttributeError(f"module 'fair2' has no attribute {name!r}")
