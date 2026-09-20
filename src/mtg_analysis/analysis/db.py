from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl

from mtg_analysis.config import PeriodGroupConfig
from mtg_analysis.transform.periods import period_lookup

TABLE_NAMES = ("cards", "card_colors", "card_keywords", "sets", "color_totals")


def get_connection(
    processed_dir: Path | str,
    period_cfg: PeriodGroupConfig | None = None,
) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with views over the processed parquet tables.

    Raw JSON is never touched here — analysis reads only the normalized tables. The
    period mapping is computed at connection time from `period_cfg`, so switching
    between per-set and grouped periods needs no rebuild.
    """
    processed_dir = Path(processed_dir)
    con = duckdb.connect()
    for name in TABLE_NAMES:
        path = processed_dir / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"missing table {path}; run `mtg-analysis build` first")
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path.as_posix()}')")

    cfg = period_cfg or PeriodGroupConfig()
    sets_df = con.execute("SELECT * FROM sets").pl()
    periods_df = period_lookup(sets_df, cfg)
    register_periods(con, periods_df)
    return con


def register_periods(con: duckdb.DuckDBPyConnection, periods_df: pl.DataFrame) -> None:
    """(Re)register the set -> period mapping and the derived fact views."""
    con.register("_set_periods_df", periods_df)
    con.execute("CREATE OR REPLACE VIEW set_periods AS SELECT * FROM _set_periods_df")
    con.execute(
        """
        CREATE OR REPLACE VIEW card_facts AS
        SELECT
            c.oracle_id, c.name, c.set, c.set_type, c.in_paper_only, c.rarity,
            c.cmc, c.type_line, c.is_creature, c.is_multiface, c.layout,
            c.released_at, c.first_printed_year, c.n_keywords, c.oracle_text_length,
            cc.color, cc.n_colors_on_card, cc.weight_fractional, cc.weight_inclusive,
            p.period, p.period_order, p.period_released_at
        FROM cards c
        JOIN card_colors cc USING (oracle_id)
        JOIN set_periods p USING (set)
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW keyword_facts AS
        SELECT f.*, k.keyword
        FROM card_facts f
        JOIN card_keywords k USING (oracle_id)
        """
    )
    con.execute(
        """
        CREATE OR REPLACE VIEW period_color_totals AS
        SELECT p.period, p.period_order, MIN(p.period_released_at) AS period_released_at,
               t.color, t.weighting_scheme, t.set_type_filter,
               SUM(t.total_cards) AS total_cards
        FROM color_totals t
        JOIN set_periods p USING (set)
        GROUP BY p.period, p.period_order, t.color, t.weighting_scheme, t.set_type_filter
        """
    )


def set_period_config(con: duckdb.DuckDBPyConnection, cfg: PeriodGroupConfig) -> None:
    """Switch an open connection to a different period grouping."""
    sets_df = con.execute("SELECT * FROM sets").pl()
    register_periods(con, period_lookup(sets_df, cfg))
