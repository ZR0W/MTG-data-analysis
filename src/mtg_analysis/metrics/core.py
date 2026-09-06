from __future__ import annotations

import math
from typing import Literal

import duckdb
import polars as pl

Weighting = Literal["fractional", "inclusive"]
SetTypeFilter = Literal["paper_only", "unfiltered"]

VALID_WEIGHTINGS = ("fractional", "inclusive")
VALID_FILTERS = ("paper_only", "unfiltered")


def validate_options(weighting: str, set_type_filter: str) -> None:
    if weighting not in VALID_WEIGHTINGS:
        raise ValueError(f"weighting must be one of {VALID_WEIGHTINGS}, got {weighting!r}")
    if set_type_filter not in VALID_FILTERS:
        raise ValueError(f"set_type_filter must be one of {VALID_FILTERS}, got {set_type_filter!r}")


def filter_clause(set_type_filter: str) -> str:
    return " AND in_paper_only" if set_type_filter == "paper_only" else ""


def keyword_weights_by_period(
    con: duckdb.DuckDBPyConnection,
    keyword: str,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> pl.DataFrame:
    """Summed color weights for one keyword, per period and color."""
    validate_options(weighting, set_type_filter)
    return con.execute(
        f"""
        SELECT period, period_order, color,
               SUM(weight_{weighting}) AS keyword_weight,
               COUNT(*) AS raw_count
        FROM keyword_facts
        WHERE keyword = ?{filter_clause(set_type_filter)}
        GROUP BY period, period_order, color
        ORDER BY period_order, color
        """,
        [keyword],
    ).pl()


def raw_count(
    con: duckdb.DuckDBPyConnection,
    keyword: str,
    color: str,
    period: str | None = None,
    set_type_filter: SetTypeFilter = "paper_only",
) -> int:
    """Number of cards carrying `keyword` that include `color` (unweighted headcount)."""
    validate_options("fractional", set_type_filter)
    period_clause = " AND period = ?" if period is not None else ""
    params: list[object] = [keyword, color]
    if period is not None:
        params.append(period)
    row = con.execute(
        f"""
        SELECT COUNT(*) FROM keyword_facts
        WHERE keyword = ? AND color = ?{period_clause}{filter_clause(set_type_filter)}
        """,
        params,
    ).fetchone()
    return int(row[0])


def color_share(
    con: duckdb.DuckDBPyConnection,
    keyword: str,
    color: str,
    period: str | None = None,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> float:
    """Share of a keyword's appearances held by one color.

    Answers "60% of Double Strike is red". Returns NaN when the keyword has no
    appearances in the period — a missing denominator is not a 0% share.
    """
    validate_options(weighting, set_type_filter)
    period_clause = " AND period = ?" if period is not None else ""
    params: list[object] = [keyword]
    if period is not None:
        params.append(period)
    row = con.execute(
        f"""
        SELECT
            SUM(CASE WHEN color = ? THEN weight_{weighting} ELSE 0 END) AS numerator,
            SUM(weight_{weighting}) AS denominator
        FROM keyword_facts
        WHERE keyword = ?{period_clause}{filter_clause(set_type_filter)}
        """,
        [color, *params],
    ).fetchone()
    numerator, denominator = row[0], row[1]
    if not denominator:
        return math.nan
    return float(numerator) / float(denominator)


def penetration_rate(
    con: duckdb.DuckDBPyConnection,
    keyword: str,
    color: str,
    period: str | None = None,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> float:
    """Share of a color's cards that carry the keyword — the dilution-proof metric.

    Answers "what % of red cards have Haste". Returns NaN when the color printed
    nothing in the period.
    """
    validate_options(weighting, set_type_filter)
    period_clause = " AND period = ?" if period is not None else ""
    numerator_params: list[object] = [keyword, color]
    if period is not None:
        numerator_params.append(period)
    numerator = con.execute(
        f"""
        SELECT COALESCE(SUM(weight_{weighting}), 0) FROM keyword_facts
        WHERE keyword = ? AND color = ?{period_clause}{filter_clause(set_type_filter)}
        """,
        numerator_params,
    ).fetchone()[0]

    denominator_params: list[object] = [color, weighting, set_type_filter]
    if period is not None:
        denominator_params.append(period)
    denominator = con.execute(
        f"""
        SELECT COALESCE(SUM(total_cards), 0) FROM period_color_totals
        WHERE color = ? AND weighting_scheme = ? AND set_type_filter = ?
        {"AND period = ?" if period is not None else ""}
        """,
        denominator_params,
    ).fetchone()[0]

    if not denominator:
        return math.nan
    return float(numerator) / float(denominator)


def trend_report(
    con: duckdb.DuckDBPyConnection,
    keyword: str,
    color: str,
    periods: list[str] | None = None,
    weighting: Weighting = "fractional",
    set_type_filter: SetTypeFilter = "paper_only",
) -> pl.DataFrame:
    """Raw count, color share and penetration rate side by side, per period.

    Share and penetration can move in opposite directions (a color's share of a keyword
    can rise while its raw usage falls, because every color printed less of it), so this
    reports them together, alongside the `color_total` denominator and an explicit
    label for the weighting scheme in use.
    """
    validate_options(weighting, set_type_filter)
    period_clause = ""
    if periods is not None:
        placeholders = ", ".join("?" for _ in periods)
        period_clause = f" AND period IN ({placeholders})"

    df = con.execute(
        f"""
        WITH kw AS (
            SELECT period, period_order,
                   SUM(CASE WHEN color = ? THEN weight_{weighting} ELSE 0 END) AS color_weight,
                   SUM(weight_{weighting}) AS keyword_weight,
                   SUM(CASE WHEN color = ? THEN 1 ELSE 0 END) AS raw_count
            FROM keyword_facts
            WHERE keyword = ?{period_clause}{filter_clause(set_type_filter)}
            GROUP BY period, period_order
        ),
        totals AS (
            SELECT period, period_order, MIN(period_released_at) AS period_released_at,
                   SUM(total_cards) AS color_total
            FROM period_color_totals
            WHERE color = ? AND weighting_scheme = ? AND set_type_filter = ?{period_clause}
            GROUP BY period, period_order
        )
        SELECT
            t.period,
            t.period_order,
            t.period_released_at,
            COALESCE(kw.raw_count, 0) AS raw_count,
            CASE WHEN kw.keyword_weight > 0 THEN kw.color_weight / kw.keyword_weight END
                AS color_share,
            CASE WHEN t.color_total > 0 THEN COALESCE(kw.color_weight, 0) / t.color_total END
                AS penetration_rate,
            t.color_total
        FROM totals t
        LEFT JOIN kw USING (period, period_order)
        ORDER BY t.period_order
        """,
        _trend_params(color, keyword, periods, weighting, set_type_filter),
    ).pl()

    return df.with_columns(
        pl.lit(keyword).alias("keyword"),
        pl.lit(color).alias("color"),
        pl.lit(weighting).alias("weighting"),
        pl.lit(set_type_filter).alias("set_type_filter"),
    )


def _trend_params(
    color: str,
    keyword: str,
    periods: list[str] | None,
    weighting: str,
    set_type_filter: str,
) -> list[object]:
    kw_params: list[object] = [color, color, keyword]
    totals_params: list[object] = [color, weighting, set_type_filter]
    if periods is not None:
        kw_params.extend(periods)
        totals_params.extend(periods)
    return kw_params + totals_params
