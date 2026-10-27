# Your data and the synthetic demo live in separate files, so a demo can never overwrite
# or mix with real data.
DB ?= data/selvra.duckdb
DEMO_DB ?= data/demo.duckdb
DBT = cd transform && SELVRA_DUCKDB=$(abspath $(DB)) uv run dbt
DBT_DEMO = cd transform && SELVRA_DUCKDB=$(abspath $(DEMO_DB)) uv run dbt
DBT_PACKAGES = transform/dbt_packages/dbt_project_evaluator

$(DBT_PACKAGES):
	cd transform && uv run dbt deps --profiles-dir .

.PHONY: demo build build-live live rapport dreamer tolka sammanfattning minne skanna import-kalender loop test lint dashboard validate validate-real example log dagbok reproduce verify-real

## Synthetic data end to end: generate, load, transform, test
demo: $(DBT_PACKAGES)
	uv run python -m selvra_analysis.synthetic data/sample
	rm -f $(DEMO_DB)
	uv run python -m selvra_analysis.ingest_clarity data/sample/clarity_*.csv --db $(DEMO_DB)
	uv run python -m selvra_analysis.ingest_events data/sample/handelser.csv --db $(DEMO_DB)
	$(DBT_DEMO) build --profiles-dir .

## Your own data: Clarity exports in data/raw/clarity/, event log in data/raw/handelser.csv
build: $(DBT_PACKAGES)
	uv run python -m selvra_analysis.ingest_clarity data/raw/clarity/*.csv --db $(DB)
	uv run python -m selvra_analysis.ingest_events data/raw/handelser.csv --db $(DB)
	$(DBT) build --profiles-dir .

## Readings collected by Selvra Diabetes (Dexcom Share), from Supabase. Needs ANALYSIS_DB_URL and
## ANALYSIS_USER_ID in .env. Clarity exports already loaded are kept and take precedence.
build-live: $(DBT_PACKAGES)
	uv run python -m selvra_analysis.ingest_supabase --db $(DB)
	uv run python -m selvra_analysis.ingest_oura --db $(DB)
	uv run python -m selvra_analysis.ingest_events data/raw/handelser.csv --db $(DB)
	$(DBT) build --profiles-dir .

## Live: fetch the latest readings from Selvra Diabetes, rebuild, render the dashboard
live: build-live dashboard

## Descriptive report of the last DAGAR days (default 30): make rapport DAGAR=14
DAGAR ?= 30
rapport:
	uv run python -m selvra_analysis.report --dagar $(DAGAR) --db $(DB)

## Check daily metrics and glycaemic events against iglu on the demo data (stored reference without R)
validate:
	uv run python -m selvra_analysis.validate_iglu --db $(DEMO_DB)

## The same check on your own data (needs R and iglu)
validate-real:
	uv run python -m selvra_analysis.validate_iglu --db $(DB)

## Checks that need real data, so they never run in CI: is the live data fresh, do all data
## tests and architecture rules pass on it
verify-real: $(DBT_PACKAGES)
	$(DBT) source freshness --profiles-dir . --select source:raw.share_readings
	$(DBT) build --profiles-dir .

## The example study's result, recomputed and compared value by value with the stored one
reproduce:
	uv run python -m selvra_analysis.reproduce --db $(DEMO_DB)

## Worked example of the full analysis workflow, on synthetic data
example:
	uv run python analyses/000-exempel-traning/analys.py --db $(DEMO_DB)

test:
	uv run pytest -q

## Code limits and architecture contracts (the same gates CI runs)
lint: $(DBT_PACKAGES)
	uv run ruff check src tests analyses
	uv run lint-imports
	cd transform && SELVRA_DUCKDB=$(abspath $(DEMO_DB)) uv run sqlfluff lint models tests macros

## Dreamer: generera en studiefil från en naturlig fråga (kräver ANTHROPIC_API_KEY)
## make dreamer                          — interaktivt
## make dreamer fraga="Påverkar stress mitt TIR?"
dreamer:
	uv run python -m selvra_analysis.dreamer $(if $(fraga),--fraga "$(fraga)",)

## Tolka en slutrapport och ge nästa steg: make tolka studie=studies/001-traning-natten-efter/
tolka:
	uv run python -m selvra_analysis.dreamer tolka "$(studie)"

## Syntetisera alla studier till en portfolio-översikt
sammanfattning:
	uv run python -m selvra_analysis.dreamer sammanfattning

## Visa vad Dreamer vet sedan tidigare (studier + lärdomar)
minne:
	uv run python -m selvra_analysis.dreamer minne

## Skanna data efter mönster och föreslå studiefrågor
skanna:
	uv run python -m selvra_analysis.scanner

## Importera händelser från iCal: make import-kalender fil=~/kalender.ics
## Förhandsgranska: make import-kalender fil=~/kalender.ics forhandsgranska=1
import-kalender:
	uv run python -m selvra_analysis.import_kalender "$(fil)" $(if $(forhandsgranska),--forhandsgranska,)

## Autonom loop: hämta data → skanna → tolka → syntetisera
loop:
	uv run python -m selvra_analysis.loop

## Dagbok: visa gårdagens CGM-siffror och logga händelser interaktivt
dagbok:
	uv run python -m selvra_analysis.dagbok

## Logga en händelse: make log start=2026-10-24 typ=traning notering="löpning 5km"
## Typer: alkohol, annat, medicinandring, menstruation, resa, sensorbyte, sjukdom, stress, traning
log:
	uv run python -m selvra_analysis.log_event --start "$(start)" --typ "$(typ)" $(if $(slut),--slut "$(slut)",) $(if $(notering),--notering "$(notering)",)

## Private data-health dashboard (rendered file is git-ignored: it contains health data)
dashboard:
	cd dashboard && SELVRA_DUCKDB=$(abspath $(DB)) uv run quarto render index.qmd
	@echo "Open dashboard/index.html"
