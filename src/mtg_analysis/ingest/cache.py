from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

MANIFEST_NAME = "manifest.json"


@dataclass
class CacheManifestEntry:
    bulk_type: str
    source_url: str
    downloaded_at: datetime
    scryfall_updated_at: datetime
    local_path: Path
    content_hash: str

    def to_json(self) -> dict:
        d = asdict(self)
        d["downloaded_at"] = self.downloaded_at.isoformat()
        d["scryfall_updated_at"] = self.scryfall_updated_at.isoformat()
        d["local_path"] = str(self.local_path)
        return d

    @classmethod
    def from_json(cls, d: dict) -> CacheManifestEntry:
        return cls(
            bulk_type=d["bulk_type"],
            source_url=d["source_url"],
            downloaded_at=datetime.fromisoformat(d["downloaded_at"]),
            scryfall_updated_at=datetime.fromisoformat(d["scryfall_updated_at"]),
            local_path=Path(d["local_path"]),
            content_hash=d["content_hash"],
        )


def manifest_path(raw_dir: Path) -> Path:
    return raw_dir / MANIFEST_NAME


def load_manifest(raw_dir: Path) -> dict[str, CacheManifestEntry]:
    path = manifest_path(raw_dir)
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {k: CacheManifestEntry.from_json(v) for k, v in raw.items()}


def save_manifest(raw_dir: Path, manifest: dict[str, CacheManifestEntry]) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    payload = {k: v.to_json() for k, v in manifest.items()}
    manifest_path(raw_dir).write_text(json.dumps(payload, indent=2, sort_keys=True))


def is_cache_fresh(
    entry: CacheManifestEntry | None,
    ttl_hours: int,
    now: datetime | None = None,
) -> bool:
    """True when the cached file exists and is younger than the TTL.

    A fresh cache means zero network calls: the TTL gate is evaluated purely against
    local state, which is what keeps us inside Scryfall's once-per-day guidance.
    """
    if entry is None or not entry.local_path.exists():
        return False
    now = now or datetime.now(UTC)
    downloaded_at = entry.downloaded_at
    if downloaded_at.tzinfo is None:
        downloaded_at = downloaded_at.replace(tzinfo=UTC)
    return now - downloaded_at < timedelta(hours=ttl_hours)
