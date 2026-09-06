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
from mtg_analysis.metrics.core import SetTypeFilter, Weighting, trend_report


def keyword_timeseries(
    con: duckdb.DuckDBPyConnection,
    keyword: str,
    colors: list[str] | None = None,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
    min_color_total: float = 0.0,
) -> pl.DataFrame:
    """Per-period trend for one keyword across colors.

    Returns raw_count, color_share and penetration_rate together for every color, so a
    claim about one metric can always be checked against the other two.
    """
    colors = colors or COLOR_ORDER
    frames = [
        trend_report(con, keyword, color, weighting=weighting, set_type_filter=set_type_filter)
        for color in colors
    ]
    df = pl.concat(frames)
    if min_color_total:
        df = df.filter(pl.col("color_total") >= min_color_total)
    return df.sort(["color", "period_order"])


def plot_keyword_timeseries(
    df: pl.DataFrame,
    metric: str = "penetration_rate",
    ax: Any | None = None,
    title: str | None = None,
) -> Any:
    """Plot one metric per color over time. Never plot two metrics on twin axes —
    call this twice on separate axes instead."""
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 4.5))

    for color in [c for c in COLOR_ORDER if c in df["color"].unique().to_list()]:
        sub = df.filter(pl.col("color") == color).sort("period_order")
        plot_color_series(ax, sub["period_released_at"].to_list(), sub[metric].to_list(), color)

    keyword = df["keyword"].unique().to_list()[0] if "keyword" in df.columns else ""
    weighting = df["weighting"].unique().to_list()[0] if "weighting" in df.columns else ""
    # The weighting scheme is named in the title, never left implicit.
    default_title = f"{keyword}: {metric.replace('_', ' ')} ({weighting} weighting)"
    style_axes(ax, title=title or default_title, ylabel=metric)
    ax.set_xlabel("set release date", color=MUTED_INK, fontsize=10)
    if metric in ("penetration_rate", "color_share"):
        ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    add_legend(ax)
    return ax
