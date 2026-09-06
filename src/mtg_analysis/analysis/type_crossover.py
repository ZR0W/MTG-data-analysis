from __future__ import annotations

from typing import Any

import duckdb
import polars as pl

from mtg_analysis.analysis.style import GRID, MUTED_INK, add_legend, style_axes
from mtg_analysis.metrics.core import (
    SetTypeFilter,
    Weighting,
    filter_clause,
    validate_options,
)

# Checked in order — a card is bucketed by the first type that matches its type line.
TYPE_BUCKETS = [
    ("Creature", "creature"),
    ("Planeswalker", "planeswalker"),
    ("Instant/Sorcery", "instant"),
    ("Instant/Sorcery", "sorcery"),
    ("Enchantment", "enchantment"),
    ("Artifact", "artifact"),
    ("Land", "land"),
]

_TYPE_CASE = "\n".join(
    f"WHEN lower(type_line) LIKE '%{needle}%' THEN '{label}'" for label, needle in TYPE_BUCKETS
)


def type_crossover(
    con: duckdb.DuckDBPyConnection,
    keyword: str,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> pl.DataFrame:
    """Share of a keyword's appearances on each card type, per period."""
    validate_options(weighting, set_type_filter)
    df = con.execute(
        f"""
        SELECT period, period_order, MIN(period_released_at) AS period_released_at,
               CASE {_TYPE_CASE} ELSE 'Other' END AS card_type,
               SUM(weight_{weighting}) AS weight,
               COUNT(*) AS raw_count
        FROM keyword_facts
        WHERE keyword = ?{filter_clause(set_type_filter)}
        GROUP BY period, period_order, card_type
        """,
        [keyword],
    ).pl()
    if df.is_empty():
        return df
    totals = df.group_by("period").agg(pl.col("weight").sum().alias("period_weight"))
    return (
        df.join(totals, on="period")
        .with_columns(
            (pl.col("weight") / pl.col("period_weight")).alias("share"),
            pl.lit(keyword).alias("keyword"),
        )
        .sort(["period_order", "card_type"])
    )


def plot_type_crossover(
    df: pl.DataFrame, ax: Any | None = None, title: str | None = None
) -> Any:
    """Stacked share-of-appearances by card type, with a surface gap between segments."""
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 4.5))

    wide = df.pivot(on="card_type", index=["period_order", "period_released_at"],
                    values="share").fill_null(0.0).sort("period_order")
    x = wide["period_released_at"].to_list()
    types = [c for c in wide.columns if c not in ("period_order", "period_released_at")]
    # Sequential steps of one hue: the categories here are ordered parts of a whole.
    ramp = plt.get_cmap("Blues")
    bottom = [0.0] * len(x)
    for i, card_type in enumerate(types):
        values = wide[card_type].to_list()
        ax.fill_between(
            x,
            bottom,
            [b + v for b, v in zip(bottom, values, strict=True)],
            label=card_type,
            color=ramp(0.25 + 0.65 * i / max(len(types) - 1, 1)),
            linewidth=1,
            edgecolor=GRID,
        )
        bottom = [b + v for b, v in zip(bottom, values, strict=True)]

    keyword = df["keyword"][0] if df.height else ""
    style_axes(ax, title=title or f"{keyword}: appearances by card type", ylabel="share")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlabel("set release date", color=MUTED_INK, fontsize=10)
    add_legend(ax)
    return ax
