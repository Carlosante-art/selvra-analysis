DB ?= data/selvra.duckdb
DBT = cd transform && SELVRA_DUCKDB=../$(DB) uv run dbt

.PHONY: demo build test lint dashboard

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

test:
	uv run pytest -q

lint:
	uv run ruff check src tests

## Private data-health dashboard (rendered file is git-ignored: it contains health data)
dashboard:
	cd dashboard && SELVRA_DUCKDB=../$(DB) uv run quarto render index.qmd
	@echo "Open dashboard/index.html"
