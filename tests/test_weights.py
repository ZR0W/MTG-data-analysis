import pytest

from mtg_analysis.transform.weights import compute_color_rows


def test_mono_color_card_gets_full_weight():
    rows = compute_color_rows("x", ["R"])
    assert rows == [
        {
            "oracle_id": "x",
            "color": "R",
            "n_colors_on_card": 1,
            "weight_fractional": 1.0,
            "weight_inclusive": 1.0,
        }
    ]


def test_two_color_card_splits_fractional_weight():
    rows = compute_color_rows("x", ["W", "R"])
    assert [r["color"] for r in rows] == ["W", "R"]
    assert all(r["weight_fractional"] == 0.5 for r in rows)
    assert all(r["weight_inclusive"] == 1.0 for r in rows)
    assert all(r["n_colors_on_card"] == 2 for r in rows)


def test_colorless_card_gets_single_c_row():
    rows = compute_color_rows("x", [])
    assert len(rows) == 1
    assert rows[0]["color"] == "C"
    assert rows[0]["n_colors_on_card"] == 0
    assert rows[0]["weight_fractional"] == 1.0
    assert rows[0]["weight_inclusive"] == 1.0


@pytest.mark.parametrize(
    "colors",
    [[], ["R"], ["W", "U"], ["W", "U", "B"], ["W", "U", "B", "R", "G"]],
)
def test_fractional_weights_always_sum_to_one(colors):
    rows = compute_color_rows("x", colors)
    assert sum(r["weight_fractional"] for r in rows) == pytest.approx(1.0)


def test_inclusive_weights_sum_to_color_count():
    rows = compute_color_rows("x", ["W", "U", "B"])
    assert sum(r["weight_inclusive"] for r in rows) == 3.0
