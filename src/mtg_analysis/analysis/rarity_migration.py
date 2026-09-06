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

RARITY_ORDINAL = {"common": 0, "uncommon": 1, "rare": 2, "mythic": 3}


def rarity_migration(
    con: duckdb.DuckDBPyConnection,
    keyword: str,
    by_color: bool = False,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> pl.DataFrame:
    """Weighted mean rarity of a keyword's appearances per period.

    Rising values mean the mechanic is being rare-gated; falling values mean it is being
    pushed down to common. `n_appearances` is reported so thin periods can be ignored.
    """
    validate_options(weighting, set_type_filter)
    group = "period, period_order, color" if by_color else "period, period_order"
    df = con.execute(
        f"""
        SELECT {group},
               MIN(period_released_at) AS period_released_at,
               SUM(weight_{weighting} * CASE rarity
                     WHEN 'common' THEN 0 WHEN 'uncommon' THEN 1
                     WHEN 'rare' THEN 2 WHEN 'mythic' THEN 3 END)
                 / NULLIF(SUM(CASE WHEN rarity IN ('common','uncommon','rare','mythic')
                                   THEN weight_{weighting} END), 0) AS mean_rarity,
               COUNT(*) AS n_appearances,
               SUM(weight_{weighting}) AS keyword_weight
        FROM keyword_facts
        WHERE keyword = ?{filter_clause(set_type_filter)}
        GROUP BY {group}
        ORDER BY period_order
        """,
        [keyword],
    ).pl()
    return df.with_columns(
        pl.lit(keyword).alias("keyword"), pl.lit(weighting).alias("weighting")
    )


def plot_rarity_migration(
    df: pl.DataFrame, ax: Any | None = None, title: str | None = None
) -> Any:
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 4.5))

    if "color" in df.columns:
        for color in [c for c in COLOR_ORDER if c in df["color"].unique().to_list()]:
            sub = df.filter(pl.col("color") == color).sort("period_order")
            plot_color_series(
                ax, sub["period_released_at"].to_list(), sub["mean_rarity"].to_list(), color
            )
        add_legend(ax)
    else:
        sub = df.sort("period_order")
        ax.plot(
            sub["period_released_at"].to_list(),
            sub["mean_rarity"].to_list(),
            color="#2563EB",
            linewidth=2,
            marker="o",
            markersize=4,
        )

    keyword = df["keyword"][0] if df.height else ""
    style_axes(ax, title=title or f"{keyword}: mean rarity over time", ylabel="mean rarity")
    ax.set_yticks(list(RARITY_ORDINAL.values()), list(RARITY_ORDINAL.keys()))
    ax.set_xlabel("set release date", color=MUTED_INK, fontsize=10)
    return ax
