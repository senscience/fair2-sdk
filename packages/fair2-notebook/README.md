# fair2-notebook

What notebooks on FAIR² datasets import when they run.

```python
import mlcroissant as mlc
from fair2_notebook import card

dataset = mlc.Dataset("https://sen.science/doi/10.71728/senscience.f2na-3dct/fair2.json")
card(dataset)  # displayed by Jupyter
```

Notebooks install this package, pinned, next to the code of their figures: its dependencies
are few, and it doesn't bound mlcroissant's own dependencies (pandas...), which the
figures need at their own versions.
