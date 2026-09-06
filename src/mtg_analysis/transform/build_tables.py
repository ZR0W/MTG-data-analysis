from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from pathlib import Path

import polars as pl

from mtg_analysis.config import Config
from mtg_analysis.ingest.bulk_client import ScryfallBulkClient
from mtg_analysis.transform.card_parser import ParsedCard, parse_card
from mtg_analysis.transform.periods import build_sets_table
from mtg_analysis.transform.weights import compute_color_rows

logger = logging.getLogger(__name__)

CARDS_SCHEMA = {
    "oracle_id": pl.Utf8,
    "name": pl.Utf8,
    "colors": pl.List(pl.Utf8),
    "color_identity": pl.List(pl.Utf8),
    "keywords": pl.List(pl.Utf8),
    "type_line": pl.Utf8,
    "oracle_text": pl.Utf8,
    "cmc": pl.Float64,
    "rarity": pl.Utf8,
    "set": pl.Utf8,
    "set_name": pl.Utf8,
    "set_type": pl.Utf8,
    "released_at": pl.Date,
    "layout": pl.Utf8,
    "is_multiface": pl.Boolean,
    "colorless": pl.Boolean,
    "n_colors": pl.Int64,
    "n_keywords": pl.Int64,
    "oracle_text_length": pl.Int64,
    "is_creature": pl.Boolean,
}


def compute_first_printed_year(default_cards_raw: Iterable[dict]) -> pl.DataFrame:
    """Earliest print year per oracle_id across every printing.

    oracle_cards carries one recognizable printing's release date, not the earliest, so
    "when did this first appear" questions need the full default_cards feed.
    """
    earliest: dict[str, int] = {}
    for raw in default_cards_raw:
        oracle_id = raw.get("oracle_id") or next(
            (f.get("oracle_id") for f in raw.get("card_faces") or [] if f.get("oracle_id")),
            None,
        )
        released_at = raw.get("released_at")
        if not oracle_id or not released_at:
            continue
        year = int(released_at[:4])
        if oracle_id not in earliest or year < earliest[oracle_id]:
            earliest[oracle_id] = year
    return pl.DataFrame(
        {
            "oracle_id": list(earliest.keys()),
            "first_printed_year": list(earliest.values()),
        },
        schema={"oracle_id": pl.Utf8, "first_printed_year": pl.Int64},
    )


def build_cards_table(
    parsed_cards: Iterable[ParsedCard],
    first_printed_years: pl.DataFrame | None = None,
    set_type_exclude: Iterable[str] = (),
) -> pl.DataFrame:
    """One row per oracle_id.

    `in_paper_only` records set-type filter membership on the card itself, so the
    numerator of a rate query and its `color_totals` denominator can never drift apart.
    """
    rows = [
        {
            "oracle_id": c.oracle_id,
            "name": c.name,
            "colors": c.colors,
            "color_identity": c.color_identity,
            "keywords": c.keywords,
            "type_line": c.type_line,
            "oracle_text": c.oracle_text,
            "cmc": c.cmc,
            "rarity": c.rarity,
            "set": c.set,
            "set_name": c.set_name,
            "set_type": c.set_type,
            "released_at": c.released_at,
            "layout": c.layout,
            "is_multiface": c.is_multiface,
            "colorless": c.colorless,
            "n_colors": len(c.colors),
            "n_keywords": len(c.keywords),
            "oracle_text_length": len(c.oracle_text),
            "is_creature": "creature" in c.type_line.lower(),
        }
        for c in parsed_cards
    ]
    df = pl.DataFrame(rows, schema=CARDS_SCHEMA).unique(subset="oracle_id", keep="first")

    if first_printed_years is not None and first_printed_years.height:
        df = df.join(first_printed_years, on="oracle_id", how="left").with_columns(
            pl.col("first_printed_year").is_null().alias("first_printed_year_is_estimate")
        )
    else:
        df = df.with_columns(pl.lit(True).alias("first_printed_year_is_estimate")).with_columns(
            pl.lit(None, dtype=pl.Int64).alias("first_printed_year")
        )

    # Fall back to this printing's own year when no earlier printing is known.
    return df.with_columns(
        pl.col("first_printed_year")
        .fill_null(pl.col("released_at").dt.year())
        .alias("first_printed_year"),
        (~pl.col("set_type").is_in(list(set_type_exclude))).alias("in_paper_only"),
    ).sort("oracle_id")


