import math

import polars as pl
import pytest

from mtg_analysis.analysis.db import get_connection
from mtg_analysis.config import PeriodGroupConfig
from mtg_analysis.metrics.core import (
    color_share,
    penetration_rate,
    raw_count,
    trend_report,
)
from mtg_analysis.transform.build_tables import build_all_tables, write_tables
from mtg_analysis.transform.card_parser import parse_card

EXCLUDED = ["masters", "memorabilia", "funny", "token", "alchemy"]


def _card(oracle_id, colors, keywords, set_code, released_at, set_type="expansion", **kw):
    return {
        "oracle_id": oracle_id,
        "name": oracle_id,
        "colors": colors,
        "color_identity": colors,
        "keywords": keywords,
        "type_line": kw.get("type_line", "Creature — Test"),
        "oracle_text": kw.get("oracle_text", ""),
        "cmc": kw.get("cmc", 2.0),
        "rarity": kw.get("rarity", "common"),
        "set": set_code,
        "set_name": set_code.upper(),
        "set_type": set_type,
        "released_at": released_at,
        "layout": "normal",
    }


def _connection(raw_cards, tmp_path, mode="per_set"):
    parsed = [c for c in (parse_card(r) for r in raw_cards) if c is not None]
    tables = build_all_tables(parsed, None, EXCLUDED)
    write_tables(tables, tmp_path)
    return get_connection(tmp_path, PeriodGroupConfig(mode=mode))


@pytest.fixture
def con(tmp_path):
    """Hand-built dataset with arithmetic simple enough to verify by inspection.

    Set 'one' (2010): 4 cards, two of them carrying Double Strike.
    Set 'two' (2015): 4 cards, one carrying Double Strike.
    """
    raw = [
        # set one
        _card("r1", ["R"], ["Double Strike"], "one", "2010-01-01"),
        _card("rw1", ["R", "W"], ["Double Strike"], "one", "2010-01-01"),
        _card("r2", ["R"], [], "one", "2010-01-01"),
        _card("w1", ["W"], [], "one", "2010-01-01"),
        # set two
        _card("w2", ["W"], ["Double Strike"], "two", "2015-01-01"),
        _card("r3", ["R"], [], "two", "2015-01-01"),
        _card("r4", ["R"], [], "two", "2015-01-01"),
        _card("c1", [], [], "two", "2015-01-01"),
        # excluded reprint set: must not affect paper_only numbers at all
        _card("r5", ["R"], ["Double Strike"], "mst", "2016-01-01", set_type="masters"),
    ]
    return _connection(raw, tmp_path)


def test_raw_count_is_a_headcount(con):
    assert raw_count(con, "Double Strike", "R", "one") == 2
    assert raw_count(con, "Double Strike", "W", "one") == 1
    assert raw_count(con, "Double Strike", "R", "two") == 0


def test_raw_count_across_all_periods(con):
    assert raw_count(con, "Double Strike", "R") == 2


def test_excluded_set_types_are_invisible_to_paper_only(con):
    assert raw_count(con, "Double Strike", "R", "mst") == 0
    assert raw_count(con, "Double Strike", "R", "mst", set_type_filter="unfiltered") == 1


def test_color_share_fractional(con):
    # Set one Double Strike: R gets 1 + 0.5 = 1.5, W gets 0.5, total 2.0
    assert color_share(con, "Double Strike", "R", "one") == pytest.approx(0.75)
    assert color_share(con, "Double Strike", "W", "one") == pytest.approx(0.25)


def test_color_share_inclusive_differs_from_fractional(con):
    # Inclusive: R touches 2 of the 3 color-appearances, W touches 1
    assert color_share(con, "Double Strike", "R", "one", weighting="inclusive") == pytest.approx(
        2 / 3
    )


def test_fractional_shares_sum_to_one_across_colors(con):
    total = sum(
        color_share(con, "Double Strike", c, "one")
        for c in ("W", "U", "B", "R", "G", "C")
        if not math.isnan(color_share(con, "Double Strike", c, "one"))
    )
    assert total == pytest.approx(1.0)


def test_color_share_is_nan_when_keyword_absent(con):
    assert math.isnan(color_share(con, "Flying", "R", "one"))


