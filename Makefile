DB ?= data/selvra.duckdb
DBT = cd transform && SELVRA_DUCKDB=../$(DB) uv run dbt

.PHONY: demo build build-live test lint dashboard validate example

## Synthetic data end to end: generate, load, transform, test
demo:
	uv run python -m selvra_analysis.synthetic data/sample
	uv run python -m selvra_analysis.ingest_clarity data/sample/clarity_*.csv --db $(DB)
	uv run python -m selvra_analysis.ingest_events data/sample/handelser.csv --db $(DB)
	$(DBT) build --profiles-dir .

## Your own data: Clarity exports in data/raw/clarity/, event log in data/raw/handelser.csv
build:
	uv run python -m selvra_analysis.ingest_clarity data/raw/clarity/*.csv --db $(DB)
	uv run python -m selvra_analysis.ingest_events data/raw/handelser.csv --db $(DB)
	$(DBT) build --profiles-dir .

## Readings collected by Selvra Diabetes (Dexcom Share), from Supabase. Needs ANALYSIS_DB_URL and
## ANALYSIS_USER_ID in .env. Clarity exports already loaded are kept and take precedence.
build-live:
	uv run python -m selvra_analysis.ingest_supabase --db $(DB)
	uv run python -m selvra_analysis.ingest_events data/raw/handelser.csv --db $(DB)
	$(DBT) build --profiles-dir .

## Check daily metrics and glycaemic events against iglu (R). Without R: stored reference, demo data only
validate:
	uv run python -m selvra_analysis.validate_iglu --db $(DB)

## Worked example of the full analysis workflow, on synthetic data
example:
	uv run python analyses/000-exempel-traning/analys.py --db $(DB)

test:
	uv run pytest -q

lint:
	uv run ruff check src tests analyses

## Private data-health dashboard (rendered file is git-ignored: it contains health data)
dashboard:
	cd dashboard && SELVRA_DUCKDB=../$(DB) uv run quarto render index.qmd
	@echo "Open dashboard/index.html"
