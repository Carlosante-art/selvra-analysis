from selvra_analysis.ingest_garmin import parse_day, to_frame


def test_each_value_comes_from_the_endpoint_that_holds_it() -> None:
    """Sleep score from sleepScores.overall, durations from the DTO, HRV from the HRV
    summary, resting HR and steps from the user summary — never mixed up."""
    sleep = {"dailySleepDTO": {"sleepTimeSeconds": 25200, "deepSleepSeconds": 5400,
                               "remSleepSeconds": 6300, "sleepScores": {"overall": {"value": 82}}}}
    summary = {"totalSteps": 11450, "restingHeartRate": 47}
    hrv = {"hrvSummary": {"lastNightAvg": 52}}
    row = parse_day("2026-10-26", sleep, summary, hrv)
    assert row["sleep_score"] == 82
    assert row["total_sleep_seconds"] == 25200
    assert (row["deep_sleep_seconds"], row["rem_sleep_seconds"]) == (5400, 6300)
    assert row["hrv_avg_ms"] == 52
    assert row["hr_lowest_bpm"] == 47
    assert row["steps"] == 11450


def test_garmin_has_no_readiness_or_efficiency() -> None:
    """Garmin lacks Oura's readiness and efficiency measures; a different measure under
    the same name would be wrong, so they stay null."""
    row = parse_day("2026-10-26", {"dailySleepDTO": {"sleepTimeSeconds": 20000}}, {}, {})
    assert row["readiness_score"] is None
    assert row["sleep_efficiency_pct"] is None


def test_missing_endpoints_give_nulls_not_errors() -> None:
    row = parse_day("2026-10-26", None, None, None)
    assert row["reading_date"] == "2026-10-26"
    assert row["sleep_score"] is None
    assert row["steps"] is None


def test_days_without_any_data_are_absent() -> None:
    rows = [parse_day("2026-10-25", None, None, None),
            parse_day("2026-10-26", None, {"totalSteps": 9000}, None)]
    df = to_frame(rows)
    assert len(df) == 1
    assert df.iloc[0]["reading_date"] == "2026-10-26"
    assert "hrv_avg_ms" in df.columns


def test_empty_input_keeps_the_columns() -> None:
    df = to_frame([])
    assert df.empty
    assert "steps" in df.columns
