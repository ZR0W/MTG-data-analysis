from __future__ import annotations

from typing import Any

import duckdb
import numpy as np
import polars as pl

from mtg_analysis.analysis.style import (
    COLOR_ORDER,
    MUTED_INK,
    add_legend,
    plot_color_series,
    style_axes,
)
from mtg_analysis.metrics.core import SetTypeFilter, Weighting, filter_clause, validate_options


def keyword_vectors(
    con: duckdb.DuckDBPyConnection,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> pl.DataFrame:
    """Normalized keyword-frequency vector per (period, color).

    Each color's vector sums to 1.0 within a period, so drift measures a change in the
    mix of a color's toolbox rather than a change in how much it printed.
    """
    validate_options(weighting, set_type_filter)
    df = con.execute(
        f"""
        SELECT period, period_order, color, keyword, SUM(weight_{weighting}) AS weight
        FROM keyword_facts
        WHERE TRUE{filter_clause(set_type_filter)}
        GROUP BY period, period_order, color, keyword
        """
    ).pl()
    totals = df.group_by(["period", "color"]).agg(pl.col("weight").sum().alias("total"))
    return (
        df.join(totals, on=["period", "color"])
        .with_columns((pl.col("weight") / pl.col("total")).alias("freq"))
        .sort(["color", "period_order", "keyword"])
    )


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else float("nan")


def color_drift(
    con: duckdb.DuckDBPyConnection,
    colors: list[str] | None = None,
    min_keyword_weight: float = 5.0,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> pl.DataFrame:
    """Cosine similarity of each color's keyword mix vs. the previous period and vs. its
    all-time baseline. Low similarity means the color's toolbox shifted."""
    vectors = keyword_vectors(con, weighting, set_type_filter)
    colors = colors or [c for c in COLOR_ORDER if c in vectors["color"].unique().to_list()]
    keywords = sorted(vectors["keyword"].unique().to_list())
    index = {k: i for i, k in enumerate(keywords)}

    rows: list[dict] = []
    for color in colors:
        sub = vectors.filter(pl.col("color") == color)
        if sub.is_empty():
            continue
        baseline = np.zeros(len(keywords))
        for keyword, weight in zip(sub["keyword"], sub["weight"], strict=True):
            baseline[index[keyword]] += weight
        baseline_norm = baseline / baseline.sum() if baseline.sum() else baseline

        previous: np.ndarray | None = None
        for period, period_order in (
            sub.select("period", "period_order").unique().sort("period_order").rows()
        ):
            chunk = sub.filter(pl.col("period") == period)
            if chunk["weight"].sum() < min_keyword_weight:
                previous = None
                continue
            vec = np.zeros(len(keywords))
            for keyword, freq in zip(chunk["keyword"], chunk["freq"], strict=True):
                vec[index[keyword]] = freq
            rows.append(
                {
                    "color": color,
                    "period": period,
                    "period_order": period_order,
                    "cosine_vs_previous": _cosine(vec, previous) if previous is not None else None,
                    "cosine_vs_baseline": _cosine(vec, baseline_norm),
                    "keyword_weight": float(chunk["weight"].sum()),
                }
            )
            previous = vec
    return pl.DataFrame(rows).sort(["color", "period_order"]) if rows else pl.DataFrame()


def plot_color_drift(
    df: pl.DataFrame,
    metric: str = "cosine_vs_baseline",
    ax: Any | None = None,
    title: str | None = None,
) -> Any:
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(10, 4.5))
    for color in [c for c in COLOR_ORDER if c in df["color"].unique().to_list()]:
        sub = df.filter(pl.col("color") == color).sort("period_order")
        plot_color_series(ax, sub["period_order"].to_list(), sub[metric].to_list(), color)
    style_axes(ax, title=title or f"Colour identity drift ({metric})", ylabel="cosine similarity")
    ax.set_xlabel("period (sets in release order)", color=MUTED_INK, fontsize=10)
    add_legend(ax)
    return ax
