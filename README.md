# MTG-data-analysis

A reusable local dataset of Magic: The Gathering cards, built for asking how keyword
mechanics are distributed across colours and how that distribution has changed over time.

The point is to parse Scryfall's bulk data **once** into normalized tables, then answer
many questions against those tables — not to re-scrape or re-derive per question.

## Quick start

```bash
uv sync --all-groups
uv run mtg-analysis fetch      # downloads Scryfall bulk data (at most once per 24h)
uv run mtg-analysis build      # parses it into data/processed/*.parquet
uv run mtg-analysis validate   # data-quality checks on the built tables
uv run jupyter lab notebooks/  # the analyses
```

`data/` is gitignored — the two CLI commands regenerate it from scratch.

## How the pipeline is split

**Ingestion** (`ingest/`) only ever uses Scryfall's `/bulk-data` endpoint, sends a
descriptive `User-Agent`, and records every download in `data/raw/manifest.json`. While a
cached file is younger than the TTL, `fetch` makes **zero network calls**; past the TTL it
checks the upstream `updated_at` and skips the download if nothing changed.

**Transform** (`transform/`) is the only code that parses raw JSON. It is idempotent: the
same cache produces the same tables, so re-running an analysis never re-parses the bulk
file.

**Metrics and analysis** (`metrics/`, `analysis/`) read only the parquet tables, through
DuckDB views.

## Tables

| Table | Grain | Notes |
|---|---|---|
| `cards` | one row per `oracle_id` | resolved colours/keywords, `first_printed_year`, `is_multiface`, `in_paper_only` |
| `card_colors` | card x colour | both weighting schemes |
| `card_keywords` | card x keyword | the core join key |
| `sets` | one row per set | the chronological timeline axis |
| `color_totals` | set x colour x weighting x filter | the denominator for every rate |

Two derived views are registered on connect: `card_facts` (cards joined to colours and
periods) and `keyword_facts` (the same, joined to keywords).

### Multi-faced cards

For transform / modal DFC / split / adventure / meld cards, top-level `colors` can be null
and keywords can live on the faces. Resolution triggers on the *presence of `card_faces`*
rather than on a list of layout names, so layouts Scryfall adds later still resolve.
Colours and keywords are unioned across faces, `cmc` always comes from the top level (never
summed per face), and the card is flagged `is_multiface` so it can be excluded where
face-splitting would distort a result.

### Colour weighting

Multicolour attribution is never silently collapsed to one scheme — both are stored:

- `weight_fractional` = 1/n per colour. Shares sum to 100% across the pie; use it for
  "60% of Double Strike is red".
- `weight_inclusive` = 1.0 per colour. Counts can exceed the card count when summed; use it
  for "any card touching red".

Colourless cards get a single `C` row with both weights at 1.0. Every function that uses a
weighting takes it as an argument and labels it in its output.

### The time axis is sets, not calendar buckets

Each Magic set is one period, running from its release until the next set's release, with
sets ordered by release date (`sets.set_order`). Set-level grain is what gets materialized;
grouping into coarser periods happens at query time:

```python
from mtg_analysis.analysis.db import get_connection, set_period_config
from mtg_analysis.config import PeriodGroupConfig

con = get_connection("data/processed")                                  # one period per set
set_period_config(con, PeriodGroupConfig("rolling_sets", group_size=5))  # 5 sets per period
```

Changing the grouping never requires a rebuild.

### Set filtering

`in_paper_only` marks cards outside the excluded `set_type` list in `config/config.yaml`
(`masters`, `memorabilia`, `funny`, `token`, `alchemy`, …). Analysis defaults to
`set_type_filter="paper_only"`; pass `"unfiltered"` for questions that need reprint sets.
The flag lives on the card itself so a rate's numerator and its `color_totals` denominator
can never fall out of sync.

## The three metrics, and why they ship together

```python
from mtg_analysis.metrics.core import trend_report
trend_report(con, "Double strike", "R")
```

1. **Raw count** — an unweighted headcount.
2. **Colour share** — that colour's slice of the keyword. "60% of Double Strike is red."
3. **Penetration rate** — the share of that colour's cards carrying the keyword, against
   `color_totals`. "What % of red cards have Haste, and is it rising."

(2) and (3) can move in opposite directions — a colour's share of a keyword can rise while
its actual usage falls, because every colour printed less of it. `trend_report` returns
all three plus the denominator so that trap is visible rather than latent. A zero
denominator yields `NaN`, never a misleading `0%`.

## Analyses

`analysis/` holds the eight deliverables as reusable functions, each returning a Polars
DataFrame with a matching `plot_*` helper: keyword x colour heatmap, per-keyword time
series, colour identity drift (cosine similarity of keyword mixes), pie-break tracking,
rarity migration, type-line crossover, a complexity proxy, and the design-volume context
chart.

## Future work

`extensions/` is stubbed, not implemented: informal mechanic mining over `oracle_text`
(impulse draw, rummaging) and functional categorization (removal, ramp, card draw). Both
emit `(oracle_id, mechanic)` rows so they plug into the existing `color_totals` rate math
unchanged.

## Development

```bash
uv run pytest
uv run ruff check .
```
