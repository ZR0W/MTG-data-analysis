# CLAUDE.md

Orientation for an agent working on this repo. `README.md` is the user-facing guide; this
file is about the invariants you must not break.

## What this is

A reusable local dataset for analysing how Magic: The Gathering keyword mechanics are
distributed across colours and how that has shifted over time. Scryfall bulk data is
downloaded once, parsed once into normalized parquet tables, and then queried repeatedly
through DuckDB. It is deliberately not a script that re-derives everything per question.

## Commands

```bash
uv sync --all-groups          # install (uv + pyproject, src layout, Python >= 3.11)
uv run pytest                 # 75 tests, fast, no network
uv run ruff check .           # lint (line-length 100)

uv run mtg-analysis fetch     # download bulk data into data/raw (respects a 24h TTL)
uv run mtg-analysis build     # parse it into data/processed/*.parquet
uv run mtg-analysis validate  # data-quality checks on the built tables
```

`fetch` takes `--type oracle_cards|default_cards|all` and `--force`; `build` takes
`--force-refresh` and `--skip-default-cards`; all three take `--config` and `--verbose`
(`src/mtg_analysis/cli.py`).

Everything runs through `uv run` — the package is installed into `.venv` from the src
layout, so a bare `python` will not find `mtg_analysis`.

## Architecture

```
ingest/  ->  transform/  ->  data/processed/*.parquet  ->  metrics/ + analysis/
```

The layering rule, which is the point of the whole design:

- **Raw JSON is parsed only in `transform/`.** Nothing downstream reads `data/raw`.
- **Analysis reads parquet only**, through `analysis/db.py:get_connection`.
- **Never call the live `/cards/search` API.** Bulk data only, cached locally.
- Ingestion and transform are idempotent and separable from analysis: re-running an
  analysis must never re-parse the bulk file.

## Tables

Built by `transform/build_tables.py:build_all_tables`, written to `data/processed/`:

| Table | Grain |
|---|---|
| `cards` | one row per `oracle_id` — resolved colours/keywords, `first_printed_year`, `is_multiface`, `in_paper_only` |
| `card_colors` | card x colour, with both weighting schemes |
| `card_keywords` | card x keyword |
| `sets` | one row per set — the chronological timeline axis |
| `color_totals` | set x colour x weighting x set-type-filter — the denominator table |

`analysis/db.py:register_periods` also registers three views on connect: `card_facts`
(cards joined to colours and periods), `keyword_facts` (that, joined to keywords), and
`period_color_totals` (`color_totals` rolled up to the current period grouping). Most
analysis queries should hit these views rather than re-joining the base tables.

## Invariants

Breaking any of these silently corrupts results rather than raising, so treat them as
load-bearing.

1. **Both weightings are always retained and always labelled.**
   `transform/weights.py:compute_color_rows` emits `weight_fractional` (1/n per colour —
   shares sum to 100%) and `weight_inclusive` (1.0 per colour — "any card touching red").
   Every metric takes `weighting` as an argument, validates it via
   `metrics/core.py:validate_options`, and names it in its output. Never pick one
   silently.
2. **Fractional weights per `oracle_id` sum to exactly 1.0.** Asserted in tests and by
   `mtg-analysis validate`.
3. **Colourless cards get a single `C` row** with both weights at 1.0 — not zero rows,
   not one row per colour.
4. **Multi-face resolution keys off the presence of `card_faces`, never a layout
   allowlist** (`transform/card_parser.py:union_colors` / `union_keywords`), so layouts
   Scryfall adds later still resolve. `cmc` always comes from the top level — summing
   per-face `cmc` double-counts split and DFC cards.
5. **The time axis is Magic sets in release order, never calendar buckets.**
   `transform/periods.py:build_sets_table` orders sets by release date (ties broken by set
   code). `color_totals` stays at per-set grain; coarser grouping is applied at query time
   via `PeriodGroupConfig` and `analysis/db.py:set_period_config`, so changing the
   grouping never requires a rebuild. Do not bake periods into the stored tables.
