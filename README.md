# selvra-analysis

**Pre-registered, reproducible analyses of personal CGM data.** Every analysis states its question, its thesis and what would disprove it *before* the data is touched, and the git history proves the order.

Built by Carl Karjalainen Joels, who lives with type 1 diabetes and analyses his own Dexcom data. The analysis method follows the epistemic principles of the [Selvra protocol](https://github.com/Carlosante-art/Selvra-1): every claim is labelled as *observed*, *derived*, *interpreted* or *self-reported*, and data quality problems are flagged, never silently deleted.

## What is here

| Path | What |
|---|---|
| [`ANALYSMALL.md`](ANALYSMALL.md) | The nine-step method every observational analysis follows (Swedish) |
| [`N1MALL.md`](N1MALL.md) | Protocol and report template for n-of-1 experiments, following SPENT 2019 and CENT 2015 (Swedish) |
| [`src/selvra_analysis/`](src/selvra_analysis/) | Ingestion of Dexcom Clarity exports and the personal event log into DuckDB; synthetic data generator |
| [`transform/`](transform/) | dbt project: staging, artefact flags, daily metrics, day context, episode tools, tests |
| [`analyses/`](analyses/) | One folder per analysis: pre-registration first, then code and results |

## Pipeline

```
Clarity CSV ──▶ raw.clarity_events ──▶ stg_clarity_readings  parse, dedupe overlapping exports, DST, Low/High as censored
Supabase ────▶ raw.share_readings ──▶ stg_share_readings    Dexcom Share via Selvra Diabetes: exact instants, mg/dL
Nightscout ──▶ raw.nightscout_*    ──▶ stg_nightscout_*      the DIY community's own server: glucose, bolus insulin, carbs
                                        int_cgm_readings      both sources; Share only after the last Clarity reading
                                        int_cgm_segments      gaps, contiguous runs, inferred sensor sessions
                                        int_cgm_flagged       early sensor period, suspected compression lows, implausible jumps
                                        int_glycaemic_events  consensus 2023 hypo/hyper events (level 1, level 2, extended)
                                        fct_glucose_daily     coverage, mean, CV, GMI, time in/above/below range, event counts,
                                                              with and without artefacts
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

## How an analysis is run

Every analysis follows [`ANALYSMALL.md`](ANALYSMALL.md). What makes a result trustworthy is the order things happen in, and the repository enforces it:

1. **Pre-registration** of question, thesis, falsification criterion, metric definitions and the statistical plan: one primary outcome, the effect size and its unit, the smallest effect that matters, the interval method, sensitivity analyses and a decision rule. Committed before any code.
2. **Blind development.** The analysis code is written against synthetic data, which contains none of the answers.
3. **Freezing.** The code's commit hash goes into the pre-registration. On real data, [`provenance.run_analysis`](src/selvra_analysis/provenance.py) refuses to run if the analysis code, the pipeline or the pre-registration have changed since.
4. **Run records.** Every run writes the result, commit, frozen commit, tool versions, parameters and data version to `korningar/`. The data version is the SHA-256 of each input file, recorded at ingestion (`raw.source_files`); file names are never stored, because Clarity names exports after the patient. The first run on real data is marked confirmatory; any later one is marked as a rerun.

**Uncertainty.** Days from one person are not independent, so [`stats.block_bootstrap_difference`](src/selvra_analysis/stats.py) resamples runs of consecutive days (circular block bootstrap, Politis & Romano 1992). A test shows why: on simulated autocorrelated days with no real effect, an ordinary bootstrap interval covers zero only about 65 % of the time instead of 95 %; blocks of 7 to 14 days bring it to 87–89 %.

[`analyses/000-exempel-traning`](analyses/000-exempel-traning/) runs the whole workflow on synthetic data (`make example`, also in CI). The synthetic data has no training effect built in, and the example correctly ends "undetermined".

## Reports

```bash
make rapport            # the last 30 days
make rapport DAGAR=14
```

A descriptive report in Swedish: time in each range, mean, GMI and CV pooled over all readings in the period, consensus 2023 hypo/hyper events with and without artefacts, the previous period beside it, and each metric against the consensus target. It warns when the period is below the consensus minimum (14 days, 70 % coverage) and marks synthetic data. It describes; questions about causes are studies. Written to `data/rapporter/` (git-ignored).

## The study engine

A study is a file. [`studies/`](studies/) holds one folder per study with a `studie.yml`: question, thesis, falsification, design, outcome, analysis and the smallest effect that matters. Readings arrive every five minutes from Selvra Diabetes; the engine does the rest:

```bash
uv run python -m selvra_analysis.study las    studies/NNN/studie.yml   # lock, draw schedule; then commit
uv run python -m selvra_analysis.study status studies/NNN/studie.yml   # progress and data quality, never the effect
uv run python -m selvra_analysis.study kor    studies/NNN/studie.yml   # the single confirmatory analysis
```

The final run refuses if the study file, the schedule or the pipeline changed after locking, if the study folder is not committed, if the study is still running, or if it has already been run. The verdict comes from a fixed rule set by one number written before the start. Format: [`studies/README.md`](studies/README.md).

## The autonomous layer

Around the study engine sits a loop that finds questions, designs studies and interprets results. The LLM steps (marked *) need `ANTHROPIC_API_KEY` in `.env`; everything else runs without it.

```bash
make log start=2026-10-24 typ=traning    # log one event
make dagbok                              # morning review: yesterday's numbers, then questions
make import-kalender fil=kalender.ics    # events from your calendar, keyword-matched
make skanna                              # patterns in the data → study questions
make dreamer fraga="..."                 # question → draft studie.yml *
make tolka studie=studies/NNN/           # verdict → plain language + next step *
make sammanfattning                      # all studies → one synthesis *
make minne                               # what Dreamer has learned so far
make loop                                # fetch → scan → interpret → synthesise *
make schemalagg                          # cron: run the loop every morning at 07:00
```

With a wearable connected (Oura via `OURA_TOKEN`, or Garmin via `GARMIN_EMAIL` + `GARMIN_PASSWORD`), context arrives without logging: sleep and steps load on every `make live`, `wearable_source` states which device produced each day, and the exposure `hoga_steg` (a day reaching `high_steps_threshold`, default 10 000 steps) is derived from the data — days without wearable data fall out of both study groups instead of counting as unexposed.

The scanner proposes questions without revealing effect sizes — measuring the effect is the study's job, and seeing it first would turn a confirmatory analysis into an exploratory one. Its questions land in [`studies/minne.yml`](studies/minne.yml), Dreamer's persistent memory: every study's question, verdict and lesson, plus open hypotheses. Dreamer reads the memory before designing, so it builds on what is already known instead of repeating it. Dreamer proposes; locking stays a human decision, on purpose. Once a study is locked, the loop runs the confirmatory analysis itself when the data suffices — the decision is the lock, the run is mechanics.

## Experiments: n-of-1

Observational analyses show what follows what. To show what *causes* what for one person, the person runs an experiment: paired periods of intervention and comparison, with the order inside each pair drawn at random before the start ([`N1MALL.md`](N1MALL.md), [`n1.py`](src/selvra_analysis/n1.py)).

- **Schedule** drawn from the operating system's random source, committed with its checksum before day one.
- **Outcome** in a fixed local-time window where the mechanism acts, because whole-day metrics are usually too noisy for an experiment of realistic length. `n1 sd` measures that noise on existing data, and `n1 power` turns it into the number of pairs needed.
- **Analysis** by the paired randomisation test: its null distribution is the 2^n ways the coin flips could have fallen, so it needs neither normality nor independent days. The interval is every effect the test does not reject. Washout days are excluded, and AB and BA pairs are reported separately to expose carryover.

## Quality gates

Every push runs the same gates, in order; any red one stops the result from leaving the lab.

| Question | Gate | Where |
|---|---|---|
| Is the code reviewable? | Complexity ≤ 10, branches ≤ 12, statements ≤ 50, nesting ≤ 4, no imports inside functions, security rules | ruff, `pyproject.toml` |
| Does the architecture hold? | No cycles; studies and reports above statistics; analysis never imports collection code | import-linter, `pyproject.toml` |
| Does the dbt project hold? | Staging one model per source; marts never read sources; tests and docs per model; exceptions documented with reasons | dbt-project-evaluator 1.x, `transform/seeds/` |
| Is the SQL unambiguous? | CTEs instead of subqueries, qualified references, explicit joins | SQLFluff, `transform/.sqlfluff` |
| What do we measure? | Every mart column states its construct, standard, valid range, iglu function, epistemic label and **what it does not measure**; contracts fix names and types | `transform/models/marts/_marts.yml`, `tests/test_ontology.py`, `DATASHEET.md` |
| Is the design sound before it is locked? | Positivity per day type, carryover against the action's known duration, negative control before the action, expected data loss, smallest attainable p and power from your own variability; `las` refuses without a passed review of that exact file | `granska.py`, `docs/studiedesign.md`, `/ny-studie`, agent `studiegranskare` |
| How do we know a claim holds? | Study files must name CENT items and a negative control; the example study reproduces value for value; every number in a report is traceable to its run record | `study.py`, `make reproduce`, `tests/test_study.py` |
| Is the data right? | Readings never lost, ranges, uniqueness, synthetic and real never mixed; freshness of live data on real data | dbt tests, `make verify-real` |
| Do the statistics do what we say? | Type I error, coverage of an injected effect, power, and the block bootstrap's real coverage (87 %, printed in reports) | `tests/test_calibration.py`, weekly at 2000 simulations |

`make verify-real` runs the checks that need real data (freshness, all dbt tests on your data); real data never reaches CI.

## Validated against an independent implementation

Every daily metric and every glycaemic event is checked against [iglu](https://github.com/irinagain/iglu) (Broll et al., *PLoS ONE* 2021), a peer-reviewed R package, on exactly the readings the pipeline used:

```bash
make validate
# daily: OK, 4380 values identical to iglu 4.4.0
# events: OK, 1236 events identical to iglu 4.4.0
```

- **Daily metrics** (mean, SD, CV, GMI, time in each range, with and without artefacts) must equal iglu's to the precision the pipeline publishes, day by day.
- **Glycaemic events** (Battelino et al., *Lancet Diabetes Endocrinol* 2023, Table 4) must be the same set of events with the same first and last reading. The pipeline uses iglu's event logic on raw readings within recording segments, without iglu's interpolation step: the consensus does not specify interpolation, and an interpolated value could start or end an event.

CI runs the check live in R on every push. Without R, `make validate` uses a stored iglu result, and only accepts it when the readings are byte-for-byte the synthetic demo data it was computed from. Your own data needs R and iglu.

Two dbt unit tests pin the hardest cases with hand-derived answers: daylight-saving time in the export, and event boundaries (an event interrupted too briefly to end, level 2 ending while level 1 continues, extended hypoglycaemia, an event cut off by a gap).

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

# Demo on synthetic data (no personal data needed), in its own file data/demo.duckdb
make demo

# Your own data
#   data/raw/clarity/*.csv   Clarity exports, English or Swedish (any number, overlaps are fine)
#   data/raw/handelser.csv   your event log, format in data/handelser.mall.csv (optional)
make build

# Plus readings collected since the last export by Selvra Diabetes (Dexcom Share)
#   .env: ANALYSIS_DB_URL and ANALYSIS_USER_ID (never committed, never printed)
make build-live

# Fetch the latest readings, rebuild and render the dashboard in one go
make live
```

`make build` loads everything, rebuilds the models and runs all tests (dbt data and unit tests, plus `make test` for the Python side). The event log is validated strictly: an unknown event type or an unreadable date stops the load and names the line.

## Privacy

Raw exports, the event log and the DuckDB file are git-ignored. Patient identifiers in the Clarity export are dropped at ingestion, and a test guarantees they never reach the database. Published results use aggregated figures and patterns, not raw data. CI runs on synthetic data only.

## Known limitations of the source data

- **Two sources, one record.** Clarity is the complete history: it includes readings the receiver backfilled after a signal loss. Dexcom Share (collected by Selvra Diabetes) has exact UTC instants but no backfill and no transmitter ID. Staging uses Share only after the last Clarity reading, so no reading is counted twice; export from Clarity now and then to replace Share with the complete record. Every Share load is snapshotted to `data/snapshots/` and its checksum recorded as the data version.

- Clarity timestamps are local wall-clock time without a zone. The pipeline converts them to UTC instants (`reading_at`) and keeps local time (`reading_at_local`, `reading_date`) for time of day and calendar days. The autumn hour that occurs twice is resolved by transmitter time within each export file; days are 23, 24 or 25 hours long and coverage is measured against the real length. A unit test pins this with known inputs. The local zone is the dbt var `local_timezone` (Europe/Stockholm); travel across zones is not modelled.
- The EGV export has no reliable sensor-start event. Sensor changes are inferred from a transmitter ID change or a gap of two hours or more, and compared with the event log in `fct_day_context`.
- Readings outside the sensor range are exported as `Low` or `High`. They are stored as censored values at the range limit (2.2 and 22.2 mmol/L), never dropped.
- The compression-low flag is a heuristic (interpreted, not observed). Metrics are always available with and without it.
