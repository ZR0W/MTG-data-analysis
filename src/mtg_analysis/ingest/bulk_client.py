from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import ijson
import requests

from mtg_analysis.ingest.cache import (
    CacheManifestEntry,
    is_cache_fresh,
    load_manifest,
    save_manifest,
)

BULK_DATA_URL = "https://api.scryfall.com/bulk-data"

logger = logging.getLogger(__name__)


class ScryfallBulkClient:
    """Downloads and caches Scryfall bulk data files.

    Only the bulk-data endpoint is used — never the paginated /cards/search API.
    """

    def __init__(
        self,
        user_agent: str,
        raw_dir: Path,
        cache_ttl_hours: int = 24,
        session: requests.Session | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.raw_dir = Path(raw_dir)
        self.cache_ttl_hours = cache_ttl_hours
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})

    def list_bulk_data(self) -> list[dict]:
        resp = self.session.get(BULK_DATA_URL, timeout=60)
        resp.raise_for_status()
        return resp.json()["data"]

    def fetch(self, bulk_type: str, force: bool = False) -> Path:
        """Return a local path to the bulk file, downloading only when the cache is stale."""
        manifest = load_manifest(self.raw_dir)
        entry = manifest.get(bulk_type)
        if not force and is_cache_fresh(entry, self.cache_ttl_hours):
            logger.info("cache hit for %s (%s)", bulk_type, entry.local_path)
            return entry.local_path

        remote = self._find_bulk_entry(bulk_type)
        scryfall_updated_at = datetime.fromisoformat(remote["updated_at"])
        target = self.raw_dir / f"{bulk_type}.json"

        if (
            not force
            and entry is not None
            and entry.local_path.exists()
            and entry.scryfall_updated_at >= scryfall_updated_at
        ):
            # Remote has not changed since our copy; refresh the TTL clock without re-downloading.
            logger.info("%s unchanged upstream, keeping cached copy", bulk_type)
            entry.downloaded_at = datetime.now(UTC)
            manifest[bulk_type] = entry
            save_manifest(self.raw_dir, manifest)
            return entry.local_path

        content_hash = self._download(remote["download_uri"], target)
        manifest[bulk_type] = CacheManifestEntry(
            bulk_type=bulk_type,
            source_url=remote["download_uri"],
            downloaded_at=datetime.now(UTC),
            scryfall_updated_at=scryfall_updated_at,
            local_path=target,
            content_hash=content_hash,
        )
        save_manifest(self.raw_dir, manifest)
        return target

    def load_cards(self, bulk_type: str, force_refresh: bool = False) -> Iterator[dict]:
        """Stream card objects out of the cached bulk file.

        default_cards is hundreds of MB, so the array is parsed incrementally rather
        than loaded whole.
        """
        path = self.fetch(bulk_type, force=force_refresh)
        with path.open("rb") as fh:
            yield from ijson.items(fh, "item")

    def _find_bulk_entry(self, bulk_type: str) -> dict:
        for item in self.list_bulk_data():
            if item["type"] == bulk_type:
                return item
        raise ValueError(f"Scryfall has no bulk data of type {bulk_type!r}")

    def _download(self, url: str, target: Path) -> str:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        digest = hashlib.sha256()
        with self.session.get(url, stream=True, timeout=600) as resp:
            resp.raise_for_status()
            with tmp.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    digest.update(chunk)
                    fh.write(chunk)
        tmp.replace(target)
        return digest.hexdigest()
