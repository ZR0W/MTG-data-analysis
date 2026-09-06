from __future__ import annotations

from typing import Any

import duckdb
import polars as pl

from mtg_analysis.analysis.style import (
    COLOR_LABEL,
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


def keyword_shares_by_period(
    con: duckdb.DuckDBPyConnection,
    keyword: str,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> pl.DataFrame:
    validate_options(weighting, set_type_filter)
    df = con.execute(
        f"""
        SELECT period, period_order, MIN(period_released_at) AS period_released_at, color,
               SUM(weight_{weighting}) AS weight, COUNT(*) AS raw_count
        FROM keyword_facts
        WHERE keyword = ?{filter_clause(set_type_filter)}
        GROUP BY period, period_order, color
        """,
        [keyword],
    ).pl()
    if df.is_empty():
        return df
    totals = df.group_by("period").agg(pl.col("weight").sum().alias("period_weight"))
    return (
        df.join(totals, on="period")
        .with_columns((pl.col("weight") / pl.col("period_weight")).alias("share"))
        .sort(["period_order", "color"])
    )


def pie_break(
    con: duckdb.DuckDBPyConnection,
    keyword: str,
    min_period_weight: float = 3.0,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> pl.DataFrame:
    """Track how much of a keyword has leaked out of its historically dominant color.

    The dominant color is whichever held the top share in the earliest period carrying
    at least `min_period_weight` of the keyword; `challenger_share` is everything else.
    """
    shares = keyword_shares_by_period(con, keyword, weighting, set_type_filter)
    if shares.is_empty():
        return shares

    qualifying = shares.filter(pl.col("period_weight") >= min_period_weight)
    if qualifying.is_empty():
        return pl.DataFrame()

    first_period = qualifying.sort("period_order")["period"][0]
    dominant = (
        qualifying.filter(pl.col("period") == first_period)
        .sort("share", descending=True)["color"][0]
    )

    return (
        qualifying.with_columns(
            pl.lit(dominant).alias("original_dominant_color"),
            (pl.col("color") == dominant).alias("is_original_dominant"),
        )
        .with_columns(
            pl.when(pl.col("is_original_dominant"))
            .then(pl.col("share"))
            .otherwise(0.0)
            .alias("dominant_share")
        )
        .with_columns(
            (1.0 - pl.col("dominant_share").sum().over("period")).alias("challenger_share")
        )
        .sort(["period_order", "color"])
    )


def plot_pie_break(df: pl.DataFrame, ax: Any | None = None, title: str | None = None) -> Any:
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 4.5))
    for color in [c for c in COLOR_ORDER if c in df["color"].unique().to_list()]:
        sub = df.filter(pl.col("color") == color).sort("period_order")
        plot_color_series(ax, sub["period_released_at"].to_list(), sub["share"].to_list(), color)

    dominant = df["original_dominant_color"][0] if df.height else "?"
    style_axes(
        ax,
        title=title or f"Share of keyword by colour (originally {COLOR_LABEL.get(dominant)})",
        ylabel="share of keyword",
    )
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlabel("set release date", color=MUTED_INK, fontsize=10)
    add_legend(ax)
    return ax
