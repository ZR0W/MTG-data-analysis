from __future__ import annotations

from mtg_analysis.transform.card_parser import COLORLESS


def compute_color_rows(oracle_id: str, colors: list[str]) -> list[dict]:
    """Long-format color attribution rows for one card.

    Both weighting schemes are always emitted so no analysis silently collapses
    multicolor attribution to one of them:
      weight_fractional -- 1/n per color, so shares sum to 100% across the pie
      weight_inclusive  -- 1.0 per color, so "any card touching red" counts fully
    Colorless cards get a single 'C' row with both weights at 1.0. The fractional
    weights of a card always sum to exactly 1.0.
    """
    if not colors:
        return [
            {
                "oracle_id": oracle_id,
                "color": COLORLESS,
                "n_colors_on_card": 0,
                "weight_fractional": 1.0,
                "weight_inclusive": 1.0,
            }
        ]
    n = len(colors)
    return [
        {
            "oracle_id": oracle_id,
            "color": color,
            "n_colors_on_card": n,
            "weight_fractional": 1.0 / n,
            "weight_inclusive": 1.0,
        }
        for color in colors
    ]
