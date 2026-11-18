"""A figure wider than the notebook, shown smaller.

The figures' code often sets a fixed size, sometimes far wider than a notebook (3400 px). The
notebook shows them with `fit`, which keeps the figure as made, only smaller:

    fit(result)

- The drawing (plots, margins, lines, markers) shrinks by one factor, k = `width` / the figure's
  width, but not below `smallest`: a figure too wide for that stays wider than the notebook.
- The texts shrink by k too, but not below `min_text` pixels (nor above their own size): Plotly's
  zoom magnifies the data, not the texts, so they must be readable as shown.
- A figure within `width`, without a fixed width (Plotly fills the cell), or that isn't a Plotly
  figure, is shown as it is.

The figure itself is left unchanged: `fit` returns a copy, whose data is checked to be the same.
Plotly isn't a dependency: `fit` imports it only for a figure, which the notebook's code made.
"""

from __future__ import annotations

import copy
import re
from typing import Any

# Sizes in pixels, by the key of the dict holding them
LINE_KEYS = ("width",)
MARGIN_KEYS = ("l", "r", "t", "b", "pad")
AXIS_KEYS = ("ticklen", "tickwidth", "linewidth", "gridwidth", "zerolinewidth", "dividerwidth")
ANNOTATION_KEYS = (
    "xshift",
    "yshift",
    "borderpad",
    "borderwidth",
    "arrowwidth",
    "standoff",
    "startstandoff",
    "width",
    "height",
)
LEGEND_KEYS = ("borderwidth", "itemwidth", "tracegroupgap")
COLORBAR_KEYS = ("xpad", "ypad", "outlinewidth", "ticklen", "tickwidth", "borderwidth")
# Font sizes written in texts, which Plotly allows: <span style="font-size:14px">
FONT_SIZE = re.compile(r"font-size:\s*([\d.]+)px")
# Plotly's defaults: a figure's height without one, the texts' size without one
DEFAULT_HEIGHT = 450
DEFAULT_TEXT = 12
# Fields of the data, compared before and after: shrinking must not change them
DATA_FIELDS = (
    "x",
    "y",
    "z",
    "values",
    "labels",
    "lat",
    "lon",
    "locations",
    "r",
    "theta",
    "a",
    "b",
    "c",
    "ids",
    "parents",
    "source",
    "target",
    "value",
)


def fit(figure: Any, width: float = 1000, min_text: float = 10, smallest: float = 0.45) -> Any:
    """The figure as it is, or a smaller copy when it is a Plotly figure wider than `width`.

    Args:
        figure: What the figure's code made: shown as it is unless a Plotly figure.
        width: The notebook's width, in pixels: the figure's width once shrunk.
        min_text: The smallest size, in pixels, its texts are shrunk to.
        smallest: The smallest factor the drawing is shrunk by.
    """
    try:
        from plotly.basedatatypes import BaseFigure
    except ImportError:
        return figure
    if not isinstance(figure, BaseFigure):
        return figure
    own = figure.layout.width
    if not own or own <= width:
        return figure
    return scaled(figure, max(width / own, smallest), min_text=min_text)


def scaled(figure: Any, k: float, *, min_text: float = 0) -> Any:
    """A copy of a Plotly figure, its sizes in pixels multiplied by k, its texts by k too but not
    below `min_text` (nor above their own size)."""

    def text(size: float) -> float:
        return max(size * k, min(min_text, size))

    spec = copy.deepcopy(figure.to_plotly_json())
    layout = spec["layout"]
    # The ratio is kept for a figure without a height too
    layout["height"] = (layout.get("height") or DEFAULT_HEIGHT) * k
    layout["width"] = layout["width"] * k
    # The texts without a size of their own take the layout's: set it, so that they shrink too
    layout.setdefault("font", {}).setdefault("size", DEFAULT_TEXT)
    _walk(layout, k, text, "layout")
    for trace in spec["data"]:
        _walk(trace, k, text, "trace")
    _scale_texts(spec, text)
    smaller = type(figure)(spec)
    _check_same_data(figure, smaller)
    return smaller


