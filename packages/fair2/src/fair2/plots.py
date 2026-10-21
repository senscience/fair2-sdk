"""A matplotlib style for the figures of the notebooks: the Frontiers colours, recessive axes.

    fair2.plot_style()  # for the rest of the notebook
    with fair2.plot_style():  # or only for some figures
        ...

It only sets defaults (`matplotlib.rcParams`), so it works with any chart, and any of them can be
overridden for one chart. The palettes are in `fair2.colors`: the series colours are its
categorical ones, and the "fair2" and "fair2_diverging" colormaps are registered. Figures keep a
white background: an image doesn't follow the notebook's dark theme, and white reads in both.
"""

from __future__ import annotations

from fair2 import colors

try:
    import matplotlib as mpl
    from cycler import cycler
    from matplotlib.colors import LinearSegmentedColormap
except ImportError as e:  # matplotlib isn't installed
    raise ImportError("fair2.plot_style needs matplotlib: pip install matplotlib") from e

STYLE = {
    # Series in the fixed order of the categorical palette.
    "axes.prop_cycle": cycler(color=colors.CATEGORICAL),
    "image.cmap": "fair2",
    # Recessive axes: no top and right borders, muted ticks and labels, titles on the left.
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": colors.MUTED,
    "axes.labelcolor": colors.INK,
    "axes.titlelocation": "left",
    "axes.titlecolor": colors.INK,
    "xtick.color": colors.MUTED,
    "ytick.color": colors.MUTED,
    # Gridlines behind the marks, light; off by default: `ax.grid(axis=...)` where they help.
    "axes.axisbelow": True,
    "grid.color": colors.GRID,
    "grid.linewidth": 0.8,
    # A white gap between touching marks (stacked bars, histograms), not a dark outline.
    "patch.force_edgecolor": True,
    "patch.edgecolor": "white",
    "patch.linewidth": 1.5,
    "lines.linewidth": 2,
    "legend.frameon": False,
    "text.color": colors.INK,
    # Box plots in the muted colour, with the median in ink.
    "boxplot.boxprops.color": colors.MUTED,
    "boxplot.whiskerprops.color": colors.MUTED,
    "boxplot.capprops.color": colors.MUTED,
    "boxplot.medianprops.color": colors.INK,
    "boxplot.flierprops.markeredgecolor": colors.MUTED,
    "boxplot.flierprops.markersize": 4,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
}


def _register_colormaps() -> None:
    for name, steps in (("fair2", colors.SEQUENTIAL), ("fair2_diverging", colors.DIVERGING)):
        if name not in mpl.colormaps:
            mpl.colormaps.register(LinearSegmentedColormap.from_list(name, steps))


class plot_style:  # noqa: N801: used as a function, like matplotlib.rc_context
    """Applies the style: until the end of the `with` block, or for the rest of the session."""

    def __init__(self, overrides: dict | None = None):
        """
        Args:
            overrides: rcParams to set on top of the style, e.g. `{"figure.figsize": (8, 4)}`.
        """
        _register_colormaps()
        style = {**STYLE, **(overrides or {})}
        self._previous = {name: mpl.rcParams[name] for name in style}
        mpl.rcParams.update(style)

    def __enter__(self) -> plot_style:
        return self

    def __exit__(self, *_) -> None:
        mpl.rcParams.update(self._previous)
