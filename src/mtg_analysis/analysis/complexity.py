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
from mtg_analysis.metrics.core import (
    SetTypeFilter,
    Weighting,
    filter_clause,
    validate_options,
)


def complexity_by_color(
    con: duckdb.DuckDBPyConnection,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> pl.DataFrame:
    """Rules-bloat proxy: mean oracle text length and mean keyword count per colour/period.

    Weighted by the colour weights, so a two-colour card contributes half to each colour
    under fractional weighting rather than being counted twice.
    """
    validate_options(weighting, set_type_filter)
    return con.execute(
        f"""
        SELECT period, period_order, MIN(period_released_at) AS period_released_at, color,
               SUM(oracle_text_length * weight_{weighting})
                 / NULLIF(SUM(weight_{weighting}), 0) AS mean_text_length,
               SUM(n_keywords * weight_{weighting})
                 / NULLIF(SUM(weight_{weighting}), 0) AS mean_keywords,
               SUM(weight_{weighting}) AS color_total,
               COUNT(*) AS n_cards
        FROM card_facts
        WHERE TRUE{filter_clause(set_type_filter)}
        GROUP BY period, period_order, color
        ORDER BY period_order, color
        """
    ).pl()


def plot_complexity(
    df: pl.DataFrame,
    metric: str = "mean_text_length",
    ax: Any | None = None,
    title: str | None = None,
) -> Any:
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 4.5))
    for color in [c for c in COLOR_ORDER if c in df["color"].unique().to_list()]:
        sub = df.filter(pl.col("color") == color).sort("period_order")
        plot_color_series(ax, sub["period_released_at"].to_list(), sub[metric].to_list(), color)
    style_axes(ax, title=title or f"Complexity proxy: {metric.replace('_', ' ')}", ylabel=metric)
    ax.set_xlabel("set release date", color=MUTED_INK, fontsize=10)
    add_legend(ax)
    return ax
