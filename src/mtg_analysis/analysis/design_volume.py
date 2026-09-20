from __future__ import annotations

from typing import Any

import duckdb
import polars as pl

from mtg_analysis.analysis.style import (
    COLOR_ORDER,
    MUTED_INK,
    add_legend,
    plot_color_series,
    style_axes,
)
from mtg_analysis.metrics.core import SetTypeFilter, Weighting, validate_options


def design_volume(
    con: duckdb.DuckDBPyConnection,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> pl.DataFrame:
    """The `color_totals` denominator itself: cards printed per colour per period.

    Pair this with any raw-count chart — a rising or falling count means little without
    the print volume behind it.
    """
    validate_options(weighting, set_type_filter)
    return con.execute(
        """
        SELECT period, period_order, MIN(period_released_at) AS period_released_at,
               color, SUM(total_cards) AS total_cards
        FROM period_color_totals
        WHERE weighting_scheme = ? AND set_type_filter = ?
        GROUP BY period, period_order, color
        ORDER BY period_order, color
        """,
        [weighting, set_type_filter],
    ).pl()


def plot_design_volume(
    df: pl.DataFrame, ax: Any | None = None, title: str | None = None
) -> Any:
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 4.5))
    for color in [c for c in COLOR_ORDER if c in df["color"].unique().to_list()]:
        sub = df.filter(pl.col("color") == color).sort("period_order")
        plot_color_series(
            ax, sub["period_released_at"].to_list(), sub["total_cards"].to_list(), color
        )
    style_axes(ax, title=title or "Cards printed per colour per set", ylabel="cards")
    ax.set_xlabel("set release date", color=MUTED_INK, fontsize=10)
    add_legend(ax)
    return ax
