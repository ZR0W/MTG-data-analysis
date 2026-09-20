# Handoff — project state, open issues, and ideas

Living status doc. Read this before picking the project up; it records what is finished,
what is known-broken or unverified, and what is worth building next.

**Last updated:** 2026-09-20, on branch `claude/mtg-keyword-color-trends-cbftfq`.

## Where the project stands

The pipeline is complete and verified against live Scryfall data. 75 tests pass, ruff is
clean, and `validate` passes on the full dataset: **38,633 cards across 574 sets**.

| Area | State |
|---|---|
| Ingestion (`ingest/`) | Done. Bulk endpoint only, 24h TTL, cache-hit makes zero HTTP calls. Verified live. |
| Normalization (`transform/`) | Done. Five Parquet tables; zero parser drops on 38,633 real cards. |
| Metrics (`metrics/core.py`) | Done. Raw count, colour share, penetration rate, `trend_report`. |
| The eight analyses (`analysis/`) | Done. All return DataFrames with separate `plot_*` helpers. |
| Notebooks | Done. Both execute end to end; full educational write-ups with worked examples; outputs committed. |
| Docs | Done. `README.md` (project description + real-data charts), `CLAUDE.md` (agent invariants), this file. |
| Extensions (`extensions/`) | Deliberately stubbed — see "Ideas" below. |

Real-data checks that have actually been run:

- `fetch` twice — second run logged a cache hit with no HTTP calls.
- `build` with the full `default_cards` pass: `first_printed_year_is_estimate` is false for
  all 38,633 rows.
- `validate`: `OK: 38633 cards, 24932 keyword rows, 44698 color rows, 7426 denominator rows`.
- All five awkward layouts spot-checked (transform, modal DFC, split, adventure, meld),
  plus `art_series` found in the wild and confirmed correctly excluded.
- Keyword distributions sanity-check against Magic knowledge: Haste 68% red, Reach 64%
  green, Deathtouch 62% black, Equip 59% colourless.
- The brief's premise reproduced: for Double strike/red, fractional share 0.418 against
  penetration 0.0085 — the two metrics genuinely diverge. Haste/red shows the reverse
  divergence over time (penetration rising ~0→12%, share falling ~90%→65%).

## Fixed along the way

1. **Scryfall dropped `download_uri`.** The endpoint now returns only
   `jsonl_download_uri`, pointing at gzipped JSON Lines rather than a JSON array. This
   crashed `fetch` with `KeyError` on first live contact. `bulk_client.py` now reads that
   field, caches `{bulk_type}.jsonl.gz`, and streams with `gzip` + line-by-line
   `json.loads`; `ijson` was dropped. Real sizes are ~25 MB (`oracle_cards`) and ~78 MB
   (`default_cards`) compressed.
2. **`vanguard`/`planechase`/`archenemy` polluted `paper_only`** — Avatars, Planes and
   Schemes are game pieces, not castable cards, and were ~6% of the colourless bucket. All
   three added to `set_type_exclude`.
3. **Per-set periods are unreadable at 574 sets.** Default changed to `rolling_sets` with
   `group_size: 10`.
4. **`art_series`** (2,243 cards) needed no fix — Scryfall tags them `memorabilia`, which
   was already excluded.

## Open issues

### 1. Pie-break silently picks a modern period as "historical" (highest priority)

Running `pie_break(con, "Double strike")` at `group_size=5` produces a series that
**starts in 2018**, and labels white the `original_dominant_color` — even though the
keyword debuted in Legions in 2003. No earlier period cleared `min_period_weight=3.0`,
because a sparse keyword spread across ~115 periods averages about one appearance each.
The function then takes "the earliest qualifying period" at face value and reports a 2018
snapshot as the mechanic's historical owner.

Nothing errors; the output is just wrong in a way only domain knowledge catches. Worth
fixing before anyone quotes a pie-break result. Options, roughly in order of preference:

