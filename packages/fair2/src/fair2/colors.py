"""Colours of the Frontiers brand for charts, as in Frontiers Data (its `frontiers.css`).

Pick the palette by the job the colour does:

- `CATEGORICAL`: identity (one colour per series), in this fixed order, never cycled. The first 5
  stay distinct for colour-blind readers; with 6, the 5th and 6th (yellow, green) are close for
  protanopia: label the series directly, or keep a legend.
- `ordinal(n)`: ordered categories (levels, grades): one hue, light to dark, up to 4 levels.
- `SEQUENTIAL` and `DIVERGING`: continuous values, as colour steps for colormaps (`plot_style()`
  registers them as "fair2" and "fair2_diverging"). Diverging is for values around a midpoint
  (correlations, differences), with a neutral grey at the midpoint.
- `NEUTRAL`: what has no category (missing, other).
- `INK`, `MUTED`, `GRID`: text, secondary text and axes, gridlines. Text never takes a series'
  colour: `ink_on(color)` is the text colour for a label inside a mark.

Checked with the dataviz palette validator (lightness, chroma, colour-blind separation of
neighbours, contrast against a white background).
"""

from __future__ import annotations

# The dataviz set of the Frontiers brand, in its order.
CATEGORICAL = [
    "#0081cc",  # blue
    "#db6e1a",  # orange
    "#8072df",  # violet
    "#cc3d38",  # red
    "#c38509",  # yellow
    "#3a8348",  # green
]

# Brink blues for ordered levels: from blue 20 (the lightest that stays visible on white) to 90.
_BLUES = ["#6d9efd", "#3673f7", "#0c4ded", "#003bde", "#002fca", "#0024b0", "#001991", "#001959"]

# Continuous values: Brink blue 0 (near zero) to blue 90.
SEQUENTIAL = ["#eef5ff", "#aecbff", "#6d9efd", "#0c4ded", "#0024b0", "#001959"]
# Around a midpoint: Brink blue 70 to red 60, through grey 20.
DIVERGING = ["#0024b0", "#3673f7", "#f0f0f0", "#f2575d", "#bd0b25"]

NEUTRAL = "#a2a2a2"  # Brink grey 60
INK = "#282828"  # Brink black
MUTED = "#545454"  # Brink grey 80
GRID = "#e6e6e6"  # Brink grey 30


# Beyond 4 levels, neighbouring Brink blues are too close in lightness to tell apart.
MAX_ORDINAL = 4


def ordinal(n: int) -> list[str]:
    """`n` colours for ordered levels, light to dark, as evenly spaced on the blue ramp as possible.

    Raises:
        ValueError: More than 4 levels: group them, or use the "fair2" colormap (`SEQUENTIAL`).
    """
    if not 1 <= n <= MAX_ORDINAL:
        raise ValueError(
            f"ordinal() gives 1 to {MAX_ORDINAL} distinguishable colours, not {n}:"
            " group the levels, or use the 'fair2' colormap"
        )
    if n == 1:
        return [_BLUES[3]]
    return [_BLUES[round(i * (len(_BLUES) - 1) / (n - 1))] for i in range(n)]


def _luminance(color: str) -> float:
    """WCAG relative luminance of a #rrggbb colour."""

    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(int(color.lstrip("#")[i : i + 2], 16) / 255) for i in (0, 2, 4))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def ink_on(color: str) -> str:
    """The text colour for a label on a mark of this colour: white on dark colours, ink on light."""
    mark = _luminance(color) + 0.05
    # The text colour with the better WCAG contrast against the mark.
    return "white" if 1.05 / mark > mark / (_luminance(INK) + 0.05) else INK
