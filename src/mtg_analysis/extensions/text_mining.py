"""Future work: informal mechanics that are not in Scryfall's `keywords` array.

Patterns like impulse draw ("exile the top card... you may play it this turn") or
rummaging ("discard a card, then draw a card") only exist in `oracle_text`, so they
need a hand-curated pattern dictionary rather than the keyword join.

The output is deliberately shaped like `card_keywords` — one row per
(oracle_id, mechanic) — so `card_facts` can join it exactly the way it joins keywords,
and every metric in `metrics.core` works unchanged against informal mechanics.
Nothing here is implemented until the keyword-based pipeline has been validated.
"""

from __future__ import annotations

import duckdb
import polars as pl


def load_pattern_dictionary(path: str) -> dict[str, list[str]]:
    """mechanic -> list of regexes matched against oracle_text."""
    raise NotImplementedError("informal mechanic mining is future work")


def build_card_mechanics_table(
    con: duckdb.DuckDBPyConnection, patterns: dict[str, list[str]]
) -> pl.DataFrame:
    """Long table: oracle_id, mechanic, matched_pattern."""
    raise NotImplementedError("informal mechanic mining is future work")
