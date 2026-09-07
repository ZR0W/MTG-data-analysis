# Handoff: real-data verification (done) and what's left

Real-data verification is **complete** as of this handoff. The pipeline now runs
end-to-end against live Scryfall data, one real bug was found and fixed, and two
config defaults were changed based on what real density revealed. This doc records
that work for the next session — read the "Findings" section before touching
ingestion or config, and see "Still open" for what nobody has checked yet.

## Status

Branch: `claude/mtg-keyword-color-trends-cbftfq`
Latest commit: `911d1d5` (real-data fix + default tuning), on top of `b8c5c70`,
`f2a6334`, `a0b7044`.

**Verified against live Scryfall data in this session**

- `uv run mtg-analysis fetch` — real download, real cache-hit-on-second-run
  behavior confirmed (zero HTTP calls on repeat within TTL).
- `uv run mtg-analysis build` — real `default_cards` pass ran (not skipped);
  `first_printed_year_is_estimate` is `false` for all 38,633 rows.
- `uv run mtg-analysis validate` — passes: `OK: 38633 cards, 24932 keyword rows,
  44698 color rows, 7426 denominator rows`.
- `parse_card` dropped **zero** of the 38,633 raw `oracle_cards` objects.
- Spot-checked all five awkward layouts from the original ask (transform, modal
  DFC, split, adventure, meld) — all correct. See "Findings" below for the one
  real layout surprise (`art_series`).
- Keyword distributions match Magic knowledge (Double strike W/R, Flying U/W,
  Reach G-dominant, Deathtouch B-then-G).
- Brief's example claim reproduced: Double strike/R share and penetration
  diverge (0.418 fractional share vs 0.0085 penetration) — confirms the brief's
  premise.
- Both notebooks execute end-to-end against real data with no errors.
- 75 tests pass, ruff clean, after updating fixtures to match the real API.

## Findings from this session

1. **Real bug: Scryfall's `/bulk-data` endpoint no longer returns `download_uri`.**
   It now only provides `jsonl_download_uri`, pointing to a gzip-compressed JSON
   Lines file (not the plain JSON array the pipeline was built against). This
   crashed `fetch` immediately with `KeyError: 'download_uri'` on first live run.
   Fixed in `src/mtg_analysis/ingest/bulk_client.py`: reads `jsonl_download_uri`,
   caches as `{bulk_type}.jsonl.gz`, and `load_cards` decompresses with `gzip`
   and parses line-by-line instead of `ijson.items()` over a JSON array (still
   streams, still memory-flat). `ijson` was dropped as a dependency. Real file
   sizes are much smaller than the old estimate since they're compressed:
   `oracle_cards` ~25 MB, `default_cards` ~78 MB (not the 150–250 MB / multi-GB
   figures in the original ask, which assumed uncompressed JSON).
2. **`art_series` layout, seen for real**: 2,243 cards (e.g. the Valki gallery-art
   variant), each its own `oracle_id` with `colors=[]`/`cmc=0`. This is correct —
   they're genuinely non-functional art cards — and Scryfall already tags them
   `set_type: memorabilia`, which was already excluded from `paper_only`. No fix
   needed here; confirms the exclude list does its job for this layout.
3. **`vanguard`/`planechase`/`archenemy` were polluting `paper_only`.**
   `vanguard` cards are 100% colorless (they're avatars, not castable spells);
   `planechase`/`archenemy` are ~45–55% colorless (Plane/Scheme game pieces mixed
   with real reprints). Together they were ~239 of 3,758 colorless-bucket rows
   (~6%) under the old config. **Fixed**: added all three to `set_type_exclude`
   in `config/config.yaml` (user-approved). Note this excludes the real reprints
   bundled into those product's canonical printings too, same coarse-grained
   tradeoff the existing `masters`/`memorabilia`/`funny` exclusions already make.
4. **Per-set charts are unreadable at real density** (574 real sets vs. the
   24-set synthetic fixture). Confirmed visually: Haste/design-volume/complexity
   timeseries were badly overplotted, and the `color_drift` legend sat on top of
   data. Tested `rolling_sets` grouping (group_size=10) — materially clearer.
   **Fixed**: changed `periods.mode` from `per_set` to `rolling_sets` in
   `config/config.yaml` (user-approved), group_size 10.
5. **Distinct `set_type` values in real data** (21 total, up from what the brief
   assumed): `alchemy, archenemy, arsenal, box, commander, core,
   draft_innovation, duel_deck, eternal, expansion, funny, masterpiece, masters,
   memorabilia, minigame, planechase, promo, starter, token, treasure_chest,
   vanguard`. Only `vanguard`/`planechase`/`archenemy` needed action (see #3);
   the rest were already handled correctly by the existing exclude list or are
   legitimately `paper_only` (e.g. `commander`, `expansion`, `core`).

## Still open — nobody has checked these yet

- **`color_drift`'s x-axis uses its own period-order scheme**, not the
  `period_color_totals`/`set_period_config` grouping the other seven
  deliverables use — it was still busy (though not as bad as the others) after
  switching the default to `rolling_sets`, because it isn't affected by that
  setting. Worth deciding whether it should respect the same period config, or
  whether its current per-comparison-index axis is intentional.
- **`rolling_sets` group_size=10 was picked from a quick visual check on two
  charts** (Haste penetration, design volume), not all eight analysis
  deliverables. Worth eyeballing the rest (`rarity_migration`, `type_crossover`,
  `pie_break`, `heatmap`) at group_size 10 before treating it as final — it may
  want to be larger or smaller per-chart.
- **Sets sharing a release date, tiebroken by set code**: this affects
  `set_order` and therefore `rolling_sets` grouping boundaries at real density.
  Never spot-checked against real duplicate-release-date sets.
- **Only two notebooks and a handful of ad-hoc queries were run.** No attempt
  was made to stress-test extreme cases (e.g. keywords with only 1-2 total
  appearances in real data, which will produce a lot of `NaN`/zero-denominator
  rows in `trend_report`).

## Setup (unchanged)

```bash
git clone https://github.com/ZR0W/MTG-data-analysis.git
cd MTG-data-analysis
git checkout claude/mtg-keyword-color-trends-cbftfq
uv sync --all-groups
uv run pytest          # expect 75 passed
uv run mtg-analysis fetch --verbose   # real data is not committed; re-fetch if data/ is gone
uv run mtg-analysis build --verbose
uv run mtg-analysis validate
```

`data/` is gitignored — a fresh clone has no tables. The commands above rebuild
from live Scryfall data in a few minutes (fetch ~100 MB total; the `default_cards`
parse for `first_printed_year` is the slow step).
