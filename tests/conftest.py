from __future__ import annotations

import pytest

# Trimmed-down objects shaped like real Scryfall bulk entries.


@pytest.fixture
def mono_red_creature() -> dict:
    return {
        "oracle_id": "id-mono-red",
        "name": "Goblin Sprinter",
        "colors": ["R"],
        "color_identity": ["R"],
        "keywords": ["Haste"],
        "type_line": "Creature — Goblin",
        "oracle_text": "Haste",
        "cmc": 1.0,
        "rarity": "common",
        "set": "aaa",
        "set_name": "Set AAA",
        "set_type": "expansion",
        "released_at": "2015-01-01",
        "layout": "normal",
    }


@pytest.fixture
def two_color_card() -> dict:
    return {
        "oracle_id": "id-two-color",
        "name": "Boros Blade",
        "colors": ["R", "W"],
        "color_identity": ["R", "W"],
        "keywords": ["Double Strike", "Haste"],
        "type_line": "Creature — Human Knight",
        "oracle_text": "Double strike, haste",
        "cmc": 3.0,
        "rarity": "rare",
        "set": "bbb",
        "set_name": "Set BBB",
        "set_type": "expansion",
        "released_at": "2018-06-01",
        "layout": "normal",
    }


@pytest.fixture
def colorless_artifact() -> dict:
    return {
        "oracle_id": "id-colorless",
        "name": "Iron Golem",
        "colors": [],
        "color_identity": [],
        "keywords": [],
        "type_line": "Artifact Creature — Golem",
        "oracle_text": "",
        "cmc": 4.0,
        "rarity": "uncommon",
        "set": "aaa",
        "set_name": "Set AAA",
        "set_type": "expansion",
        "released_at": "2015-01-01",
        "layout": "normal",
    }


@pytest.fixture
def transform_dfc() -> dict:
    """Top-level colors/keywords/oracle_text are null; everything lives on the faces."""
    return {
        "oracle_id": "id-transform",
        "name": "Village Elder // Moonlit Beast",
        "colors": None,
        "color_identity": ["G", "R"],
        "type_line": None,
        "cmc": 2.0,
        "rarity": "rare",
        "set": "ccc",
        "set_name": "Set CCC",
        "set_type": "expansion",
        "released_at": "2021-09-24",
        "layout": "transform",
        "card_faces": [
            {
                "name": "Village Elder",
                "colors": ["G"],
                "keywords": ["Vigilance"],
                "type_line": "Creature — Human",
                "oracle_text": "Vigilance",
            },
            {
                "name": "Moonlit Beast",
                "colors": ["R"],
                "keywords": ["Trample"],
                "type_line": "Creature — Werewolf",
                "oracle_text": "Trample",
            },
        ],
    }


@pytest.fixture
def split_card() -> dict:
    return {
        "oracle_id": "id-split",
        "name": "Fire // Ice",
        "colors": ["R", "U"],
        "color_identity": ["R", "U"],
        "keywords": [],
        "type_line": "Instant // Instant",
        "cmc": 4.0,
        "rarity": "uncommon",
        "set": "ddd",
        "set_name": "Set DDD",
        "set_type": "masters",
        "released_at": "2019-03-01",
        "layout": "split",
        "card_faces": [
            {"name": "Fire", "colors": ["R"], "oracle_text": "Fire deals 2 damage."},
            {"name": "Ice", "colors": ["U"], "oracle_text": "Tap target permanent. Draw a card."},
        ],
    }


@pytest.fixture
def adventure_card() -> dict:
    """Top-level keywords present, an extra keyword only on the adventure face."""
    return {
        "oracle_id": "id-adventure",
        "name": "Brave Knight",
        "colors": ["W"],
        "color_identity": ["W"],
        "keywords": ["Flying"],
        "type_line": "Creature — Human Knight // Sorcery — Adventure",
        "oracle_text": None,
        "cmc": 2.0,
        "rarity": "rare",
        "set": "ccc",
        "set_name": "Set CCC",
        "set_type": "expansion",
        "released_at": "2021-09-24",
        "layout": "adventure",
        "card_faces": [
            {
                "name": "Brave Knight",
                "colors": ["W"],
                "keywords": ["Flying"],
                "type_line": "Creature — Human Knight",
                "oracle_text": "Flying",
            },
            {
                "name": "Bold Charge",
                "colors": ["W"],
                "keywords": ["Lifelink"],
                "type_line": "Sorcery — Adventure",
                "oracle_text": "Target creature gains lifelink.",
            },
        ],
    }


@pytest.fixture
def no_oracle_id_card() -> dict:
    """Reversible-card style entry: oracle_id only exists on a face."""
    return {
        "name": "Reversible Thing",
        "colors": None,
        "color_identity": ["U"],
        "cmc": 1.0,
        "rarity": "rare",
        "set": "eee",
        "set_name": "Set EEE",
        "set_type": "memorabilia",
        "released_at": "2022-04-29",
        "layout": "reversible_card",
        "card_faces": [
            {
                "oracle_id": "id-reversible",
                "name": "Reversible Thing",
                "colors": ["U"],
                "keywords": ["Flying"],
                "type_line": "Creature — Bird",
                "oracle_text": "Flying",
            }
        ],
    }


@pytest.fixture
def null_release_card() -> dict:
    return {
        "oracle_id": "id-null-release",
        "name": "Undated Card",
        "colors": ["B"],
        "color_identity": ["B"],
        "keywords": ["Deathtouch"],
        "type_line": "Creature — Horror",
        "oracle_text": "Deathtouch",
        "cmc": 2.0,
        "rarity": "common",
        "set": "fff",
        "set_name": "Set FFF",
        "set_type": "funny",
        "released_at": None,
        "layout": "normal",
    }


@pytest.fixture
def sample_raw_cards(
    mono_red_creature,
    two_color_card,
    colorless_artifact,
    transform_dfc,
    split_card,
    adventure_card,
) -> list[dict]:
    return [
        mono_red_creature,
        two_color_card,
        colorless_artifact,
        transform_dfc,
        split_card,
        adventure_card,
    ]
