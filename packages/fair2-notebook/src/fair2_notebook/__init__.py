"""What notebooks on FAIR² datasets import when they run.

import mlcroissant as mlc
from fair2_notebook import card

dataset = mlc.Dataset("https://sen.science/doi/10.71728/senscience.f2na-3dct/fair2.json")
card(dataset)  # displayed by Jupyter

Or the top of the card in a Markdown cell, written into the notebook beforehand
(`card(dataset).top_html()`), and its record sets, fields and files below:

structure(dataset)  # displayed by Jupyter
"""

from fair2_notebook.card import DatasetCard, card, structure
from fair2_notebook.themes import FRONTIERS, Theme

__all__ = ["FRONTIERS", "DatasetCard", "Theme", "card", "structure"]
