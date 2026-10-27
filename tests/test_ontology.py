"""Ontology gate: every column in the marts says what it measures and what it does not.

The marts are where claims come from. Each column must carry a registry entry in its dbt
`meta`, and the registry must match the columns the models actually produce. Agreement
with iglu proves the computation; this registry states the construct. Matching a
reference implementation does not show that a number measures what we claim.
"""

from pathlib import Path

import duckdb
import pytest
import yaml

ROOT = Path(__file__).parents[1]
MARTS = ["fct_glucose_daily", "fct_day_context", "mart_analysis_days"]
REQUIRED = ["construct", "source_standard", "valid_range", "iglu_function", "does_not_measure", "epistemics"]
EPISTEMICS = {"observed", "derived", "interpreted", "self-reported"}


@pytest.fixture(scope="module")
def registry() -> dict:
    doc = yaml.safe_load((ROOT / "transform" / "models" / "marts" / "_marts.yml").read_text())
    return {m["name"]: m for m in doc["models"]}


def test_every_mart_column_has_a_complete_registry_entry(registry: dict) -> None:
    problems = []
    for name in MARTS:
        model = registry[name]
        assert model["config"]["contract"]["enforced"], f"{name}: contract must be enforced"
        for col in model["columns"]:
            meta = col.get("meta") or {}
            missing = [k for k in REQUIRED if k not in meta]
            if not col.get("description"):
                missing.append("description")
            if meta.get("epistemics") not in EPISTEMICS:
                missing.append(f"epistemics in {sorted(EPISTEMICS)}")
            if not str(meta.get("does_not_measure") or "").strip():
                missing.append("does_not_measure (non-empty)")
            if missing:
                problems.append(f"{name}.{col['name']}: {', '.join(missing)}")
    assert not problems, "\n".join(problems)


def test_registry_matches_the_columns_the_models_produce(registry: dict) -> None:
    """The contract makes dbt fail on a mismatch at build time; this checks the same in the
    demo database, so a column cannot exist without an entry."""
    db = ROOT / "data" / "demo.duckdb"
    if not db.exists():
        pytest.skip("run `make demo` first")
    with duckdb.connect(str(db), read_only=True) as con:
        for name in MARTS:
            built = {r[0] for r in con.execute(
                "select column_name from information_schema.columns "
                "where table_schema = 'marts' and table_name = ?", [name]).fetchall()}
            documented = {c["name"] for c in registry[name]["columns"]}
            assert built == documented, f"{name}: built-only {built - documented}, registry-only {documented - built}"


def test_datasheet_has_the_required_sections() -> None:
    text = (ROOT / "DATASHEET.md").read_text()
    for section in ("Motivation", "Composition", "Collection", "Preprocessing", "Uses",
                    "Distribution", "Maintenance"):
        assert f"## {section}" in text, f"DATASHEET.md lacks ## {section}"
