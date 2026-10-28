"""API-jämförelsen: klockans FIT-filer är facit, API:erna är de åtalade.

Frågan validitetslagret vilar på: vad tappas eller förvanskas mellan klockan
och ett API-svar? Facit är FIT-filerna från egen klocka (egen data, läst via
USB → data/fit/, gitignorerad). Jämförelsen diffar dagliga aggregat fält för
fält mot garminconnect (och Terra när konto finns): steg, sömn per stadium,
vilopuls, HRV — plus det lömska: tidszoner och dagsgränser (en natt som slutar
07:10 — vilken dag tillhör den, enligt vem?).

Bara aggregat lämnar skriptet; inga rådata i repot. Utdata:
data/rapporter/api-jamforelse.md (gitignorerat som allt under data/).

    make api-jamforelse                 # FIT mot garminconnect (person: carl)
    ... --terra-json data/terra.json    # + Terra, ur en exporterad dump

Ärlighetsnoter, tills riktiga filer setts (klockan kommer 2026-10-30):
- Stegen i monitoring-FIT är kumulativa per aktivitetstyp; dagssumman är
  summan av max per typ. Verifieras mot klockans egen display första dagen.
- "Vilopuls" har olika definitioner per källa; när FIT saknar uttryckligt
  resting_heart_rate rapporteras min(samples) och MÄRKS som sådan — skillnaden
  är ett fynd, inte ett fel i skriptet.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import fitdecode
import pandas as pd

from selvra_analysis.ingest_garmin import _login_with_token, parse_day, person_paths

FIT_DIR = Path("data/fit")
UT = Path("data/rapporter/api-jamforelse.md")
FALT = ["steps", "total_sleep_seconds", "deep_sleep_seconds", "rem_sleep_seconds",
        "hr_lowest_bpm", "hrv_avg_ms"]
GARMIN_EPOCH = datetime(1989, 12, 31)


def _fit_tid(v) -> datetime | None:
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, int):
        return GARMIN_EPOCH + timedelta(seconds=v)
    return None


class _Ack:
    """Ackumulator för dagliga aggregat under FIT-läsningen."""

    def __init__(self) -> None:
        self.steg_max: dict[tuple[date, int], int] = defaultdict(int)
        self.somn: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.puls_min: dict[date, int] = {}
        self.rhr: dict[date, int] = {}
        self.hrv: dict[date, float] = {}
        self.offset_sek: set[int] = set()
        self.noter: list[str] = []


def _ta_monitoring(a: _Ack, f: dict, dag: date) -> None:
    if isinstance(f.get("steps"), int):
        typ = int(f.get("activity_type") or 0)
        a.steg_max[(dag, typ)] = max(a.steg_max[(dag, typ)], f["steps"])
    if isinstance(f.get("heart_rate"), int) and f["heart_rate"] > 0:
        a.puls_min[dag] = min(a.puls_min.get(dag, 300), f["heart_rate"])


def _ta_somn(a: _Ack, f: dict, ts: datetime) -> None:
    # nivåer per Garmin: 1 vaken, 2 lätt, 3 djup, 4 REM; natten tillhör
    # uppvakningsdagen — dagsgränsregeln är låst i test_api_jamforelse
    niva = f.get("sleep_level")
    dag = ts.date() if ts.hour < 12 else (ts + timedelta(days=1)).date()
    if niva in (2, 3, 4):
        a.somn[dag]["total_sleep_seconds"] += 60
    namn = {3: "deep_sleep_seconds", 4: "rem_sleep_seconds"}.get(niva)
    if namn:
        a.somn[dag][namn] += 60


def _ta_frame(a: _Ack, frame) -> None:
    f = {x.name: x.value for x in frame.fields}
    ts, lokal = _fit_tid(f.get("timestamp")), _fit_tid(f.get("local_timestamp"))
    if ts and lokal:
        a.offset_sek.add(int((lokal - ts).total_seconds()))
    if not ts:
        return
    dag = (lokal or ts).date()
    if frame.name == "monitoring":
        _ta_monitoring(a, f, dag)
    elif frame.name == "monitoring_info" and isinstance(f.get("resting_heart_rate"), int):
        a.rhr[dag] = f["resting_heart_rate"]
    elif frame.name == "sleep_level":
        _ta_somn(a, f, ts)
    elif frame.name in ("hrv_status_summary", "hrv_summary"):
        v = f.get("last_night_average") or f.get("weekly_average")
        if v:
            a.hrv[dag] = float(v)


def _las_fil(a: _Ack, fil: Path) -> None:
    try:
        with fitdecode.FitReader(fil) as fr:
            for frame in fr:
                if isinstance(frame, fitdecode.FitDataMessage):
                    _ta_frame(a, frame)
    except Exception as err:  # noqa: BLE001 — en trasig fil fäller inte jämförelsen
        a.noter.append(f"{fil.name}: kunde inte läsas ({err})")


def las_fit_mapp(mapp: Path) -> tuple[pd.DataFrame, list[str]]:
    """Dagliga aggregat ur alla FIT-filer i mappen, plus noter om vad som saknades."""
    a = _Ack()
    filer = sorted(mapp.glob("**/*.[fF][iI][tT]"))
    if not filer:
        a.noter.append(f"inga FIT-filer i {mapp} — lägg klockans GARMIN/Monitor + Sleep där")
    for fil in filer:
        _las_fil(a, fil)

    dagssteg: dict[date, int] = defaultdict(int)
    for (d, _typ), v in a.steg_max.items():
        dagssteg[d] += v
    dagar = sorted(set(dagssteg) | set(a.somn) | set(a.puls_min) | set(a.rhr) | set(a.hrv))
    rader = [{
        "reading_date": d,
        "steps": dagssteg.get(d),
        "total_sleep_seconds": a.somn[d].get("total_sleep_seconds") or None,
        "deep_sleep_seconds": a.somn[d].get("deep_sleep_seconds") or None,
        "rem_sleep_seconds": a.somn[d].get("rem_sleep_seconds") or None,
        "hr_lowest_bpm": a.rhr.get(d, a.puls_min.get(d)),
        "hrv_avg_ms": a.hrv.get(d),
    } for d in dagar]
    a.noter += [f"{d}: FIT saknar resting_heart_rate; min(samples)={a.puls_min[d]} används, märkt"
                for d in dagar if d in a.puls_min and d not in a.rhr]
    if a.offset_sek:
        a.noter.append("FIT lokal UTC-offset: "
                       + ", ".join(f"{s / 3600:+.0f} h" for s in sorted(a.offset_sek)))
    return pd.DataFrame(rader), a.noter


def las_garminconnect(person: str, dagar: list[date]) -> pd.DataFrame:
    g = _login_with_token(person_paths(person)["token"])
    return pd.DataFrame([parse_day(g, str(d)) | {"reading_date": d} for d in dagar])


def las_terra_json(fil: Path) -> pd.DataFrame:
    """Terra-dump (exporterad för hand) → samma kolumnnamn. Mappningen fylls på
    när ett konto finns; tills dess accepteras redan-harmoniserad JSON."""
    rader = json.loads(fil.read_text())
    df = pd.DataFrame(rader)
    df["reading_date"] = pd.to_datetime(df["reading_date"]).dt.date
    return df


def diffa(facit: pd.DataFrame, kallor: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """En rad per dag × fält: facit, varje källas värde och avvikelse."""
    rader = []
    for _, fr in facit.iterrows():
        d = fr["reading_date"]
        for falt in FALT:
            rad = {"datum": d, "falt": falt, "fit": fr.get(falt)}
            for namn, df in kallor.items():
                tr = df[df["reading_date"] == d]
                v = tr[falt].iloc[0] if (not tr.empty and falt in tr) else None
                rad[namn] = v
                rad[f"{namn}_diff"] = (
                    None if v is None or pd.isna(v) or rad["fit"] is None or pd.isna(rad["fit"])
                    else float(v) - float(rad["fit"]))
            rader.append(rad)
    return pd.DataFrame(rader)


def rapport(diff: pd.DataFrame, noter: list[str], kallor: list[str]) -> str:
    rader = ["# API-jämförelse: FIT-facit mot API-svar", "",
             (f"*{diff['datum'].nunique()} dagar · källor: {', '.join(kallor)} · "
              "bara aggregat — rådatan bor i data/fit/ (gitignorerad)*"), ""]
    for falt in FALT:
        f = diff[diff["falt"] == falt]
        rader += [f"## {falt}", "", "| datum | FIT (facit) | " + " | ".join(
            f"{k} | diff" for k in kallor) + " |",
            "|---|---|" + "---|---|" * len(kallor)]
        for _, r in f.iterrows():
            celler = [str(r["datum"]), _c(r["fit"])]
            for k in kallor:
                celler += [_c(r[k]), _c(r.get(f"{k}_diff"))]
            rader.append("| " + " | ".join(celler) + " |")
        rader.append("")
    if noter:
        rader += ["## Noter (definitioner, saknade fält, tidszoner)", ""]
        rader += [f"- {n}" for n in noter]
    return "\n".join(rader) + "\n"


def _c(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{v:+.0f}" if isinstance(v, float) else str(v)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--person", default="carl")
    p.add_argument("--fit", type=Path, default=FIT_DIR)
    p.add_argument("--terra-json", type=Path, default=None)
    p.add_argument("--dagar", type=int, default=14)
    args = p.parse_args(argv)

    facit, noter = las_fit_mapp(args.fit)
    if facit.empty:
        print("\n".join(noter), file=sys.stderr)
        return 1
    dagar = sorted(facit["reading_date"])[-args.dagar:]
    facit = facit[facit["reading_date"].isin(dagar)]

    kallor = {"garminconnect": las_garminconnect(args.person, dagar)}
    if args.terra_json:
        kallor["terra"] = las_terra_json(args.terra_json)

    diff = diffa(facit, kallor)
    UT.parent.mkdir(parents=True, exist_ok=True)
    UT.write_text(rapport(diff, noter, list(kallor)))
    print(f"skrev {UT} ({len(dagar)} dagar)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