def test_penetration_rate_uses_color_totals_denominator(con):
    # Set one red totals (fractional): r1 1.0 + rw1 0.5 + r2 1.0 = 2.5
    # Red Double Strike weight: 1.0 + 0.5 = 1.5  ->  0.6
    assert penetration_rate(con, "Double Strike", "R", "one") == pytest.approx(1.5 / 2.5)
    # Inclusive: red touches 3 cards, 2 of which have the keyword
    assert penetration_rate(
        con, "Double Strike", "R", "one", weighting="inclusive"
    ) == pytest.approx(2 / 3)


def test_penetration_rate_is_zero_when_color_printed_but_keyword_absent(con):
    assert penetration_rate(con, "Double Strike", "R", "two") == pytest.approx(0.0)


def test_penetration_rate_is_nan_when_color_absent_from_period(con):
    assert math.isnan(penetration_rate(con, "Double Strike", "G", "one"))


def test_share_and_penetration_can_diverge(tmp_path):
    """The failure mode the project is built to avoid: share up, penetration down.

    Red's share of the keyword rises from 25% to 100% while the share of red cards
    carrying it halves, because every color printed less of the keyword.
    """
    raw = []
    for i in range(10):
        raw.append(_card(f"r_a{i}", ["R"], ["Double Strike"] if i < 2 else [], "one", "2010-01-01"))
        raw.append(_card(f"w_a{i}", ["W"], ["Double Strike"] if i < 6 else [], "one", "2010-01-01"))
        raw.append(_card(f"r_b{i}", ["R"], ["Double Strike"] if i < 1 else [], "two", "2015-01-01"))
        raw.append(_card(f"w_b{i}", ["W"], [], "two", "2015-01-01"))
    con = _connection(raw, tmp_path)

    report = trend_report(con, "Double Strike", "R", ["one", "two"]).sort("period_order")
    shares = report["color_share"].to_list()
    penetrations = report["penetration_rate"].to_list()

    assert shares == pytest.approx([0.25, 1.0])
    assert penetrations == pytest.approx([0.2, 0.1])
    assert report["raw_count"].to_list() == [2, 1]


def test_trend_report_labels_its_weighting_and_filter(con):
    report = trend_report(con, "Double Strike", "R")
    assert set(report["weighting"]) == {"fractional"}
    assert set(report["set_type_filter"]) == {"paper_only"}
    assert set(report.columns) >= {
        "period",
        "raw_count",
        "color_share",
        "penetration_rate",
        "color_total",
    }


def test_trend_report_covers_periods_where_the_keyword_is_absent(con):
    report = trend_report(con, "Double Strike", "R").sort("period_order")
    assert report["period"].to_list() == ["one", "two"]
    assert report["raw_count"].to_list() == [2, 0]
    assert report["penetration_rate"].to_list()[1] == pytest.approx(0.0)


def test_grouped_periods_merge_sets(con):
    from mtg_analysis.analysis.db import set_period_config

    set_period_config(con, PeriodGroupConfig(mode="rolling_sets", group_size=5))
    report = trend_report(con, "Double Strike", "R")
    assert report.height == 1
    assert report["raw_count"].item() == 2


def test_invalid_weighting_rejected(con):
    with pytest.raises(ValueError):
        color_share(con, "Double Strike", "R", "one", weighting="bogus")


def test_period_color_totals_match_raw_table(con):
    per_set = con.execute(
        """
        SELECT SUM(total_cards) FROM color_totals
        WHERE weighting_scheme = 'fractional' AND set_type_filter = 'paper_only'
        """
    ).fetchone()[0]
    per_period = con.execute(
        """
        SELECT SUM(total_cards) FROM period_color_totals
        WHERE weighting_scheme = 'fractional' AND set_type_filter = 'paper_only'
        """
    ).fetchone()[0]
    assert per_set == pytest.approx(per_period)
    # 8 paper cards, each contributing exactly 1.0 of fractional weight
    assert per_period == pytest.approx(8.0)


def test_card_facts_view_does_not_duplicate_cards(con):
    counts = con.execute(
        "SELECT oracle_id, COUNT(*) AS n FROM card_facts GROUP BY oracle_id"
    ).pl()
    expected = con.execute("SELECT oracle_id, n_colors FROM cards").pl().with_columns(
        pl.when(pl.col("n_colors") == 0).then(1).otherwise(pl.col("n_colors")).alias("n")
    )
    joined = counts.join(expected.select("oracle_id", "n"), on="oracle_id", suffix="_expected")
    assert joined["n"].to_list() == joined["n_expected"].to_list()