def build_card_colors_table(cards_df: pl.DataFrame) -> pl.DataFrame:
    """Long card x color table carrying both weighting schemes."""
    rows: list[dict] = []
    for oracle_id, colors in zip(
        cards_df["oracle_id"].to_list(), cards_df["colors"].to_list(), strict=True
    ):
        rows.extend(compute_color_rows(oracle_id, list(colors or [])))
    return pl.DataFrame(
        rows,
        schema={
            "oracle_id": pl.Utf8,
            "color": pl.Utf8,
            "n_colors_on_card": pl.Int64,
            "weight_fractional": pl.Float64,
            "weight_inclusive": pl.Float64,
        },
    ).sort(["oracle_id", "color"])


def build_card_keywords_table(cards_df: pl.DataFrame) -> pl.DataFrame:
    """Long card x keyword table. Cards without keywords contribute no rows."""
    return (
        cards_df.select("oracle_id", "keywords")
        .filter(pl.col("keywords").list.len() > 0)
        .explode("keywords", empty_as_null=False)
        .rename({"keywords": "keyword"})
        .sort(["oracle_id", "keyword"])
    )


def build_color_totals_table(
    cards_df: pl.DataFrame,
    card_colors_df: pl.DataFrame,
) -> pl.DataFrame:
    """Denominator table: total cards per set x color, for both weightings and both filters.

    Materialized at per-set grain. Grouping sets into coarser periods happens at query
    time, so changing the period config never requires rebuilding this table.
    """
    joined = card_colors_df.join(
        cards_df.select("oracle_id", "set", "in_paper_only"), on="oracle_id", how="inner"
    )
    variants = {
        "unfiltered": joined,
        "paper_only": joined.filter(pl.col("in_paper_only")),
    }
    frames = []
    for filter_name, df in variants.items():
        for scheme in ("fractional", "inclusive"):
            frames.append(
                df.group_by(["set", "color"])
                .agg(pl.col(f"weight_{scheme}").sum().alias("total_cards"))
                .with_columns(
                    pl.lit(scheme).alias("weighting_scheme"),
                    pl.lit(filter_name).alias("set_type_filter"),
                )
                .select("set", "color", "weighting_scheme", "set_type_filter", "total_cards")
            )
    return pl.concat(frames).sort(["set", "color", "weighting_scheme", "set_type_filter"])


def build_all_tables(
    parsed_cards: Iterable[ParsedCard],
    first_printed_years: pl.DataFrame | None,
    set_type_exclude: Iterable[str],
) -> dict[str, pl.DataFrame]:
    cards = build_cards_table(parsed_cards, first_printed_years, set_type_exclude)
    card_colors = build_card_colors_table(cards)
    card_keywords = build_card_keywords_table(cards)
    sets = build_sets_table(cards)
    color_totals = build_color_totals_table(cards, card_colors)
    return {
        "cards": cards,
        "card_colors": card_colors,
        "card_keywords": card_keywords,
        "sets": sets,
        "color_totals": color_totals,
    }


def write_tables(tables: dict[str, pl.DataFrame], processed_dir: Path) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.write_parquet(processed_dir / f"{name}.parquet")
        logger.info("wrote %s (%d rows)", name, df.height)


def _parse_stream(raw_cards: Iterator[dict]) -> Iterator[ParsedCard]:
    for raw in raw_cards:
        parsed = parse_card(raw)
        if parsed is not None:
            yield parsed


def run_pipeline(
    config: Config,
    force_refresh: bool = False,
    use_default_cards: bool = True,
) -> dict[str, pl.DataFrame]:
    """Ingest -> parse -> normalized parquet tables. Idempotent: safe to re-run."""
    client = ScryfallBulkClient(
        user_agent=config.ingest.user_agent,
        raw_dir=config.paths.raw_dir,
        cache_ttl_hours=config.ingest.cache_ttl_hours,
    )
    first_printed_years = None
    if use_default_cards:
        logger.info("computing first_printed_year from default_cards")
        first_printed_years = compute_first_printed_year(
            client.load_cards("default_cards", force_refresh=force_refresh)
        )

    logger.info("parsing oracle_cards")
    parsed = _parse_stream(client.load_cards("oracle_cards", force_refresh=force_refresh))
    tables = build_all_tables(parsed, first_printed_years, config.set_type_exclude)
    write_tables(tables, config.paths.processed_dir)
    return tables