6. **`in_paper_only` lives on the card** (`transform/build_tables.py:build_cards_table`),
   so a rate's numerator and its `color_totals` denominator apply the same set-type filter
   and cannot drift apart. Don't reintroduce a filter that re-derives the exclusion list
   at query time.
7. **Share and penetration are reported together.** `metrics/core.py:trend_report` returns
   raw count, `color_share`, `penetration_rate` and the `color_total` denominator side by
   side, because share and penetration can move in opposite directions. A raw count
   without its denominator is not a finding.
8. **Zero denominators return `NaN`, never `0.0`** — "no data" and "0% share" are
   different claims.
9. **`transform` is idempotent**: the same cache produces the same tables.

## Chart conventions

`analysis/style.py` holds the WUBRG palette, which was stepped until it passed the
categorical checks (lightness band, chroma floor, CVD separation, contrast) against both
light and dark surfaces. Red and green necessarily sit in the 6-8 deutan band, which is
legal only alongside secondary encoding — hence the per-colour dash pattern (`LINE_STYLE`)
and marker (`MARKER`). If you touch the palette: keep the secondary encoding, keep the
legend, and don't substitute naive `#FF0000`-style hues.

Analysis functions return a Polars DataFrame and have a separate `plot_*` helper; keep
that split so results stay testable without matplotlib.

## File map

```
src/mtg_analysis/
  cli.py                  fetch / build / validate
  config.py               Config, PeriodGroupConfig, load_config
  ingest/cache.py         manifest + TTL gate (is_cache_fresh)
  ingest/bulk_client.py   ScryfallBulkClient: list_bulk_data, fetch, load_cards
  transform/card_parser.py    parse_card, union_colors, union_keywords  <- highest bug risk
  transform/weights.py        compute_color_rows
  transform/periods.py        build_sets_table, assign_period, period_lookup
  transform/build_tables.py   the five tables, run_pipeline
  metrics/core.py         raw_count, color_share, penetration_rate, trend_report
  analysis/db.py          get_connection, register_periods, set_period_config
  analysis/*.py           the eight deliverables + plot helpers
  extensions/             deliberately NotImplementedError (future work, not a bug)
tests/                    fixtures in conftest.py cover DFC/split/adventure/colourless
notebooks/                01 overview, 02 deep dive
config/config.yaml        User-Agent, TTL, excluded set_types, period grouping
docs/HANDOFF.md           what still needs verifying against real Scryfall data
```

## Gotchas

- **`data/` is gitignored.** A fresh clone has no tables — run `fetch` then `build` before
  anything in `analysis/` will work. `get_connection` raises `FileNotFoundError` naming
  the missing table if you skip this.
- **Scryfall etiquette is a requirement, not a nicety**: descriptive `User-Agent` (set in
  `config/config.yaml`), bulk endpoint only, and no re-download inside the 24h TTL. A
  fresh cache means literally zero HTTP calls.
- **Bulk data is gzipped JSON Lines**, one card object per line — not a JSON array.
  `load_cards` decompresses and parses a line at a time; the cached files are
  `data/raw/{bulk_type}.jsonl.gz` (roughly 25 MB for `oracle_cards`, 78 MB for
  `default_cards`). `default_cards` is only needed for `first_printed_year`;
  `build --skip-default-cards` falls back to each card's own printing year and sets
  `first_printed_year_is_estimate`.
- **Keyword lookups are exact-match**, and Scryfall capitalizes only the first word
  ("Double strike", "First strike"). Check `SELECT DISTINCT keyword FROM card_keywords`
  before assuming a spelling.
- **`extensions/` raising `NotImplementedError` is intentional.** It documents the shape
  of the future informal-mechanic pipeline (`oracle_id, mechanic` rows that plug into the
  same `color_totals` rate math). Don't "fix" it unless asked to build it.
