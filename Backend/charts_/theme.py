"""Sonar look for every chart: colours, font and axis style."""
import logging

import matplotlib
matplotlib.use("Agg")  # render to files, never open a window
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib import font_manager

SLATE = "#4a4959"   # main data colour
ORANGE = "#c98633"  # secondary series / reference lines
RED = "#c8161d"     # errors, breaches, outliers
GREEN = "#2f8a4c"   # success
INK = "#1f1f29"
MUTED = "#73737f"
GRID = "#e9e9ee"

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)


def apply_theme() -> None:
    # Use Poppins if it is installed, otherwise fall back quietly
    for path in font_manager.findSystemFonts():
        if "Poppins" in path:
            font_manager.fontManager.addfont(path)
    plt.rcParams.update({
        "font.family": ["Poppins", "DejaVu Sans"],
        "font.size": 9,
        "axes.edgecolor": "#cfcfd6",
        "axes.labelcolor": MUTED,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlecolor": INK,
        "axes.titlelocation": "left",
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.axisbelow": True,
        "legend.frameon": False,
        "figure.dpi": 170,
    })


def fmt_ms(value: float) -> str:
    """250 -> '250 ms', 2400 -> '2.4 s'."""
    if value >= 1000:
        return f"{value / 1000:.1f} s"
    return f"{value:.0f} ms"


MS_FORMATTER = mticker.FuncFormatter(
    lambda v, _: f"{v / 1000:g} s" if v >= 1000 else f"{v:g} ms"
)