- Pick the historical owner from the earliest periods that *together* hold some share of
  the keyword's all-time weight (say the first 10%), rather than the first period over a
  fixed threshold.
- Auto-coarsen the grouping for sparse keywords instead of dropping periods.
- At minimum, return the qualifying-period count and the dominant period's date in the
  frame, and have `plot_pie_break` say which period the owner came from.

### 2. `color_drift`'s x-axis is ordinal, not dated

A correction to what this doc previously claimed: `keyword_vectors` reads `period` and
`period_order` from `keyword_facts`, so drift **does** respect `set_period_config` like
everything else. The real difference is in the plot — `plot_color_drift` puts
`period_order` (an integer index) on the x-axis, where the other seven charts use
`period_released_at` (a date). Because drift also drops periods under
`min_keyword_weight`, that index is not evenly spaced in time, so the line implies a
regular cadence that does not exist. Switching the axis to `period_released_at` is a
small change.

### 3. `group_size=10` was validated on two charts, not eight

It was chosen by eyeballing Haste penetration and design volume. `rarity_migration`,
`type_crossover`, `pie_break` and the heatmap were never checked at that setting — and
issue #1 suggests sparse-keyword charts may want a different grouping entirely. A
per-chart default may be more honest than one global number.

### 4. Sets sharing a release date

Ties are broken by set code, which fixes `set_order` and therefore every `rolling_sets`
boundary. Never spot-checked against real same-day releases, of which there are many in
the modern schedule.

### 5. Sparse keywords are unstress-tested generally

Keywords with one or two total appearances will produce `NaN`/zero-denominator rows
throughout `trend_report`. The `NaN` semantics are correct by design, but nobody has
looked at what the charts do with them.

## Ideas worth building

**Near-term, small:**

- **`mtg-analysis report`** — render all eight analyses to static PNG/HTML without
  Jupyter. Deferred at planning time; now that charts are committed to `docs/images/`,
  this would also keep the README current automatically.
- **Confidence bands on rates.** A penetration rate computed from a three-card denominator
  should not look as solid as one from three hundred. Even a simple binomial interval
  would stop small periods from reading as signal.
- **Reprint analysis.** `default_cards` is already fetched for `first_printed_year` but
  otherwise unused — printing counts per `oracle_id` would answer "how often has this been
  reprinted, and does that correlate with keyword or colour?"

**The brief's Step 6, still unbuilt:**

- **Informal mechanic mining** (`extensions/text_mining.py`) — regex/pattern dictionary
  over `oracle_text` for the mechanics that have no formal keyword: impulse draw
  ("exile the top card… you may play it this turn"), rummaging, scry-adjacent effects.
- **Functional categorisation** (`extensions/categorization.py`) — removal, ramp, card
  draw, counterspells. This is what answers "is card draw still blue-dominant?"
- **Power/toughness and mana efficiency by colour over time** — creature stats per mana
  value, which would show power creep directly rather than by proxy.

Both stubs emit `(oracle_id, mechanic)` rows precisely so they join to `card_facts` and
reuse every existing rate calculation unchanged.

**Bigger:**

- **Set-level design fingerprints** — cluster sets by their keyword mix to find which sets
  were mechanically unusual for their era.
- **Colour-pair analysis** — the current model attributes to single colours; guild-level
  identity (Boros vs Izzet toolboxes) is a different and interesting cut.

## Setup

```bash
git clone https://github.com/ZR0W/MTG-data-analysis.git
cd MTG-data-analysis
git checkout claude/mtg-keyword-color-trends-cbftfq
uv sync --all-groups
uv run pytest                          # expect 75 passed
uv run mtg-analysis fetch --verbose    # data/ is gitignored; re-fetch if absent
uv run mtg-analysis build --verbose    # the default_cards pass is the slow step
uv run mtg-analysis validate
```

A full rebuild from live Scryfall takes a few minutes and ~100 MB of download.
