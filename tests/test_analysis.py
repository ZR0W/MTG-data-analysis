import matplotlib
import polars as pl
import pytest

matplotlib.use("Agg")

from mtg_analysis.analysis.color_drift import color_drift, keyword_vectors  # noqa: E402
from mtg_analysis.analysis.complexity import complexity_by_color, plot_complexity  # noqa: E402
from mtg_analysis.analysis.db import get_connection  # noqa: E402
from mtg_analysis.analysis.design_volume import design_volume, plot_design_volume  # noqa: E402
from mtg_analysis.analysis.heatmap import (  # noqa: E402
    keyword_color_matrix,
    pivot_matrix,
    plot_keyword_color_heatmap,
)
from mtg_analysis.analysis.pie_break import pie_break, plot_pie_break  # noqa: E402
from mtg_analysis.analysis.rarity_migration import rarity_migration  # noqa: E402
from mtg_analysis.analysis.timeseries import (  # noqa: E402
    keyword_timeseries,
    plot_keyword_timeseries,
)
from mtg_analysis.analysis.type_crossover import type_crossover  # noqa: E402
from mtg_analysis.config import PeriodGroupConfig  # noqa: E402
from mtg_analysis.transform.build_tables import build_all_tables, write_tables  # noqa: E402
from mtg_analysis.transform.card_parser import parse_card  # noqa: E402

EXCLUDED = ["masters", "memorabilia", "funny", "token", "alchemy"]


def _card(oracle_id, colors, keywords, set_code, released_at, **kw):
    return {
        "oracle_id": oracle_id,
        "name": oracle_id,
        "colors": colors,
        "color_identity": colors,
        "keywords": keywords,
        "type_line": kw.get("type_line", "Creature — Test"),
        "oracle_text": kw.get("oracle_text", "text"),
        "cmc": 2.0,
        "rarity": kw.get("rarity", "common"),
        "set": set_code,
        "set_name": set_code.upper(),
        "set_type": "expansion",
        "released_at": released_at,
        "layout": "normal",
    }


@pytest.fixture
def con(tmp_path):
    raw = [
        _card("r1", ["R"], ["Haste", "Trample"], "one", "2010-01-01"),
        _card("r2", ["R"], ["Haste"], "one", "2010-01-01", rarity="rare"),
        _card("w1", ["W"], ["Flying"], "one", "2010-01-01"),
        _card("rw1", ["R", "W"], ["Haste"], "one", "2010-01-01"),
        _card("r3", ["R"], ["Trample"], "two", "2015-01-01", rarity="mythic"),
        _card("w2", ["W"], ["Haste"], "two", "2015-01-01", type_line="Instant"),
        _card("u1", ["U"], ["Flying"], "two", "2015-01-01"),
        _card("c1", [], [], "two", "2015-01-01", type_line="Artifact"),
    ]
    parsed = [c for c in (parse_card(r) for r in raw) if c is not None]
    write_tables(build_all_tables(parsed, None, EXCLUDED), tmp_path)
    return get_connection(tmp_path, PeriodGroupConfig(mode="per_set"))


def test_keyword_color_matrix_shares_sum_to_one(con):
    matrix = keyword_color_matrix(con)
    per_keyword = matrix.group_by("keyword").agg(pl.col("share").sum())
    assert per_keyword["share"].to_list() == pytest.approx([1.0] * per_keyword.height)


def test_keyword_color_matrix_respects_explicit_keywords(con):
    matrix = keyword_color_matrix(con, keywords=["Haste"])
    assert set(matrix["keyword"]) == {"Haste"}
    # Haste weights: R = 1.0 + 1.0 + 0.5 = 2.5, W = 0.5 + 1.0 = 1.5, total 4.0
    red = matrix.filter(pl.col("color") == "R")["share"].item()
    assert red == pytest.approx(2.5 / 4.0)
    assert matrix["share"].sum() == pytest.approx(1.0)


def test_pivot_matrix_orders_columns_wubrg(con):
    wide = pivot_matrix(keyword_color_matrix(con))
    assert wide.columns == ["keyword", "W", "U", "R"]


def test_keyword_timeseries_covers_every_requested_color(con):
    df = keyword_timeseries(con, "Haste", colors=["R", "W"])
    assert set(df["color"]) == {"R", "W"}
    assert set(df["period"]) == {"one", "two"}
    assert set(df["weighting"]) == {"fractional"}


def test_color_drift_similarity_bounds(con):
    drift = color_drift(con, min_keyword_weight=0.5)
    values = [v for v in drift["cosine_vs_baseline"].to_list() if v is not None]
    assert values and all(0.0 <= v <= 1.0 + 1e-9 for v in values)
    # first period of each colour has no predecessor
    first = drift.sort(["color", "period_order"]).group_by("color").first()
    assert first["cosine_vs_previous"].to_list() == [None] * first.height


def test_keyword_vectors_normalize_within_period_and_color(con):
    vectors = keyword_vectors(con)
    sums = vectors.group_by(["period", "color"]).agg(pl.col("freq").sum())
    assert sums["freq"].to_list() == pytest.approx([1.0] * sums.height)


def test_pie_break_identifies_dominant_color(con):
    df = pie_break(con, "Haste", min_period_weight=0.5)
    assert df["original_dominant_color"].unique().to_list() == ["R"]
    # In set two only white prints Haste, so challengers hold the whole pie.
    two = df.filter(pl.col("period") == "two")
    assert two["challenger_share"].unique().to_list() == pytest.approx([1.0])


def test_rarity_migration_is_ordinal_mean(con):
    df = rarity_migration(con, "Trample").sort("period_order")
    # set one: r1 common (0); set two: r3 mythic (3)
    assert df["mean_rarity"].to_list() == pytest.approx([0.0, 3.0])


def test_type_crossover_shares_sum_to_one_per_period(con):
    df = type_crossover(con, "Haste")
    sums = df.group_by("period").agg(pl.col("share").sum())
    assert sums["share"].to_list() == pytest.approx([1.0] * sums.height)
    assert "Instant/Sorcery" in df["card_type"].to_list()


def test_complexity_metrics_are_weighted_means(con):
    df = complexity_by_color(con)
    assert set(df.columns) >= {"mean_text_length", "mean_keywords", "color_total"}
    red_one = df.filter((pl.col("period") == "one") & (pl.col("color") == "R"))
    # r1 (2 keywords) + r2 (1) + rw1 (1 at half weight) over a total weight of 2.5
    assert red_one["mean_keywords"].item() == pytest.approx((2 + 1 + 0.5) / 2.5)


def test_design_volume_matches_color_totals(con):
    df = design_volume(con)
    assert df["total_cards"].sum() == pytest.approx(8.0)
    assert set(df["color"]) == {"W", "U", "R", "C"}


def test_plot_helpers_run(con):
    plot_keyword_color_heatmap(keyword_color_matrix(con))
    plot_keyword_timeseries(keyword_timeseries(con, "Haste", colors=["R", "W"]))
    plot_pie_break(pie_break(con, "Haste", min_period_weight=0.5))
    plot_complexity(complexity_by_color(con))
    plot_design_volume(design_volume(con))
