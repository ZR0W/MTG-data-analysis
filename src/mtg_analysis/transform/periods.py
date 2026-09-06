from __future__ import annotations

import polars as pl

from mtg_analysis.config import PeriodGroupConfig


def build_sets_table(cards_df: pl.DataFrame) -> pl.DataFrame:
    """One row per set, chronologically ordered — the timeline axis for every analysis.

    A set's release date is the earliest release date among its cards. `set_order` is
    0-based and ties on release date are broken by set code so the ordering is stable
    across rebuilds.
    """
    sets = (
        cards_df.group_by("set")
        .agg(
            pl.col("set_name").first(),
            pl.col("set_type").first(),
            pl.col("released_at").min().alias("released_at"),
            pl.len().alias("n_cards"),
        )
        .sort(["released_at", "set"], nulls_last=True)
        .with_row_index("set_order")
        .with_columns(pl.col("set_order").cast(pl.Int64))
    )
    return sets.select(
        "set", "set_name", "set_type", "released_at", "set_order", "n_cards"
    )


def assign_period(sets_df: pl.DataFrame, cfg: PeriodGroupConfig) -> pl.DataFrame:
    """Add `period`, `period_order` and `period_released_at` columns to a sets table.

    per_set: each set is its own period (breakpoints at each set's release date).
    rolling_sets: `group_size` consecutive sets form one period, labelled
    "<first set>..<last set>" — the noise-smoothing knob for small sets.
    """
    if cfg.mode == "per_set":
        return sets_df.with_columns(
            pl.col("set").alias("period"),
            pl.col("set_order").alias("period_order"),
            pl.col("released_at").alias("period_released_at"),
        )

    grouped = sets_df.sort("set_order").with_columns(
        (pl.col("set_order") // cfg.group_size).alias("period_order")
    )
    labels = grouped.group_by("period_order").agg(
        pl.col("set").sort_by("set_order").first().alias("_first_set"),
        pl.col("set").sort_by("set_order").last().alias("_last_set"),
        pl.col("released_at").min().alias("period_released_at"),
    )
    return (
        grouped.join(labels, on="period_order", how="left")
        .with_columns(
            pl.when(pl.col("_first_set") == pl.col("_last_set"))
            .then(pl.col("_first_set"))
            .otherwise(pl.col("_first_set") + ".." + pl.col("_last_set"))
            .alias("period")
        )
        .drop("_first_set", "_last_set")
    )


def period_lookup(sets_df: pl.DataFrame, cfg: PeriodGroupConfig) -> pl.DataFrame:
    """set -> period mapping, the join key between card-level tables and the timeline."""
    return assign_period(sets_df, cfg).select(
        "set", "period", "period_order", "period_released_at"
    )
