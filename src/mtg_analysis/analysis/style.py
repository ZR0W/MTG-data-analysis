from __future__ import annotations

from typing import Any

COLOR_ORDER = ["W", "U", "B", "R", "G", "C"]

COLOR_LABEL = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
    "C": "Colorless",
}

# WUBRG hues stepped until they clear the categorical palette checks (lightness band,
# chroma floor, CVD separation, contrast) against both light and dark surfaces. Red and
# green sit in the 6-8 deutan band, which is only legal alongside secondary encoding —
# hence the per-color dash pattern and marker below, and direct labels on every series.
COLOR_HEX = {
    "W": "#AD8A16",
    "U": "#2563EB",
    "B": "#A33FB5",
    "R": "#D93025",
    "G": "#0E9A6E",
    # Colorless is deliberately the one neutral: it reads as "no color" rather than as a
    # sixth hue, and always carries a dashed line plus a direct label.
    "C": "#6B7280",
}

LINE_STYLE = {
    "W": "-",
    "U": (0, (6, 2)),
    "B": (0, (3, 1, 1, 1)),
    "R": (0, (1, 1)),
    "G": (0, (5, 1, 1, 1, 1, 1)),
    "C": (0, (2, 2)),
}

MARKER = {"W": "o", "U": "s", "B": "D", "R": "^", "G": "v", "C": "x"}

SEQUENTIAL_CMAP = "Blues"

INK = "#33322e"
MUTED_INK = "#73726c"
GRID = "#e5e4df"


def style_axes(ax: Any, title: str | None = None, ylabel: str | None = None) -> Any:
    """Recessive grid and axes; text in ink tokens rather than series colors."""
    ax.grid(True, axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED_INK, labelsize=9)
    if title:
        ax.set_title(title, color=INK, fontsize=12, loc="left", pad=12)
    if ylabel:
        ax.set_ylabel(ylabel, color=MUTED_INK, fontsize=10)
    return ax


def plot_color_series(ax: Any, x, y, color_code: str, label: str | None = None) -> Any:
    """One MTG color's series, with the dash pattern and marker that carry identity."""
    return ax.plot(
        x,
        y,
        color=COLOR_HEX.get(color_code, MUTED_INK),
        linestyle=LINE_STYLE.get(color_code, "-"),
        marker=MARKER.get(color_code, "o"),
        markersize=4,
        linewidth=2,
        label=label or COLOR_LABEL.get(color_code, color_code),
    )


def add_legend(ax: Any) -> Any:
    legend = ax.legend(frameon=False, fontsize=9, labelcolor=MUTED_INK, ncols=3)
    return legend
