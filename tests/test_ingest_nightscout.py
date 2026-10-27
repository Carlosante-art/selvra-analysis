from selvra_analysis.ingest_nightscout import parse_entries, parse_treatments


def test_only_sgv_entries_become_readings() -> None:
    items = [
        {"type": "sgv", "sgv": 120, "date": 1761523200000, "direction": "Flat", "device": "xDrip"},
        {"type": "mbg", "mbg": 110, "date": 1761523200000},
        {"type": "cal", "date": 1761523200000},
        {"type": "sgv", "sgv": None, "date": 1761523500000},
        {"type": "sgv", "sgv": 95},
    ]
    df = parse_entries(items)
    assert len(df) == 1
    assert df.iloc[0]["value_mgdl"] == 120
    assert df.iloc[0]["trend"] == "Flat"


def test_treatments_without_substance_are_skipped() -> None:
    items = [
        {"eventType": "Meal Bolus", "insulin": 4.5, "carbs": 60, "created_at": "2026-10-26T18:00:00Z"},
        {"eventType": "Correction Bolus", "insulin": 1.0, "created_at": "2026-10-26T21:00:00Z"},
        {"eventType": "Note", "notes": "bara text", "created_at": "2026-10-26T12:00:00Z"},
        {"eventType": "Site Change", "created_at": "2026-10-26T08:00:00Z"},
        {"eventType": "Temp Basal", "absolute": 0.4, "duration": 60, "created_at": "2026-10-26T02:00:00Z"},
    ]
    df = parse_treatments(items)
    assert len(df) == 3
    assert df["insulin_units"].dropna().sum() == 5.5
    assert df["carbs_g"].dropna().sum() == 60
    basal = df[df["event_type"] == "Temp Basal"].iloc[0]
    assert basal["basal_rate"] == 0.4
    assert basal["duration_min"] == 60


def test_treatment_without_timestamp_is_skipped() -> None:
    df = parse_treatments([{"eventType": "Meal Bolus", "insulin": 2.0}])
    assert df.empty
    assert "insulin_units" in df.columns


def test_empty_input_keeps_columns() -> None:
    assert "value_mgdl" in parse_entries([]).columns
    assert "carbs_g" in parse_treatments([]).columns
