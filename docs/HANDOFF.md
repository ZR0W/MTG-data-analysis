# Handoff: verification against real Scryfall data

For an agent (or human) with real network access. The pipeline is complete and pushed,
but it has **never run against real Scryfall data** — the session that built it was in a
sandbox whose network policy blocked `api.scryfall.com` (403 on CONNECT at the proxy).
Your job is to close that gap.

## Status

Branch: `claude/mtg-keyword-color-trends-cbftfq`
Commits: `a0b7044` (pipeline), `f2a6334` (notebooks, README, chart fixes)

**Verified in the build session**

- 75 tests pass (`uv run pytest`), `ruff` clean.
- The whole `fetch → build → validate →` analysis path ran end to end, and both notebooks
  executed without error — but against a **seeded synthetic cache** (~2,880 generated
  cards across 24 fake sets, including multi-face cards and reprint-only earlier
  printings), not real data.
- The eight analysis deliverables all return data and render charts.

**Not verified**

- Any real HTTP download: `ScryfallBulkClient.list_bulk_data` / `fetch` / `_download`
  against the live endpoint. Covered only by mocked tests (`tests/test_cache.py`).
- Parsing of real multi-face cards. The parser was written against hand-built fixtures
  that mimic Scryfall's shape; real oddities (meld, reversible, `art_series`, missing
  `oracle_id`, unusual layouts) have never touched it.
- Behaviour at real data volume: ~35k cards and ~900 sets versus 2,880 and 24.

## Setup

```bash
git clone https://github.com/ZR0W/MTG-data-analysis.git
cd MTG-data-analysis
git checkout claude/mtg-keyword-color-trends-cbftfq
uv sync --all-groups
uv run pytest          # expect 75 passed
```

Read `CLAUDE.md` first — it lists the invariants that matter.

## Step 1 — Live fetch

```bash
rm -rf data/                        # make sure no synthetic cache is mistaken for real data
uv run mtg-analysis fetch --verbose
uv run mtg-analysis fetch --verbose # second run: must be a cache hit
```

Check:

- Both files land in `data/raw/` with a `manifest.json` recording `downloaded_at`,
  `scryfall_updated_at` and a sha256. Rough sizes: `oracle_cards` ~150–250 MB,
  `default_cards` a few GB (it grows; treat these as order-of-magnitude).
- **The second run must log `cache hit` and make zero HTTP requests.** This is the
  Scryfall-etiquette guarantee; if it re-downloads, that's a bug in
  `ingest/cache.py:is_cache_fresh` or the manifest round-trip.
- Memory stays flat during download and parse — `load_cards` streams the array with
  `ijson` and must never hold the whole file.

Tight on disk? `--type oracle_cards` alone is enough for everything except
`first_printed_year` (then use `build --skip-default-cards`).

## Step 2 — Build and validate

```bash
uv run mtg-analysis build --verbose
uv run mtg-analysis validate
```

Expect roughly (order of magnitude, not exact):

- `cards` ~30–40k rows, `card_colors` slightly more (multicolour cards contribute a row
  per colour), `card_keywords` in the tens of thousands, `sets` ~900+,
  `color_totals` = sets x colours x 2 weightings x 2 filters.
- `validate` prints `OK: ...`. It fails loudly on duplicate `oracle_id`, a colour outside
  `{W,U,B,R,G,C}`, any card whose fractional weights don't sum to 1.0, orphan rows, or a
  missing `color_totals` variant.

The `default_cards` pass (`compute_first_printed_year`) is the slow part — several minutes
is normal.

## Step 3 — Spot-check real cards

This is the highest-value step: the parser has only ever seen synthetic fixtures. Check a
handful of real cards of each awkward layout, e.g.

| Layout | Card | What to confirm |
|---|---|---|
| transform | Huntmaster of the Fells | colours unioned across faces (R and G), `is_multiface` true, `cmc` 4 not 8 |
| modal DFC | Valki, God of Lies | colours from both faces (B and R), keywords unioned |
| split | Fire // Ice | colours R and U, `cmc` 4 (top-level, not summed per face) |
| adventure | Brazen Borrower | Flash and Flying both present, colour U |
| meld | Bruna, the Fading Light | parses at all; both halves present as separate oracle ids |

```python
import polars as pl
cards = pl.read_parquet("data/processed/cards.parquet")
cards.filter(pl.col("name").str.contains("Huntmaster")).select(
    "name", "colors", "keywords", "cmc", "is_multiface", "layout"
)
```

Also sanity-check the keyword distribution against Magic knowledge — if these look wrong,
something upstream is wrong:

- Double strike overwhelmingly red and white
- Flying concentrated in blue and white
- Reach almost entirely green
- Deathtouch concentrated in black (with green second)

And confirm keyword spelling before querying: Scryfall capitalizes only the first word,
and lookups are exact-match.

```python
con.execute("SELECT DISTINCT keyword FROM card_keywords ORDER BY 1").pl()
```

## Step 4 — Reproduce the brief's example claims

```python
from mtg_analysis.analysis.db import get_connection
from mtg_analysis.config import load_config
from mtg_analysis.metrics.core import color_share, penetration_rate, trend_report

config = load_config()
con = get_connection(config.paths.processed_dir, config.periods)

for w in ("fractional", "inclusive"):
    print(w, color_share(con, "Double strike", "R", weighting=w))

trend_report(con, "Haste", "R").tail(20)   # share and penetration side by side
```

Report both metrics with the weighting named, and say explicitly whether share and
penetration move together or diverge — the brief's whole point is that they can diverge,
and only real data will tell us whether they actually do for Double strike / Haste.

## Step 5 — Notebooks at real density

```bash
uv run jupyter lab notebooks/
```

Run `01_exploratory_heatmap.ipynb` then `02_trend_deep_dive.ipynb`. The thing most likely
to look wrong is chart legibility: ~900 sets on the x-axis is ~40x the density the charts
were eyeballed at. Watch for overplotted lines, a legend landing on the marks, and
unreadable heatmap cell labels. Per-set periods will be noisy — compare against grouped
periods:

```python
from mtg_analysis.analysis.db import set_period_config
from mtg_analysis.config import PeriodGroupConfig
set_period_config(con, PeriodGroupConfig(mode="rolling_sets", group_size=5))
```

If per-set is unusable at real density, changing the default in `config/config.yaml` is a
reasonable call — say so rather than silently switching it.

## Known risks

- **Real layouts the fixtures don't cover** — `reversible_card`, `art_series`, tokens, and
  anything with no top-level `oracle_id`. `parse_card` returns `None` for objects with no
  recoverable `oracle_id`; count how many get dropped and check the drops are all things
  that *should* be dropped.
- **`first_printed_year`** depends on the multi-GB `default_cards` file; if it was skipped,
  `first_printed_year_is_estimate` is true and any "when did this first appear" claim is
  unreliable.
- **Set-type exclusions** in `config/config.yaml` were chosen from the brief, not from the
  real distribution. Check `SELECT DISTINCT set_type FROM cards` against that list — there
  may be real `set_type` values worth excluding (or wrongly excluded) that nobody has seen
  yet.
- **Sets sharing a release date** are ordered by set code as a tiebreak; at real density
  this affects `set_order` and therefore `rolling_sets` grouping boundaries.

## What to report back

1. Row counts for all five tables, and `validate` output.
2. How many raw objects `parse_card` dropped, and why.
3. Any spot-check mismatch from step 3 (this is the one most likely to surface a real bug).
4. Whether the step 4 example claims reproduced, with both metrics and the weighting named.
5. Whether the charts hold up at real density, and whether per-set should stay the default
   period grouping.
