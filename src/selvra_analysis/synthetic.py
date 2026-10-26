"""Generate synthetic CGM data in Dexcom Clarity export format.

Used for the public demo and for CI, so the pipeline can be shown and tested
without any personal health data.

The generator reproduces the *artefacts* real data has (sensor changes with
warm-up gaps, a less accurate first day, nightly compression lows, signal
loss, Low/High values out of range, overlapping exports). It deliberately
does NOT encode any answer to the analyses in this repository: high-glucose
streaks are followed by ordinary days. A pipeline tested on data that already
contains the expected finding proves nothing.

Time works as on a real receiver: readings are every 5 minutes of real time,
exported as local wall-clock time in Europe/Stockholm. The default year
therefore contains both daylight-saving changes, including the autumn hour
that appears twice in the export.

Usage:
    python -m selvra_analysis.synthetic data/sample --days 365 --seed 7
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

STEP = timedelta(minutes=5)
TZ = "Europe/Stockholm"
LOW_LIMIT, HIGH_LIMIT = 2.2, 22.2

HEADER = [
    "Index",
    "Timestamp (YYYY-MM-DDThh:mm:ss)",
    "Event Type",
    "Event Subtype",
    "Patient Info",
    "Device Info",
    "Source Device ID",
    "Glucose Value (mmol/L)",
    "Insulin Value (u)",
    "Carb Value (grams)",
    "Duration (hh:mm:ss)",
    "Glucose Rate of Change (mmol/L/min)",
    "Transmitter Time (Long Integer)",
    "Transmitter ID",
]


def _meal_curve(minutes_since: np.ndarray, peak: float) -> np.ndarray:
    """Gamma-shaped glucose rise after a meal, peaking around 60 minutes."""
    t = np.clip(minutes_since, 0, None) / 60.0
    return peak * t * np.exp(1 - t) * (minutes_since >= 0)


def generate(
    days: int, start: datetime, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (glucose readings, meal events, personal event log) for `days` days."""
    rng = np.random.default_rng(seed)
    n = days * 288
    # Real time runs in UTC; the receiver shows local wall-clock time.
    utc = pd.date_range(pd.Timestamp(start).tz_localize(TZ), periods=n, freq="5min").tz_convert("UTC")
    ts = utc.tz_convert(TZ).tz_localize(None)
    minute_of_day = (ts.hour * 60 + ts.minute).to_numpy()
    day_idx = (ts.normalize() - pd.Timestamp(start)).days.to_numpy()
    local_minute = ((ts - pd.Timestamp(start)).total_seconds() / 60).to_numpy()

    glucose = np.full(n, 7.2)
    glucose += 1.0 * np.exp(-(((minute_of_day - 390) / 60.0) ** 2))  # dawn phenomenon

    log: list[tuple[str, str, str, str]] = []

    def day(d: int) -> str:
        return (start + timedelta(days=int(d))).strftime("%Y-%m-%d")

    meals = []
    for d in range(days):
        for base_min, carbs in ((450, 50), (750, 70), (1110, 80)):
            meal_min = base_min + int(rng.normal(0, 25))
            peak = rng.uniform(2.0, 7.0)
            since = local_minute - (d * 1440 + meal_min)
            glucose += _meal_curve(since.astype(float), peak) * (since < 300)
            meals.append((start + timedelta(days=d, minutes=meal_min), int(carbs * rng.uniform(0.7, 1.3))))

    # Slow-moving noise (AR(1)) plus sensor noise
    ar = np.zeros(n)
    eps = rng.normal(0, 0.12, n)
    for i in range(1, n):
        ar[i] = 0.97 * ar[i - 1] + eps[i]
    glucose += ar + rng.normal(0, 0.15, n)

    # Multi-day high streaks (illness, insulin issues). No effect is added afterwards.
    for _ in range(max(1, days // 30)):
        d0 = rng.integers(5, days - 6)
        length = rng.integers(3, 5)
        mask = (day_idx >= d0) & (day_idx < d0 + length)
        glucose[mask] += rng.uniform(2.5, 4.0)
        # Some streaks have a logged cause, some do not: as in real life
        if rng.random() < 0.6:
            log.append((day(d0), day(d0 + length - 1), "sjukdom", "förkyld (syntetisk)"))

    # Real hypoglycaemia, about one every four days
    for _ in range(days // 4):
        i0 = rng.integers(0, n - 24)
        depth = glucose[i0] - rng.uniform(3.0, 3.7)
        glucose[i0 : i0 + 12] -= depth * np.sin(np.linspace(0, np.pi, 12))

    # Sensors: 10 days each, 30 min warm-up gap, noisier and biased first 24 h
    sensor_id = np.empty(n, dtype=object)
    transmitter_time = np.zeros(n, dtype=np.int64)
    keep = np.ones(n, dtype=bool)
    sensor_len = 10 * 288
    for k, s0 in enumerate(range(0, n, sensor_len)):
        sensor_id[s0 : s0 + sensor_len] = f"SYN{k:04d}"
        transmitter_time[s0 : s0 + sensor_len] = np.arange(len(transmitter_time[s0 : s0 + sensor_len])) * 300
        if k > 0 and rng.random() < 0.8:  # sensor changes are sometimes forgotten in the log
            log.append((day(s0 // 288), "", "sensorbyte", ""))
        keep[s0 : s0 + 6] = False
        first_day = slice(s0 + 6, min(s0 + 288, n))
        glucose[first_day] += 0.5 + rng.normal(0, 0.4, len(glucose[first_day]))

    # Compression lows: sharp nightly dips that recover within ~30 min, 02:00-05:00 local
    night = np.flatnonzero((ts.hour >= 2) & (ts.hour < 5))
    for _ in range(days // 7):
        d = rng.integers(0, days)
        candidates = night[day_idx[night] == d]
        if len(candidates) == 0:
            continue
        i0 = int(rng.choice(candidates))
        if i0 + 8 < n:
            target = rng.uniform(2.4, 3.2)
            glucose[i0 : i0 + 6] = np.linspace(glucose[i0], target, 6)
            glucose[i0 + 6 : i0 + 8] = target

    # Signal loss: a few gaps per month of 20-90 minutes
    for _ in range(days // 10):
        i0 = rng.integers(0, n - 20)
        keep[i0 : i0 + rng.integers(4, 18)] = False

    # Everyday context with no glucose effect built in
    for d in range(days):
        if rng.random() < 0.08:
            log.append((day(d), "", "alkohol", ""))
        if rng.random() < 0.3:
            log.append((day(d), "", "traning", "promenad 40 min"))

    readings = pd.DataFrame(
        {"ts": ts, "glucose": glucose, "sensor": sensor_id, "transmitter_time": transmitter_time}
    )[keep]
    meal_events = pd.DataFrame(meals, columns=["ts", "carbs"])
    event_log = pd.DataFrame(log, columns=["start", "slut", "typ", "notering"]).sort_values("start")
    return readings, meal_events, event_log


def _format_glucose(v: float) -> str:
    if v < LOW_LIMIT:
        return "Low"
    if v > HIGH_LIMIT:
        return "High"
    return f"{v:.1f}"


def to_clarity(readings: pd.DataFrame, meals: pd.DataFrame) -> pd.DataFrame:
    rows = [
        ["", "", "FirstName", "", "Synthetic", "", "", "", "", "", "", "", "", ""],
        ["", "", "LastName", "", "Person", "", "", "", "", "", "", "", "", ""],
        ["", "", "Device", "", "", "Dexcom G7 (synthetic)", "SYNTHETIC", "", "", "", "", "", "", ""],
    ]
    for r in readings.itertuples():
        rows.append(
            ["", r.ts.strftime("%Y-%m-%dT%H:%M:%S"), "EGV", "", "", "", "SYNTHETIC",
             _format_glucose(r.glucose), "", "", "", "", str(r.transmitter_time), r.sensor]
        )
    for m in meals.itertuples():
        rows.append(
            ["", m.ts.strftime("%Y-%m-%dT%H:%M:%S"), "Carbs", "", "", "", "SYNTHETIC",
             "", "", str(m.carbs), "", "", "", ""]
        )
    df = pd.DataFrame(rows, columns=HEADER)
    df["Index"] = range(1, len(df) + 1)
    return df


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--start", default="2025-01-01")
    args = parser.parse_args(argv)

    start = datetime.fromisoformat(args.start)
    readings, meals, event_log = generate(args.days, start, args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Two exports that overlap by ten days, as happens when you export twice.
    split = start + timedelta(days=args.days // 2)
    overlap = timedelta(days=10)
    parts = {
        "clarity_synthetic_part1.csv": (readings.ts < split + overlap, meals.ts < split + overlap),
        "clarity_synthetic_part2.csv": (readings.ts >= split - overlap, meals.ts >= split - overlap),
    }
    for name, (r_mask, m_mask) in parts.items():
        to_clarity(readings[r_mask], meals[m_mask]).to_csv(args.out_dir / name, index=False)
        print(f"Wrote {args.out_dir / name}")
    event_log.to_csv(args.out_dir / "handelser.csv", index=False)
    print(f"Wrote {args.out_dir / 'handelser.csv'}")


if __name__ == "__main__":
    main()
