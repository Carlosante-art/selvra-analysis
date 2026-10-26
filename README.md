# selvra-analysis

**Pre-registered, reproducible analyses of personal CGM data.** Every analysis states its question, its thesis and what would disprove it *before* the data is touched, and the git history proves the order.

Built by Carl Karjalainen Joels, who lives with type 1 diabetes and analyses his own Dexcom data. The analysis method follows the epistemic principles of the [Selvra protocol](https://github.com/Carlosante-art/Selvra-1): every claim is labelled as *observed*, *derived* or *interpreted*, and data quality problems are flagged, never silently deleted.

## What is here

| Path | What |
|---|---|
| [`ANALYSMALL.md`](ANALYSMALL.md) | The nine-step method every analysis follows (Swedish) |
| [`src/selvra_analysis/`](src/selvra_analysis/) | Ingestion of Dexcom Clarity CSV exports into DuckDB, and a synthetic data generator |
| [`transform/`](transform/) | dbt project: staging, sensor-artefact flags, daily glucose metrics, tests |
| [`analyses/`](analyses/) | One folder per analysis: pre-registration first, then code and results |

## Pipeline

```
Clarity CSV ──▶ ingest (Python) ──▶ raw.clarity_events (DuckDB)
                                        │
                                        ▼  dbt
                    stg_cgm_readings      parse, dedupe overlapping exports, Low/High as censored values
                    int_cgm_segments      contiguous recording runs, gaps, probable sensor changes
                    int_cgm_flagged       artefact flags: early sensor period, suspected compression lows, implausible jumps
                    fct_glucose_daily     coverage, mean, CV, GMI, time in/above/below range, with and without flagged readings
```

Patient identifiers (name, date of birth) in the Clarity export are dropped at ingestion and never reach the database.

## Run it

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync

# Demo on synthetic data (no personal data needed)
make demo

# Your own data: put Clarity CSV exports in data/raw/, then
make build
```

`make build` loads every CSV in `data/raw/`, rebuilds the models and runs all tests. Exports that overlap in time are deduplicated.

## Privacy

Raw exports and the DuckDB file are git-ignored. Published results use aggregated figures and shifted dates. Nothing in this repository contains real personal health data; CI runs on synthetic data only.

## Known limitations of the source data

- Clarity timestamps are local display time. Daylight-saving changes create a duplicated or missing hour twice a year.
- The EGV export has no reliable sensor-start event. Sensor changes are inferred from gaps of two hours or more, and confirmed against the personal event log when available.
- Readings outside the sensor range are exported as `Low` or `High`. They are stored as censored values at the range limit (2.2 and 22.2 mmol/L), never dropped.
