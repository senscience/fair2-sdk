import matplotlib
import pytest

import fair2
from fair2 import colors

matplotlib.use("Agg")


def test_ordinal_colours_light_to_dark_up_to_four():
    assert colors.ordinal(3) == ["#6d9efd", "#002fca", "#001959"]
    assert len(colors.ordinal(4)) == 4
    with pytest.raises(ValueError, match="group the levels"):
        colors.ordinal(5)


def test_ink_on_a_mark():
    assert colors.ink_on("#001959") == "white"
    assert colors.ink_on("#6d9efd") == colors.INK
    assert colors.ink_on(colors.NEUTRAL) == colors.INK


def test_style_for_a_block_only():
    before = matplotlib.rcParams["axes.spines.top"]
    with fair2.plot_style({"figure.figsize": (3, 2)}):
        assert matplotlib.rcParams["axes.spines.top"] is False
        assert list(matplotlib.rcParams["figure.figsize"]) == [3, 2]
        assert matplotlib.rcParams["axes.prop_cycle"].by_key()["color"] == colors.CATEGORICAL
        assert "fair2" in matplotlib.colormaps and "fair2_diverging" in matplotlib.colormaps
    assert matplotlib.rcParams["axes.spines.top"] == before


def test_style_for_the_session():
    try:
        fair2.plot_style()
        assert matplotlib.rcParams["image.cmap"] == "fair2"
    finally:
        matplotlib.rcdefaults()


def test_plotly_template_by_default():
    import plotly.express as px
    import plotly.io as pio

    previous = pio.templates.default
    try:
        fair2.plotly_style()
        assert pio.templates.default == "plotly_white+fair2"
        fig = px.bar(x=["a", "b"], y=[1, 2], color=["a", "b"])
        layout = fig.layout.template.layout
        assert list(layout.colorway) == colors.CATEGORICAL
        assert layout.colorscale.diverging[2][1] == colors.DIVERGING[2]
        # The first series takes the first categorical colour.
        assert fig.data[0].marker.color == colors.CATEGORICAL[0]
    finally:
        pio.templates.default = previous
