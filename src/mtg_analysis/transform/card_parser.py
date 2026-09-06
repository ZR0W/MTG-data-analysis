from __future__ import annotations

from dataclasses import dataclass
from datetime import date

COLOR_ORDER = ["W", "U", "B", "R", "G"]
COLORLESS = "C"


@dataclass
class ParsedCard:
    oracle_id: str
    name: str
    colors: list[str]
    color_identity: list[str]
    keywords: list[str]
    type_line: str
    oracle_text: str
    cmc: float
    rarity: str
    set: str
    set_name: str
    set_type: str
    released_at: date | None
    layout: str
    is_multiface: bool
    colorless: bool


def _faces(raw: dict) -> list[dict]:
    faces = raw.get("card_faces")
    return faces if isinstance(faces, list) else []


def _sort_colors(colors: set[str]) -> list[str]:
    return [c for c in COLOR_ORDER if c in colors] + sorted(colors - set(COLOR_ORDER))


def union_colors(raw: dict) -> list[str]:
    """Resolved colors for a card, unioning faces when the top-level field is absent.

    Keyed off the presence of `card_faces` rather than a layout allowlist, so layouts
    Scryfall adds later still resolve instead of silently coming back empty.
    """
    top = raw.get("colors")
    if top is not None:
        return _sort_colors(set(top))
    colors: set[str] = set()
    for face in _faces(raw):
        colors.update(face.get("colors") or [])
    return _sort_colors(colors)


def union_keywords(raw: dict) -> list[str]:
    """Union of top-level and per-face keywords.

    Scryfall normally unions these already at the card level; the face pass is a guard
    against gaps rather than the primary source.
    """
    keywords: set[str] = set(raw.get("keywords") or [])
    for face in _faces(raw):
        keywords.update(face.get("keywords") or [])
    return sorted(keywords)


def resolve_oracle_text(raw: dict) -> str:
    top = raw.get("oracle_text")
    if top is not None:
        return top
    parts = [face.get("oracle_text", "") for face in _faces(raw)]
    return "\n//\n".join(p for p in parts if p)


def resolve_type_line(raw: dict) -> str:
    top = raw.get("type_line")
    if top is not None:
        return top
    return " // ".join(face.get("type_line", "") for face in _faces(raw))


def _resolve_oracle_id(raw: dict) -> str | None:
    oracle_id = raw.get("oracle_id")
    if oracle_id:
        return oracle_id
    for face in _faces(raw):
        if face.get("oracle_id"):
            return face["oracle_id"]
    return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_card(raw: dict) -> ParsedCard | None:
    """Normalize one raw Scryfall card object. Returns None for objects without an oracle_id."""
    oracle_id = _resolve_oracle_id(raw)
    if oracle_id is None:
        return None
    colors = union_colors(raw)
    return ParsedCard(
        oracle_id=oracle_id,
        name=raw.get("name", ""),
        colors=colors,
        color_identity=_sort_colors(set(raw.get("color_identity") or [])),
        keywords=union_keywords(raw),
        type_line=resolve_type_line(raw),
        oracle_text=resolve_oracle_text(raw),
        # Always the top-level value: summing per-face cmc double-counts split/DFC cards.
        cmc=float(raw.get("cmc") or 0.0),
        rarity=raw.get("rarity", ""),
        set=raw.get("set", ""),
        set_name=raw.get("set_name", ""),
        set_type=raw.get("set_type", ""),
        released_at=_parse_date(raw.get("released_at")),
        layout=raw.get("layout", ""),
        is_multiface=bool(_faces(raw)),
        colorless=not colors,
    )
