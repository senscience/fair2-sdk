"""A Plotly template for the figures of the notebooks: the Frontiers colours, recessive axes.

    fair2.plotly_style()  # the default template for the rest of the notebook
    fig.update_layout(template="fair2")  # then, for a figure with another template

It's the counterpart of `fair2.plot_style()` for matplotlib, with the same palettes
(`fair2.colors`): the series colours are its categorical ones, and its sequential and diverging
steps are the default colour scales (`SEQUENTIAL` and `DIVERGING` here, as Plotly colour scales).
It only sets defaults, so any of them can be overridden for one figure.
"""

from __future__ import annotations

from fair2 import colors

try:
    import plotly.graph_objects as go
    import plotly.io as pio
except ImportError as e:  # plotly isn't installed
    raise ImportError("fair2.plotly_style needs plotly: pip install plotly") from e

NAME = "fair2"


def _scale(steps: list[str]) -> list[list]:
    """A Plotly colour scale with evenly spaced steps."""
    return [[i / (len(steps) - 1), step] for i, step in enumerate(steps)]


SEQUENTIAL = _scale(colors.SEQUENTIAL)
DIVERGING = _scale(colors.DIVERGING)


def _axis() -> dict:
    # Recessive axes: a muted baseline and ticks, light gridlines, no zero line.
    return {
        "showline": True,
        "linecolor": colors.MUTED,
        "ticks": "outside",
        "tickcolor": colors.MUTED,
        "tickfont": {"color": colors.MUTED},
        "title": {"font": {"color": colors.INK}, "standoff": 10},
        "gridcolor": colors.GRID,
        "zeroline": False,
        "automargin": True,
    }


def template() -> go.layout.Template:
    """The template, also registered as "fair2" by `plotly_style()`."""
    return go.layout.Template(
        layout={
            # Series in the fixed order of the categorical palette.
            "colorway": colors.CATEGORICAL,
            "colorscale": {"sequential": SEQUENTIAL, "diverging": DIVERGING},
            "font": {"family": "Helvetica, Arial, sans-serif", "color": colors.INK, "size": 12},
            "title": {"x": 0, "xanchor": "left", "font": {"size": 15}},
            "paper_bgcolor": "white",
            "plot_bgcolor": "white",
            "xaxis": {**_axis(), "showgrid": False},
            "yaxis": {**_axis(), "showgrid": True},
            "legend": {"bgcolor": "rgba(0,0,0,0)", "title": {"font": {"color": colors.MUTED}}},
            "hoverlabel": {"bgcolor": "white", "font": {"color": colors.INK}},
            # A white gap between neighbouring bars.
            "bargap": 0.2,
            "coloraxis": {"colorbar": {"outlinewidth": 0, "ticks": "outside"}},
        },
        data={
            # A white gap between touching marks (stacked bars, histogram bins, pie slices).
            "bar": [go.Bar(marker={"line": {"color": "white", "width": 1}})],
            "histogram": [go.Histogram(marker={"line": {"color": "white", "width": 0.5}})],
            "pie": [go.Pie(marker={"line": {"color": "white", "width": 1.5}})],
            "scatter": [go.Scatter(line={"width": 2}, marker={"size": 8})],
            "heatmap": [go.Heatmap(colorscale=SEQUENTIAL)],
        },
    )


def plotly_style() -> None:
    """Registers the "fair2" template and makes it the default, on top of "plotly_white"."""
    pio.templates[NAME] = template()
    pio.templates.default = f"plotly_white+{NAME}"
