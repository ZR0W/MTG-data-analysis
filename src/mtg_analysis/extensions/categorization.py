"""Future work: functional categories (removal, ramp, card draw) rather than keywords.

Same pattern-matching approach as `text_mining`, aimed at "which colour does this job,
and has that shifted" questions — e.g. whether card draw is still blue-dominant. Emits
the same (oracle_id, mechanic) shape so it plugs into the existing `color_totals`
denominators without new rate math.
"""

from __future__ import annotations

import duckdb
import polars as pl

CATEGORIES = ("removal", "ramp", "card_draw", "counterspell", "recursion")


def build_card_categories_table(
    con: duckdb.DuckDBPyConnection, categories: tuple[str, ...] = CATEGORIES
) -> pl.DataFrame:
    """Long table: oracle_id, mechanic (a functional category), matched_pattern."""
    raise NotImplementedError("functional categorization is future work")
