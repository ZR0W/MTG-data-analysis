from __future__ import annotations

from typing import Any

import duckdb
import polars as pl

from mtg_analysis.analysis.style import (
    COLOR_LABEL,
    COLOR_ORDER,
    MUTED_INK,
    SEQUENTIAL_CMAP,
    style_axes,
)
from mtg_analysis.metrics.core import SetTypeFilter, Weighting, filter_clause, validate_options


def keyword_color_matrix(
    con: duckdb.DuckDBPyConnection,
    keywords: list[str] | None = None,
    top_n: int = 25,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> pl.DataFrame:
    """Keyword x color table over the full history: raw counts and color shares.

    `share` uses the chosen weighting and sums to 1.0 across colors within a keyword
    (under fractional weighting); `raw_count` is an unweighted headcount, so the two
    columns answer different questions and are both kept.
    """
    validate_options(weighting, set_type_filter)
    params: list[object] = []
    keyword_clause = ""
    if keywords:
        keyword_clause = f" AND keyword IN ({', '.join('?' for _ in keywords)})"
        params.extend(keywords)

    df = con.execute(
        f"""
        SELECT keyword, color,
               COUNT(*) AS raw_count,
               SUM(weight_{weighting}) AS weight
        FROM keyword_facts
        WHERE TRUE{keyword_clause}{filter_clause(set_type_filter)}
        GROUP BY keyword, color
        """,
        params,
    ).pl()

    if df.is_empty():
        return df

    totals = df.group_by("keyword").agg(
        pl.col("weight").sum().alias("keyword_weight"),
        pl.col("raw_count").sum().alias("keyword_count"),
    )
    df = (
        df.join(totals, on="keyword")
        .with_columns((pl.col("weight") / pl.col("keyword_weight")).alias("share"))
        .with_columns(
            pl.lit(weighting).alias("weighting"),
            pl.lit(set_type_filter).alias("set_type_filter"),
        )
    )

    if keywords is None and top_n:
        keep = (
            totals.sort("keyword_count", descending=True).head(top_n)["keyword"].to_list()
        )
        df = df.filter(pl.col("keyword").is_in(keep))
    return df.sort(["keyword_count", "keyword", "color"], descending=[True, False, False])


def pivot_matrix(matrix: pl.DataFrame, value: str = "share") -> pl.DataFrame:
    """Wide keyword x color grid, columns in WUBRG order, missing cells as 0."""
    wide = matrix.pivot(on="color", index="keyword", values=value).fill_null(0.0)
    present = [c for c in COLOR_ORDER if c in wide.columns]
    return wide.select(["keyword", *present])


def plot_keyword_color_heatmap(
    matrix: pl.DataFrame,
    value: str = "share",
    ax: Any | None = None,
    title: str | None = None,
) -> Any:
    """Sequential single-hue heatmap; cell values are labelled so color is never the
    only channel carrying magnitude."""
    import matplotlib.pyplot as plt

    wide = pivot_matrix(matrix, value)
    colors = [c for c in wide.columns if c != "keyword"]
    data = wide.select(colors).to_numpy()
    keywords = wide["keyword"].to_list()

    if ax is None:
        _, ax = plt.subplots(figsize=(1.1 * len(colors) + 3, 0.34 * len(keywords) + 2))

    im = ax.imshow(data, cmap=SEQUENTIAL_CMAP, aspect="auto")
    ax.set_xticks(range(len(colors)), [COLOR_LABEL.get(c, c) for c in colors])
    ax.set_yticks(range(len(keywords)), keywords)
    ax.grid(False)
    fmt = "{:.0%}" if value == "share" else "{:.0f}"
    threshold = data.max() * 0.6 if data.size else 0
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            ax.text(
                j,
                i,
                fmt.format(data[i, j]),
                ha="center",
                va="center",
                fontsize=7,
                color="white" if data[i, j] > threshold else MUTED_INK,
            )
    style_axes(ax, title=title or f"Keyword x color ({value})")
    ax.grid(False)
    ax.figure.colorbar(im, ax=ax, shrink=0.6, label=value)
    return ax
