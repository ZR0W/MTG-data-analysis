from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import polars as pl
import typer

from mtg_analysis.config import DEFAULT_CONFIG_PATH, load_config
from mtg_analysis.ingest.bulk_client import ScryfallBulkClient
from mtg_analysis.transform.build_tables import run_pipeline

app = typer.Typer(help="Build and validate the local MTG keyword/color dataset.")

ConfigOpt = Annotated[Path, typer.Option("--config", help="Path to config.yaml")]


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


@app.command()
def fetch(
    config: ConfigOpt = DEFAULT_CONFIG_PATH,
    bulk_type: Annotated[
        str, typer.Option("--type", help="oracle_cards, default_cards, or all")
    ] = "all",
    force: Annotated[bool, typer.Option("--force", help="Ignore the cache TTL")] = False,
    verbose: bool = False,
) -> None:
    """Download Scryfall bulk data into the local cache (at most once per TTL window)."""
    _setup_logging(verbose)
    cfg = load_config(config)
    client = ScryfallBulkClient(
        user_agent=cfg.ingest.user_agent,
        raw_dir=cfg.paths.raw_dir,
        cache_ttl_hours=cfg.ingest.cache_ttl_hours,
    )
    types = cfg.ingest.bulk_types if bulk_type == "all" else [bulk_type]
    for t in types:
        path = client.fetch(t, force=force)
        typer.echo(f"{t}: {path} ({path.stat().st_size / 1e6:.1f} MB)")


@app.command()
def build(
    config: ConfigOpt = DEFAULT_CONFIG_PATH,
    force_refresh: Annotated[
        bool, typer.Option("--force-refresh", help="Re-download bulk data before building")
    ] = False,
    skip_default_cards: Annotated[
        bool,
        typer.Option(
            "--skip-default-cards",
            help="Skip first_printed_year (falls back to the oracle printing's own year)",
        ),
    ] = False,
    verbose: bool = False,
) -> None:
    """Parse the cached bulk data into the normalized parquet tables."""
    _setup_logging(verbose)
    cfg = load_config(config)
    tables = run_pipeline(
        cfg, force_refresh=force_refresh, use_default_cards=not skip_default_cards
    )
    for name, df in tables.items():
        typer.echo(f"{name}: {df.height} rows -> {cfg.paths.processed_dir / (name + '.parquet')}")


@app.command()
def validate(config: ConfigOpt = DEFAULT_CONFIG_PATH, verbose: bool = False) -> None:
    """Data-quality checks over the built tables."""
    _setup_logging(verbose)
    cfg = load_config(config)
    d = cfg.paths.processed_dir
    cards = pl.read_parquet(d / "cards.parquet")
    card_colors = pl.read_parquet(d / "card_colors.parquet")
    card_keywords = pl.read_parquet(d / "card_keywords.parquet")
    color_totals = pl.read_parquet(d / "color_totals.parquet")

    failures: list[str] = []

    if cards["oracle_id"].n_unique() != cards.height:
        failures.append("duplicate oracle_id in cards")

    valid_colors = {"W", "U", "B", "R", "G", "C"}
    bad_colors = set(card_colors["color"].unique().to_list()) - valid_colors
    if bad_colors:
        failures.append(f"unexpected colors in card_colors: {sorted(bad_colors)}")

    weight_sums = card_colors.group_by("oracle_id").agg(pl.col("weight_fractional").sum())
    off = weight_sums.filter((pl.col("weight_fractional") - 1.0).abs() > 1e-9)
    if off.height:
        failures.append(f"{off.height} cards whose fractional weights do not sum to 1.0")

    orphan_keywords = card_keywords.join(cards.select("oracle_id"), on="oracle_id", how="anti")
    if orphan_keywords.height:
        failures.append(f"{orphan_keywords.height} card_keywords rows with no matching card")

    orphan_colors = card_colors.join(cards.select("oracle_id"), on="oracle_id", how="anti")
    if orphan_colors.height:
        failures.append(f"{orphan_colors.height} card_colors rows with no matching card")

    expected_variants = {"fractional", "inclusive"}
    if set(color_totals["weighting_scheme"].unique().to_list()) != expected_variants:
        failures.append("color_totals is missing a weighting scheme")
    if set(color_totals["set_type_filter"].unique().to_list()) != {"paper_only", "unfiltered"}:
        failures.append("color_totals is missing a set_type filter variant")

    if failures:
        for f in failures:
            typer.echo(f"FAIL: {f}")
        raise typer.Exit(code=1)

    typer.echo(
        f"OK: {cards.height} cards, {card_keywords.height} keyword rows, "
        f"{card_colors.height} color rows, {color_totals.height} denominator rows"
    )


if __name__ == "__main__":
    app()
