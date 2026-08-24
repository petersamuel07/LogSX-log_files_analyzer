"""Matplotlib chart generation for log analytics.

``FigureBuilder`` builds the figures; ``ChartGenerator`` saves them as PNGs and
the GUI dashboard embeds the same objects directly in the window.
"""

from log_analyzer.visualization.charts import ChartGenerator
from log_analyzer.visualization.figures import Chart, FigureBuilder
from log_analyzer.visualization.theme import DARK_THEME, LIGHT_THEME, ChartTheme

__all__ = ["ChartGenerator", "FigureBuilder", "Chart", "ChartTheme", "LIGHT_THEME", "DARK_THEME"]
