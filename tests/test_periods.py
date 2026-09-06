from datetime import date

import polars as pl

from mtg_analysis.config import PeriodGroupConfig
from mtg_analysis.transform.periods import assign_period, build_sets_table


def _cards(rows):
    return pl.DataFrame(
        rows,
        schema={
            "set": pl.Utf8,
            "set_name": pl.Utf8,
            "set_type": pl.Utf8,
            "released_at": pl.Date,
        },
    )


def test_sets_are_ordered_by_release_date():
    cards = _cards(
        [
            {"set": "later", "set_name": "L", "set_type": "expansion",
             "released_at": date(2020, 1, 1)},
            {"set": "early", "set_name": "E", "set_type": "core",
             "released_at": date(1995, 5, 1)},
            {"set": "early", "set_name": "E", "set_type": "core",
             "released_at": date(1995, 8, 1)},
        ]
    )
    sets = build_sets_table(cards)
    assert sets["set"].to_list() == ["early", "later"]
    assert sets["set_order"].to_list() == [0, 1]
    # A set's date is its earliest card's release date.
    assert sets["released_at"].to_list() == [date(1995, 5, 1), date(2020, 1, 1)]
    assert sets["n_cards"].to_list() == [2, 1]


def test_same_day_releases_break_ties_by_set_code():
    cards = _cards(
        [
            {"set": "zzz", "set_name": "Z", "set_type": "expansion",
             "released_at": date(2020, 1, 1)},
            {"set": "aaa", "set_name": "A", "set_type": "expansion",
             "released_at": date(2020, 1, 1)},
        ]
    )
    assert build_sets_table(cards)["set"].to_list() == ["aaa", "zzz"]


def _sets_table(n):
    return pl.DataFrame(
        {
            "set": [f"s{i}" for i in range(n)],
            "set_name": [f"Set {i}" for i in range(n)],
            "set_type": ["expansion"] * n,
            "released_at": [date(2000 + i, 1, 1) for i in range(n)],
            "set_order": list(range(n)),
            "n_cards": [10] * n,
        }
    )


def test_per_set_mode_gives_one_period_per_set():
    out = assign_period(_sets_table(3), PeriodGroupConfig(mode="per_set"))
    assert out["period"].to_list() == ["s0", "s1", "s2"]
    assert out["period_order"].to_list() == [0, 1, 2]


def test_rolling_sets_groups_consecutive_sets():
    out = assign_period(_sets_table(5), PeriodGroupConfig(mode="rolling_sets", group_size=2))
    assert out.sort("set_order")["period"].to_list() == [
        "s0..s1",
        "s0..s1",
        "s2..s3",
        "s2..s3",
        "s4",
    ]
    assert out.sort("set_order")["period_order"].to_list() == [0, 0, 1, 1, 2]


def test_rolling_period_release_date_is_group_minimum():
    out = assign_period(_sets_table(4), PeriodGroupConfig(mode="rolling_sets", group_size=2))
    first = out.filter(pl.col("period") == "s0..s1")
    assert first["period_released_at"].unique().to_list() == [date(2000, 1, 1)]
