import polars as pl
import pytest

from mtg_analysis.transform.build_tables import (
    build_all_tables,
    build_cards_table,
    compute_first_printed_year,
)
from mtg_analysis.transform.card_parser import parse_card

EXCLUDED = ["masters", "memorabilia", "funny", "token", "alchemy"]


@pytest.fixture
def tables(sample_raw_cards):
    parsed = [c for c in (parse_card(r) for r in sample_raw_cards) if c is not None]
    return build_all_tables(parsed, None, EXCLUDED)


def test_cards_table_is_one_row_per_oracle_id(tables, sample_raw_cards):
    cards = tables["cards"]
    assert cards.height == len(sample_raw_cards)
    assert cards["oracle_id"].n_unique() == cards.height


def test_set_type_membership_recorded_on_card(tables):
    cards = tables["cards"]
    split = cards.filter(pl.col("oracle_id") == "id-split")
    assert split["set_type"].item() == "masters"
    assert split["in_paper_only"].item() is False
    assert cards.filter(pl.col("oracle_id") == "id-mono-red")["in_paper_only"].item() is True


def test_card_colors_rows_match_resolved_colors(tables):
    colors = tables["card_colors"]
    two_color = colors.filter(pl.col("oracle_id") == "id-two-color")
    assert sorted(two_color["color"].to_list()) == ["R", "W"]
    assert two_color["weight_fractional"].sum() == pytest.approx(1.0)
    colorless = colors.filter(pl.col("oracle_id") == "id-colorless")
    assert colorless["color"].to_list() == ["C"]


def test_fractional_weights_sum_to_one_for_every_card(tables):
    sums = tables["card_colors"].group_by("oracle_id").agg(pl.col("weight_fractional").sum())
    assert sums["weight_fractional"].to_list() == pytest.approx([1.0] * sums.height)


def test_card_keywords_is_long_and_excludes_keywordless_cards(tables):
    kw = tables["card_keywords"]
    assert set(kw.filter(pl.col("oracle_id") == "id-two-color")["keyword"]) == {
        "Double Strike",
        "Haste",
    }
    assert kw.filter(pl.col("oracle_id") == "id-colorless").height == 0
    # unioned across the adventure card's two faces
    assert set(kw.filter(pl.col("oracle_id") == "id-adventure")["keyword"]) == {
        "Flying",
        "Lifelink",
    }


def test_referential_integrity(tables):
    cards = tables["cards"].select("oracle_id")
    for name in ("card_colors", "card_keywords"):
        assert tables[name].join(cards, on="oracle_id", how="anti").height == 0
    assert tables["color_totals"].join(tables["sets"], on="set", how="anti").height == 0


def test_color_totals_has_both_weightings_and_both_filters(tables):
    totals = tables["color_totals"]
    assert set(totals["weighting_scheme"]) == {"fractional", "inclusive"}
    assert set(totals["set_type_filter"]) == {"paper_only", "unfiltered"}

    # Set BBB has exactly one card, red/white, so fractional totals are 0.5 per color
    # while inclusive totals are 1.0 per color.
    bbb = totals.filter((pl.col("set") == "bbb") & (pl.col("set_type_filter") == "paper_only"))
    frac = bbb.filter(pl.col("weighting_scheme") == "fractional")["total_cards"].to_list()
    incl = bbb.filter(pl.col("weighting_scheme") == "inclusive")["total_cards"].to_list()
    assert frac == pytest.approx([0.5, 0.5])
    assert incl == pytest.approx([1.0, 1.0])


def test_paper_only_totals_exclude_filtered_set_types(tables):
    totals = tables["color_totals"]
    ddd_paper = totals.filter(
        (pl.col("set") == "ddd") & (pl.col("set_type_filter") == "paper_only")
    )
    ddd_all = totals.filter(
        (pl.col("set") == "ddd") & (pl.col("set_type_filter") == "unfiltered")
    )
    assert ddd_paper.height == 0  # 'ddd' is a masters set
    assert ddd_all.height > 0


def test_first_printed_year_is_earliest_printing():
    printings = [
        {"oracle_id": "a", "released_at": "2005-01-01"},
        {"oracle_id": "a", "released_at": "1999-08-01"},
        {"oracle_id": "b", "released_at": "2012-01-01"},
        {"oracle_id": "c", "released_at": None},
    ]
    out = compute_first_printed_year(printings).sort("oracle_id")
    assert out["oracle_id"].to_list() == ["a", "b"]
    assert out["first_printed_year"].to_list() == [1999, 2012]


def test_first_printed_year_joins_into_cards(sample_raw_cards):
    parsed = [c for c in (parse_card(r) for r in sample_raw_cards) if c is not None]
    first = pl.DataFrame(
        {"oracle_id": ["id-two-color"], "first_printed_year": [2001]},
        schema={"oracle_id": pl.Utf8, "first_printed_year": pl.Int64},
    )
    cards = build_cards_table(parsed, first, EXCLUDED)
    row = cards.filter(pl.col("oracle_id") == "id-two-color")
    assert row["first_printed_year"].item() == 2001
    assert row["first_printed_year_is_estimate"].item() is False
    # Cards with no earlier printing fall back to their own release year.
    fallback = cards.filter(pl.col("oracle_id") == "id-mono-red")
    assert fallback["first_printed_year"].item() == 2015
    assert fallback["first_printed_year_is_estimate"].item() is True