def _scale_texts(node: Any, text) -> None:
    """The font sizes written in texts, in place: strings only, the data's numbers untouched."""
    if isinstance(node, dict):
        items = list(node.items())
    elif isinstance(node, list):
        items = list(enumerate(node))
    else:
        return
    for key, value in items:
        if isinstance(value, str) and "font-size" in value:
            node[key] = FONT_SIZE.sub(lambda m: f"font-size:{text(float(m.group(1))):.1f}px", value)
        elif isinstance(value, (dict, list)):
            _scale_texts(value, text)


def _scale(value: Any, k: float) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value * k
    if isinstance(value, (list, tuple)):
        return [_scale(v, k) for v in value]
    try:  # numpy arrays
        return value * k
    except TypeError:
        return value


def _scale_keys(node: dict, keys: tuple[str, ...], k: float) -> None:
    for key in keys:
        if key in node:
            node[key] = _scale(node[key], k)


def _walk(node: Any, k: float, text, name: str) -> None:
    """The sizes in pixels of a part of the figure, in place, by the name of the part."""
    if isinstance(node, list):
        for item in node:
            _walk(item, k, text, name)
        return
    if not isinstance(node, dict):
        return
    if name.endswith("font"):
        size = node.get("size")
        if isinstance(size, (int, float)) and not isinstance(size, bool):
            node["size"] = text(size)
        elif isinstance(size, (list, tuple)):
            node["size"] = [text(s) if isinstance(s, (int, float)) else s for s in size]
    elif name == "line" or (name.endswith("line") and name != "outline"):
        _scale_keys(node, LINE_KEYS, k)
    elif name == "margin":
        _scale_keys(node, MARGIN_KEYS, k)
    elif name.startswith(("xaxis", "yaxis", "radialaxis", "angularaxis")):
        _scale_keys(node, AXIS_KEYS, k)
    elif name == "annotations":
        _scale_keys(node, ANNOTATION_KEYS, k)
        # Arrow offsets: pixels, unless given in an axis's units
        for ref, key in (("axref", "ax"), ("ayref", "ay")):
            if node.get(ref, "pixel") == "pixel" and key in node:
                node[key] = _scale(node[key], k)
    elif name == "legend":
        _scale_keys(node, LEGEND_KEYS, k)
        if node.get("entrywidthmode", "pixels") == "pixels":
            _scale_keys(node, ("entrywidth",), k)
    elif name == "colorbar":
        _scale_keys(node, COLORBAR_KEYS, k)
        if node.get("thicknessmode", "pixels") == "pixels":
            _scale_keys(node, ("thickness",), k)
        if node.get("lenmode") == "pixels":
            _scale_keys(node, ("len",), k)
    elif name == "marker":
        if "sizeref" in node:
            # Sizes in the data's units: their reference scales instead (area or diameter)
            power = 2 if node.get("sizemode", "diameter") == "area" else 1
            node["sizeref"] = node["sizeref"] / k**power
        else:
            _scale_keys(node, ("size",), k)
        _scale_keys(node, ("sizemin",), k)
    elif name == "node":  # Sankey
        _scale_keys(node, ("pad", "thickness"), k)
    elif name == "title":
        _scale_keys(node, ("standoff",), k)
    for key, value in node.items():
        if isinstance(value, (dict, list)):
            _walk(value, k, text, key)


def _check_same_data(before: Any, after: Any) -> None:
    for a, b in zip(before.data, after.data, strict=True):
        for field in DATA_FIELDS:
            va, vb = getattr(a, field, None), getattr(b, field, None)
            if (va is not None or vb is not None) and not _equal(va, vb):
                raise AssertionError(f"fit changed the figure's data: {a.type}.{field}")


def _equal(a: Any, b: Any) -> bool:
    """Equal values, missing ones (NaN, None) equal to each other."""
    import pandas as pd

    sa = pd.Series(list(_flat(a)), dtype=object)
    sb = pd.Series(list(_flat(b)), dtype=object)
    if len(sa) != len(sb):
        return False
    return bool(((sa.isna() & sb.isna()) | (sa == sb)).all())


def _flat(value: Any):
    import numpy as np

    if isinstance(value, (str, bytes)) or np.ndim(value) == 0:
        yield value
        return
    for item in value:
        yield from _flat(item)
