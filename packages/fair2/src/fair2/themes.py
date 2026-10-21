"""Themes of the dataset card: colours for light and dark notebooks, a typeface, and a logo.

The default, `FRONTIERS`, follows the Frontiers brand of FAIR² Discovery (fair2-discovery,
`app/src/styles/brands/frontiers.css`): the Brink palette with Discovery's dark values. It has no
logo: the notebooks show the Frontiers Data logo at their top, in their first Markdown cell.
Colours are CSS variables scoped to the card, so the notebook isn't restyled.
"""

from __future__ import annotations

import dataclasses
from importlib import resources

# The colours a theme sets, as CSS colours. The card's rules only read these.
COLORS = (
    "background",  # the card
    "foreground",  # text
    "muted",  # secondary text: summaries, table headers
    "border",
    "highlight",  # table headers
    "link",  # links and section titles
    "badge",  # DOI, version, date and license
    "badge-foreground",
    "warning",  # record sets without a table
    "logo",  # the parts of the logo drawn with currentColor
)

# Notebook frontends in a dark theme: JupyterLab and Notebook 7, VS Code, Colab.
DARK_SELECTORS = (
    '[data-jp-theme-light="false"]',
    "body.vscode-dark",
    "body.vscode-high-contrast:not(.vscode-high-contrast-light)",
    'html[theme="dark"]',
)


@dataclasses.dataclass(frozen=True)
class Theme:
    light: dict[str, str]
    """Colour name (see `COLORS`) -> CSS colour."""
    dark: dict[str, str]
    """The same colours in dark notebook themes."""
    logo: str | None = None
    """An inline SVG, shown above the title. Parts filled with currentColor take the logo colour."""
    logo_label: str = ""
    """What the logo says, for screen readers."""
    font: str | None = None
    """A CSS font-family list. The fonts aren't loaded: the first one installed is used."""

    def css(self) -> str:
        """The theme's CSS variables, for the light and the dark notebook themes."""

        def variables(colors: dict[str, str]) -> str:
            return " ".join(f"--f2-{name}: {colors[name]};" for name in COLORS if name in colors)

        dark = ", ".join(f"{selector} .fair2-card" for selector in DARK_SELECTORS)
        font = f" font-family: {self.font};" if self.font else ""
        return (
            f".fair2-card.fair2-themed {{ {variables(self.light)}{font} }}\n"
            f"{dark} {{ {variables(self.dark)} }}"
        )


def asset(name: str) -> str:
    """A file of fair2/assets: the stylesheets of the card."""
    return (resources.files("fair2") / "assets" / name).read_text(encoding="utf-8")


# Brink colours (light) and their Discovery dark-theme steps, in the comments.
FRONTIERS = Theme(
    light={
        "background": "#ffffff",  # white
        "foreground": "#282828",  # black
        "muted": "#545454",  # grey 80
        "border": "#d5d5d5",  # grey 40
        "highlight": "#f7f7f7",  # grey 10
        "link": "#0024b0",  # blue 70
        "badge": "#cee1ff",  # blue 5
        "badge-foreground": "#001959",  # blue 90
        "warning": "#a93f0c",  # orange 70
        "logo": "#5a5a5c",
    },
    dark={
        "background": "#202020",  # surface 900
        "foreground": "#ffffff",  # white
        "muted": "#bfbfbf",  # grey 50
        "border": "#454545",  # surface 700
        "highlight": "#282828",  # black
        "link": "#6d9efd",  # blue 20
        "badge": "#001959",  # blue 90
        "badge-foreground": "#aecbff",  # blue 10
        "warning": "#ffb062",  # orange 30
        "logo": "#ffffff",
    },
    # Museo Sans, the Frontiers typeface, when it is installed.
    font="'museo-sans', 'Museo Sans', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto,"
    " sans-serif",
)
