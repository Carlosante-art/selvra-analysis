# selvra-analysis

**Pre-registered, reproducible analyses of personal CGM data.** Every analysis states its question, its thesis and what would disprove it *before* the data is touched, and the git history proves the order.

Built by Carl Karjalainen Joels, who lives with type 1 diabetes and analyses his own Dexcom data. The analysis method follows the epistemic principles of the [Selvra protocol](https://github.com/Carlosante-art/Selvra-1): every claim is labelled as *observed*, *derived*, *interpreted* or *self-reported*, and data quality problems are flagged, never silently deleted.

## What is here

| Path | What |
|---|---|
| [`ANALYSMALL.md`](ANALYSMALL.md) | The nine-step method every analysis follows (Swedish) |
| [`src/selvra_analysis/`](src/selvra_analysis/) | Ingestion of Dexcom Clarity exports and the personal event log into DuckDB; synthetic data generator |
| [`transform/`](transform/) | dbt project: staging, artefact flags, daily metrics, day context, episode tools, tests |
| [`analyses/`](analyses/) | One folder per analysis: pre-registration first, then code and results |

## Pipeline

```
Clarity CSV ──▶ raw.clarity_events ──▶ stg_cgm_readings      parse, dedupe overlapping exports, Low/High as censored values
                                        int_cgm_segments      gaps, contiguous runs, inferred sensor sessions
                                        int_cgm_flagged       early sensor period, suspected compression lows, implausible jumps
                                        fct_glucose_daily     coverage, mean, CV, GMI, time in/above/below range, with and without artefacts
                                                 │
handelser.csv ─▶ raw.personal_events ─▶ stg_personal_events  │
                                        fct_day_context ◀────┘  illness, logged vs inferred sensor changes, alcohol, training, travel …
                                                 │
                                        mart_analysis_days    where every analysis starts: one row per day, metrics + context
```

### Episode tools

Two dbt macros in [`transform/macros/episodes.sql`](transform/macros/episodes.sql) cover the most common analysis shape, *what happens after X*:

- `consecutive_runs(relation, date_column, condition, min_length)` finds runs of consecutive days meeting a condition. A day without data breaks a run.
- `event_windows(runs, days, days_after, days_before)` returns the days around each run, joined to the day table, with `in_other_run` marking days contaminated by another episode.

They take the episode definition as input and never define one. What counts as "high" is decided in each analysis's pre-registration.

## Data-health dashboard

A private working view, rendered with [Quarto](https://quarto.org) from the same marts the analyses use: coverage per day, an ambulatory glucose profile for the last 14 days, time in ranges per day, artefact flags per week, the last 30 days with logged context, and how complete the event log is.

```bash
make dashboard   # writes dashboard/index.html
```

The rendered file contains personal health data and is git-ignored. Only `dashboard/index.qmd` is committed.

## Run it

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync

# Demo on synthetic data (no personal data needed)
make demo

# Your own data
#   data/raw/clarity/*.csv   Clarity exports (any number, overlaps are fine)
#   data/raw/handelser.csv   your event log, format in data/handelser.mall.csv (optional)
make build
```

`make build` loads everything, rebuilds the models and runs all tests (dbt data and unit tests, plus `make test` for the Python side). The event log is validated strictly: an unknown event type or an unreadable date stops the load and names the line.

## Privacy

Raw exports, the event log and the DuckDB file are git-ignored. Patient identifiers in the Clarity export are dropped at ingestion, and a test guarantees they never reach the database. Published results use aggregated figures and patterns, not raw data. CI runs on synthetic data only.

## Known limitations of the source data

- Clarity timestamps are local wall-clock time without a zone. The pipeline converts them to UTC instants (`reading_at`) and keeps local time (`reading_at_local`, `reading_date`) for time of day and calendar days. The autumn hour that occurs twice is resolved by transmitter time within each export file; days are 23, 24 or 25 hours long and coverage is measured against the real length. A unit test pins this with known inputs. The local zone is the dbt var `local_timezone` (Europe/Stockholm); travel across zones is not modelled.
- The EGV export has no reliable sensor-start event. Sensor changes are inferred from a transmitter ID change or a gap of two hours or more, and compared with the event log in `fct_day_context`.
- Readings outside the sensor range are exported as `Low` or `High`. They are stored as censored values at the range limit (2.2 and 22.2 mmol/L), never dropped.
- The compression-low flag is a heuristic (interpreted, not observed). Metrics are always available with and without it.
