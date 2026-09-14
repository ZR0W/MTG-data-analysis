import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import responses

from mtg_analysis.ingest.bulk_client import BULK_DATA_URL, ScryfallBulkClient
from mtg_analysis.ingest.cache import (
    CacheManifestEntry,
    is_cache_fresh,
    load_manifest,
    save_manifest,
)

DOWNLOAD_URL = "https://data.scryfall.io/oracle-cards/test.jsonl.gz"


def _jsonl_gz(rows: list[dict]) -> bytes:
    return gzip.compress("\n".join(json.dumps(r) for r in rows).encode("utf-8"))


def _entry(path: Path, downloaded_at: datetime, updated_at: datetime | None = None):
    return CacheManifestEntry(
        bulk_type="oracle_cards",
        source_url=DOWNLOAD_URL,
        downloaded_at=downloaded_at,
        scryfall_updated_at=updated_at or downloaded_at,
        local_path=path,
        content_hash="abc",
    )


def test_manifest_round_trip(tmp_path):
    path = tmp_path / "oracle_cards.jsonl.gz"
    path.write_bytes(_jsonl_gz([]))
    entry = _entry(path, datetime(2026, 1, 1, tzinfo=UTC))
    save_manifest(tmp_path, {"oracle_cards": entry})
    loaded = load_manifest(tmp_path)["oracle_cards"]
    assert loaded == entry


def test_missing_manifest_is_empty(tmp_path):
    assert load_manifest(tmp_path) == {}


def test_cache_is_stale_without_entry():
    assert is_cache_fresh(None, 24) is False


def test_cache_is_stale_when_file_is_gone(tmp_path):
    entry = _entry(tmp_path / "gone.jsonl.gz", datetime.now(UTC))
    assert is_cache_fresh(entry, 24) is False


@pytest.mark.parametrize(
    ("age_hours", "expected"),
    [(1, True), (23, True), (25, False)],
)
def test_ttl_boundary(tmp_path, age_hours, expected):
    path = tmp_path / "oracle_cards.jsonl.gz"
    path.write_bytes(_jsonl_gz([]))
    now = datetime.now(UTC)
    entry = _entry(path, now - timedelta(hours=age_hours))
    assert is_cache_fresh(entry, 24, now=now) is expected


@responses.activate
def test_fetch_downloads_and_records_manifest(tmp_path):
    responses.add(
        responses.GET,
        BULK_DATA_URL,
        json={
            "data": [
                {
                    "type": "oracle_cards",
                    "jsonl_download_uri": DOWNLOAD_URL,
                    "updated_at": "2026-09-06T09:00:00+00:00",
                }
            ]
        },
    )
    responses.add(responses.GET, DOWNLOAD_URL, body=_jsonl_gz([{"oracle_id": "x"}]))

    client = ScryfallBulkClient("test-agent/1.0", tmp_path)
    path = client.fetch("oracle_cards")

    assert path.exists()
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        assert [json.loads(line) for line in fh] == [{"oracle_id": "x"}]
    entry = load_manifest(tmp_path)["oracle_cards"]
    assert entry.source_url == DOWNLOAD_URL
    assert responses.calls[0].request.headers["User-Agent"] == "test-agent/1.0"


@responses.activate
def test_fresh_cache_makes_no_network_calls(tmp_path):
    path = tmp_path / "oracle_cards.jsonl.gz"
    path.write_bytes(_jsonl_gz([]))
    save_manifest(tmp_path, {"oracle_cards": _entry(path, datetime.now(UTC))})

    client = ScryfallBulkClient("test-agent/1.0", tmp_path)
    assert client.fetch("oracle_cards") == path
    assert len(responses.calls) == 0


@responses.activate
def test_stale_cache_skips_download_when_upstream_is_unchanged(tmp_path):
    path = tmp_path / "oracle_cards.jsonl.gz"
    path.write_bytes(_jsonl_gz([]))
    updated_at = datetime(2026, 9, 1, tzinfo=UTC)
    save_manifest(
        tmp_path,
        {
            "oracle_cards": _entry(
                path, datetime.now(UTC) - timedelta(hours=48), updated_at
            )
        },
    )
    responses.add(
        responses.GET,
        BULK_DATA_URL,
        json={
            "data": [
                {
                    "type": "oracle_cards",
                    "jsonl_download_uri": DOWNLOAD_URL,
                    "updated_at": updated_at.isoformat(),
                }
            ]
        },
    )

    client = ScryfallBulkClient("test-agent/1.0", tmp_path)
    client.fetch("oracle_cards")

    # bulk-data listing only; the file itself was not re-downloaded
    assert [c.request.url for c in responses.calls] == [BULK_DATA_URL]
    assert is_cache_fresh(load_manifest(tmp_path)["oracle_cards"], 24)


@responses.activate
def test_unknown_bulk_type_raises(tmp_path):
    responses.add(responses.GET, BULK_DATA_URL, json={"data": []})
    client = ScryfallBulkClient("test-agent/1.0", tmp_path)
    with pytest.raises(ValueError, match="no bulk data"):
        client.fetch("oracle_cards")


@responses.activate
def test_load_cards_streams_objects(tmp_path):
    responses.add(
        responses.GET,
        BULK_DATA_URL,
        json={
            "data": [
                {
                    "type": "oracle_cards",
                    "jsonl_download_uri": DOWNLOAD_URL,
                    "updated_at": "2026-09-06T09:00:00+00:00",
                }
            ]
        },
    )
    responses.add(
        responses.GET,
        DOWNLOAD_URL,
        body=_jsonl_gz([{"oracle_id": "a"}, {"oracle_id": "b"}]),
    )
    client = ScryfallBulkClient("test-agent/1.0", tmp_path)
    assert [c["oracle_id"] for c in client.load_cards("oracle_cards")] == ["a", "b"]
