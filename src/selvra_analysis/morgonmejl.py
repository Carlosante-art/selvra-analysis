"""Morgonmejl till en person: en spegel av gårdagen som blir rikare ju mer Selvra vet om personen.

Steg 1 (spegel)      från första dagen: gårdagens värden mot personens egna dagar hittills
Steg 2 (ditt normala) från 14 dagar med data: personens eget intervall, avvikelser markeras
Steg 3 och 4 (mönster som frågor, egen studie) kommer senare; mejlet säger vad som krävs.

Mejlet beskriver vad apparaten mätte, källattribuerat, och ger aldrig råd. Synkar klockan
inte säger mejlet det först, i stället för att rapportera tomma värden.

Personen beskrivs i data/personer/<namn>/person.yml (gitignored; e-postadressen är privat):

    namn: Kari
    epost: kari@example.com
    kallor: [garmin]

Utskick via SMTP, inställt i .env: SELVRA_SMTP_USER, SELVRA_SMTP_PASSWORD (för Gmail ett
applösenord), valfritt SELVRA_SMTP_HOST (smtp.gmail.com) och SELVRA_SMTP_PORT (587).

    uv run python -m selvra_analysis.morgonmejl pappa            # visa mejlet, skicka inget
    uv run python -m selvra_analysis.morgonmejl pappa --skicka   # hämta ny data och skicka

Genväg i MVP:n: mejlet läser personens Garmin-dagar direkt (raw.garmin_daily), eftersom
datalagret ännu utgår från CGM-dagar och saknar rader för den som inte har CGM.
"""

from __future__ import annotations

import argparse
import os
import smtplib
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from selvra_analysis.ingest_garmin import load as load_garmin
from selvra_analysis.ingest_garmin import person_paths

STAGE2_DAYS = 14          # dagar med data innan personens eget intervall används
BASELINE_DAYS = 28        # det egna normala: de senaste 28 dagarna med data
FETCH_DAYS = 10           # hämtas varje morgon, så sena synkar kommer med
WEEKDAYS = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]


@dataclass
class Measure:
    column: str
    sentence: str        # "{}" is the value, e.g. "Garmin räknade {} steg"
    unit: str            # after a range, e.g. " ms"


MEASURES = [
    Measure("steps", "Garmin räknade {} steg i går", ""),
    Measure("total_sleep_seconds", "Garmin mätte {} sömn i natt", ""),
    Measure("hr_lowest_bpm", "Garmin mätte vilopulsen till {} i går", ""),
    Measure("hrv_avg_ms", "Garmin mätte HRV {} ms i natt", " ms"),
]


def _short(m: Measure, v: float) -> str:
    if m.column == "total_sleep_seconds":
        h, mins = divmod(round(v / 60), 60)
        return f"{h} h {mins:02d} min"
    if m.column == "steps":
        return f"{round(v / 100) * 100:,.0f}".replace(",", " ")
    return f"{v:.0f}"


def read_days(db: Path) -> pd.DataFrame:
    with duckdb.connect(str(db), read_only=True) as con:
        df = con.execute("select * from raw.garmin_daily order by reading_date").df()
    df["reading_date"] = pd.to_datetime(df["reading_date"]).dt.date
    return df


def _sync_line(df: pd.DataFrame, today: date) -> str | None:
    """Warn first when the watch has not synced, so a gap is noticed in days, not months."""
    if df.empty:
        return "Garmin har ingen data från klockan ännu. Öppna Garmin Connect-appen så att klockan synkar."
    latest = df.loc[df["steps"].notna(), "reading_date"].max()
    if pd.isna(latest) or latest < today - timedelta(days=1):
        since = "aldrig" if pd.isna(latest) else f"sedan {latest.day}/{latest.month}"
        return (f"Klockan har inte synkat {since}. Öppna Garmin Connect-appen på telefonen så att "
                "datan inte går förlorad; klockan sparar bara en begränsad tid.")
    return None


