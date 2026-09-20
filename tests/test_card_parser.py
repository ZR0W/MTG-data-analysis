from datetime import date

from mtg_analysis.transform.card_parser import (
    parse_card,
    resolve_oracle_text,
    union_colors,
    union_keywords,
)


def test_mono_color_card(mono_red_creature):
    card = parse_card(mono_red_creature)
    assert card.colors == ["R"]
    assert card.keywords == ["Haste"]
    assert card.is_multiface is False
    assert card.colorless is False
    assert card.released_at == date(2015, 1, 1)


def test_colors_are_sorted_in_wubrg_order(two_color_card):
    assert union_colors(two_color_card) == ["W", "R"]


def test_colorless_card_flagged(colorless_artifact):
    card = parse_card(colorless_artifact)
    assert card.colors == []
    assert card.colorless is True


def test_transform_card_unions_faces(transform_dfc):
    card = parse_card(transform_dfc)
    assert card.colors == ["R", "G"]
    assert card.keywords == ["Trample", "Vigilance"]
    assert card.is_multiface is True
    assert card.type_line == "Creature — Human // Creature — Werewolf"
    assert "Vigilance" in card.oracle_text and "Trample" in card.oracle_text
    # cmc always comes from the top level, never summed across faces
    assert card.cmc == 2.0


def test_split_card_keeps_top_level_colors(split_card):
    card = parse_card(split_card)
    assert card.colors == ["U", "R"]
    assert card.keywords == []
    assert card.is_multiface is True


def test_adventure_card_unions_face_keywords(adventure_card):
    assert union_keywords(adventure_card) == ["Flying", "Lifelink"]
    card = parse_card(adventure_card)
    assert card.colors == ["W"]


def test_face_only_oracle_id_is_recovered(no_oracle_id_card):
    card = parse_card(no_oracle_id_card)
    assert card is not None
    assert card.oracle_id == "id-reversible"
    assert card.colors == ["U"]


def test_card_without_any_oracle_id_is_dropped():
    assert parse_card({"name": "Token", "layout": "token"}) is None


def test_null_release_date_parses_to_none(null_release_card):
    card = parse_card(null_release_card)
    assert card.released_at is None


def test_resolve_oracle_text_joins_faces(transform_dfc):
    assert resolve_oracle_text(transform_dfc) == "Vigilance\n//\nTrample"
