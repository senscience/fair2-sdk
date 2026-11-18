import math

import numpy as np
import plotly.graph_objects as go
import pytest
from plotly.subplots import make_subplots

from fair2_notebook import fit


def wide(width=2000, height=500, **layout):
    figure = go.Figure(
        go.Scatter(x=[1, 2, 3], y=[4, 5, 6], marker={"size": 20}, line={"width": 4}),
        layout={"width": width, "height": height, "margin": {"l": 100, "r": 40}, **layout},
    )
    figure.update_layout(font={"size": 16}, xaxis={"tickfont": {"size": 14}})
    return figure


def test_shown_as_it_is():
    # Not a Plotly figure, no fixed width (Plotly fills the cell), within the notebook's width
    table = object()
    assert fit(table) is table
    autosized = go.Figure(go.Bar(x=[1], y=[2]))
    assert fit(autosized) is autosized
    narrow = wide(width=900)
    assert fit(narrow) is narrow


def test_shrunk_to_the_width_keeping_its_ratio():
    figure = wide(width=2000, height=500)
    small = fit(figure)
    assert (small.layout.width, small.layout.height) == (1000, 250)
    # Every size in pixels by the same factor
    assert small.layout.margin.l == 50 and small.layout.margin.r == 20
    assert small.data[0].marker.size == 10 and small.data[0].line.width == 2
    # The figure itself unchanged, and the data of the copy too
    assert figure.layout.width == 2000 and figure.data[0].marker.size == 20
    assert list(small.data[0].x) == [1, 2, 3] and list(small.data[0].y) == [4, 5, 6]


def test_texts_not_below_the_smallest_size():
    small = fit(wide(width=2000), min_text=10)
    # 16 and 14 px halved would be 8 and 7: 10 at least
    assert small.layout.font.size == 10 and small.layout.xaxis.tickfont.size == 10
    # A text already smaller keeps its own size
    tiny = wide(width=2000)
    tiny.update_layout(yaxis={"tickfont": {"size": 8}})
    assert fit(tiny).layout.yaxis.tickfont.size == 8
    # Texts without a size of their own take the layout's: Plotly's 12 px, shrunk too
    plain = go.Figure(go.Bar(x=[1], y=[2]), layout={"width": 1500, "height": 300})
    assert fit(plain).layout.font.size == 10


def test_very_wide_figures_shrink_as_far_as_they_stay_readable():
    small = fit(wide(width=3400, height=800))
    # Not below 0.45: 1530 px, wider than the notebook
    assert math.isclose(small.layout.width, 1530) and math.isclose(small.layout.height, 360)


def test_a_figure_without_a_height():
    figure = go.Figure(go.Bar(x=[1], y=[2]), layout={"width": 2000})
    # Plotly's default height, 450 px: the ratio is kept
    assert fit(figure).layout.height == 225


def test_font_sizes_written_in_texts():
    figure = wide(width=2000)
    figure.update_yaxes(
        tickvals=[4, 5],
        ticktext=['<span style="font-size:24px">a</span>', '<span style="font-size:12px">b</span>'],
    )
    assert list(fit(figure).layout.yaxis.ticktext) == [
        '<span style="font-size:12.0px">a</span>',
        '<span style="font-size:10.0px">b</span>',
    ]


def test_subplots_annotations_and_colorbars():
    figure = make_subplots(rows=1, cols=2, subplot_titles=["A", "B"])
    figure.add_trace(go.Heatmap(z=[[1, np.nan], [3, 4]], colorbar={"thickness": 40}), 1, 1)
    figure.add_trace(go.Bar(x=[1, 2], y=[3, 4]), 1, 2)
    figure.update_layout(width=2000, height=800)
    figure.update_annotations(font_size=20)
    small = fit(figure)
    # The subplot titles are annotations: their texts shrink, not below 10 px
    assert all(a.font.size == 10 for a in small.layout.annotations)
    assert small.data[0].colorbar.thickness == 20
    # Missing values in the data are kept as they are
    assert np.isnan(small.data[0].z[0][1])


def test_marker_sizes_in_the_data_units():
    # Bubble sizes are the data: their reference changes, not them
    figure = go.Figure(
        go.Scatter(x=[1, 2], y=[1, 2], marker={"size": [10, 40], "sizeref": 2, "sizemode": "area"}),
        layout={"width": 2000, "height": 1000},
    )
    small = fit(figure)
    assert list(small.data[0].marker.size) == [10, 40]
    assert small.data[0].marker.sizeref == pytest.approx(8)


def test_other_settings():
    small = fit(wide(width=4000), width=800, min_text=6, smallest=0.1)
    assert small.layout.width == 800 and small.layout.font.size == 6
