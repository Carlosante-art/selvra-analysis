from selvra_analysis.ingest_oura import parse


def test_measured_values_come_from_sleep_periods_not_contributor_scores() -> None:
    """Oura's `contributors` are 1-100 sub-scores. A contributor score of 85 must never end up
    as 85 seconds of sleep or 85 ms of HRV."""
    daily_sleep = [{"day": "2026-10-20", "score": 81,
                    "contributors": {"total_sleep": 85, "deep_sleep": 90, "rem_sleep": 70}}]
    daily_readiness = [{"day": "2026-10-20", "score": 77,
                        "contributors": {"hrv_balance": 60, "resting_heart_rate": 95}}]
    periods = [
        {"day": "2026-10-20", "type": "late_nap", "total_sleep_duration": 1800,
         "average_hrv": 30, "lowest_heart_rate": 60},
        {"day": "2026-10-20", "type": "long_sleep", "total_sleep_duration": 26100,
         "deep_sleep_duration": 5400, "rem_sleep_duration": 6000, "efficiency": 91,
         "average_hrv": 48, "lowest_heart_rate": 52},
    ]
    row = parse(daily_sleep, daily_readiness, periods).iloc[0]
    assert (row["sleep_score"], row["readiness_score"]) == (81, 77)
    assert row["total_sleep_seconds"] == 26100, "the main (longest) period, not the nap"
    assert (row["hrv_avg_ms"], row["hr_lowest_bpm"]) == (48, 52)
    assert row["sleep_efficiency_pct"] == 91


def test_days_without_any_data_are_absent() -> None:
    df = parse([], [], [])
    assert df.empty
    assert "hrv_avg_ms" in df.columns