def _measure_line(m: Measure, value: float, history: pd.Series, stage2: bool) -> str:
    text = m.sentence.format(_short(m, value))
    if history.empty:
        return text + "."
    if stage2:
        lo, hi = history.quantile(0.1), history.quantile(0.9)
        where = "över" if value > hi else "under" if value < lo else "inom"
        return text + f", {where} ditt vanliga {_short(m, lo)}–{_short(m, hi)}{m.unit}."
    return text + f". Hittills brukar det vara {_short(m, history.median())}{m.unit} ({len(history)} dagar)."


def compose(name: str, df: pd.DataFrame, today: date) -> tuple[str, str]:
    """Subject and body of one morning's mail."""
    yesterday = today - timedelta(days=1)
    n_days = int(df["steps"].notna().sum()) if not df.empty else 0
    lines = [f"God morgon {name},", ""]
    warn = _sync_line(df, today)
    if warn:
        lines += [warn, ""]
    shown = 0
    for m in MEASURES:
        # Sleep and HRV belong to the night that ended this morning; steps and pulse to yesterday.
        day = today if m.column in ("total_sleep_seconds", "hrv_avg_ms") else yesterday
        row = df[df["reading_date"] == day]
        if row.empty or pd.isna(row[m.column].iloc[0]):
            continue
        # The person's last BASELINE_DAYS days *with data*: a sync gap must not empty the baseline.
        hist = df.loc[df["reading_date"] < day, m.column].dropna().tail(BASELINE_DAYS)
        lines.append("- " + _measure_line(m, float(row[m.column].iloc[0]), hist, len(hist) >= STAGE2_DAYS))
        shown += 1
    if not shown:
        lines.append("Inga nya värden från klockan för i går och i natt ännu.")
    lines += ["", _stage_footer(n_days), "", "Selvra"]
    subject = f"Selvra {WEEKDAYS[today.weekday()]} {today.day}/{today.month}" + (" – klockan har inte synkat" if warn else "")
    return subject, "\n".join(lines) + "\n"


def _stage_footer(n_days: int) -> str:
    if n_days < STAGE2_DAYS:
        return (f"Selvra har {n_days} dagar med data från dig. Vid {STAGE2_DAYS} dagar lär den sig ditt eget "
                "normala intervall för varje mått, i stället för att bara jämföra med snittet hittills.")
    return (f"Selvra har {n_days} dagar med data från dig och jämför med ditt eget normala. Om några veckor "
            "kan den föreslå en fråga om dig själv som går att pröva.")


def send(to: str, subject: str, body: str) -> None:
    user, password = os.environ.get("SELVRA_SMTP_USER"), os.environ.get("SELVRA_SMTP_PASSWORD")
    if not user or not password:
        raise SystemExit("SELVRA_SMTP_USER och SELVRA_SMTP_PASSWORD saknas i .env")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = f"Selvra <{user}>", to, subject
    msg.set_content(body)
    host = os.environ.get("SELVRA_SMTP_HOST", "smtp.gmail.com")
    with smtplib.SMTP(host, int(os.environ.get("SELVRA_SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)


def _load_dotenv() -> None:
    env = Path(".env")
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        key, sep, val = line.strip().partition("=")
        if sep and key.startswith("SELVRA_SMTP_") and key not in os.environ:
            os.environ[key.strip()] = val.strip().strip('"').strip("'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("person")
    parser.add_argument("--skicka", action="store_true", help="hämta ny data och skicka mejlet")
    args = parser.parse_args(argv)
    paths = person_paths(args.person)
    conf_path = paths["db"].parent / "person.yml"
    if not conf_path.exists():
        raise SystemExit(f"{conf_path} saknas (namn, epost, kallor)")
    conf = yaml.safe_load(conf_path.read_text())
    if args.skicka:
        load_garmin(paths["db"], FETCH_DAYS, paths["token"], paths["snapshots"])
    subject, body = compose(conf["namn"], read_days(paths["db"]), date.today())
    if args.skicka:
        _load_dotenv()
        send(conf["epost"], subject, body)
        print(f"Skickat till {conf['epost']}: {subject}", file=sys.stderr)
    else:
        print(f"Ämne: {subject}\n\n{body}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
