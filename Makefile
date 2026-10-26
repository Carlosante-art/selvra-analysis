DB ?= data/selvra.duckdb
DBT = cd transform && SELVRA_DUCKDB=../$(DB) uv run dbt
USER_ID ?= 98345704-bed3-4f31-ac83-4818171d39ea

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

## Live data direct from Supabase — kräver ANALYSIS_DB_URL i env
## Kör: ANALYSIS_DB_URL=postgresql://... make build-live
build-live:
	uv run python -m selvra_analysis.ingest_supabase --user-id $(USER_ID) --db $(DB)
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
