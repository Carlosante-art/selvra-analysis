DB ?= data/selvra.duckdb
DBT = cd transform && SELVRA_DUCKDB=../$(DB) uv run dbt

.PHONY: demo build test lint

## Synthetic data end to end: generate, load, transform, test
demo:
	uv run python -m selvra_analysis.synthetic data/sample
	uv run python -m selvra_analysis.ingest_clarity data/sample/*.csv --db $(DB)
	$(DBT) build --profiles-dir .

## Your own Clarity exports in data/raw/
build:
	uv run python -m selvra_analysis.ingest_clarity data/raw/*.csv --db $(DB)
	$(DBT) build --profiles-dir .

test:
	uv run pytest -q

lint:
	uv run ruff check src tests
