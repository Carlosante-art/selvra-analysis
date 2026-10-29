"""Share-diffen: realtidsröret mot efterfyllnadsröret, parat per 5-minutersslot.

Samma sensor, två hämtvägar: Share (realtid, 5 min) och Clarity-exporten
(efterfylld). Diffen svarar på tre frågor ur mätlagret (METODPLAN §6):
hur ofta tappar realtidsröret avläsningar som efterfyllnaden visar fanns,
hur stora är värdeskillnaderna när båda levererar, och när på dygnet sker
tappen (nattens hål är de som väcker anhöriga i onödan).

Viktig avgränsning: till skillnad från klock-jämförelsen finns här ingen
enhetsfil som facit — båda rören är leverantörsprocessade. Diffen mäter
rörens OENIGHET (driftlarm-lagret), aldrig vilket rör som har rätt.

Bara aggregat lämnar skriptet: data/rapporter/share-diff.md (gitignorerat).
Rapporten anger ärligt sitt överlapp; en färsk Clarity-export vidgar det.

    make share-diff
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

DB = Path("data/selvra.duckdb")
UT = Path("data/rapporter/share-diff.md")
MGDL_PER_MMOL = 18.016
SLOT = "300s"              # Dexcoms grid
LIKA_TOLERANS = 0.06       # mmol/L: avrundningsskillnad, inte oenighet


def las_ror(db: Path) -> tuple[pd.Series, pd.Series]:
    """Två serier mmol/L indexerade på 5-minutersslot i lokal tid."""
    with duckdb.connect(str(db), read_only=True) as con:
        share = con.execute(
            "select reading_at, value_mgdl from raw.share_readings order by 1").df()
        clarity = con.execute(
            "select try_cast(ts_raw as timestamp) as reading_at, "
            "try_cast(replace(glucose_raw, ',', '.') as double) as mmol from raw.clarity_events "
            "where event_type = 'EGV' and glucose_unit = 'mmol/L' order by 1").df()
    s = share.dropna()
    s["mmol"] = s["value_mgdl"] / MGDL_PER_MMOL
    s["slot"] = (pd.to_datetime(s["reading_at"], utc=True)
                 .dt.tz_convert("Europe/Stockholm").dt.tz_localize(None).dt.round(SLOT))
    c = clarity.dropna()
    c["slot"] = pd.to_datetime(c["reading_at"]).dt.round(SLOT)
    return (s.groupby("slot")["mmol"].mean(), c.groupby("slot")["mmol"].mean())


def diffa(share: pd.Series, clarity: pd.Series) -> pd.DataFrame:
    """Yttre koppling per slot: båda, bara share, bara clarity — med värdediff."""
    df = pd.concat({"share": share, "clarity": clarity}, axis=1)
    df["kategori"] = "bada"
    df.loc[df["clarity"].isna(), "kategori"] = "bara_share"
    df.loc[df["share"].isna(), "kategori"] = "bara_clarity"   # realtidsröret tappade
    df["diff"] = df["share"] - df["clarity"]
    return df


def _overlapp(df: pd.DataFrame) -> pd.DataFrame:
    """Begränsa till spannet där båda rören över huvud taget levererar —
    utanför det mäter kategorierna bara exportens slutdatum, inte rörens tapp."""
    bada = df[df["kategori"] == "bada"]
    if bada.empty:
        return bada
    return df.loc[bada.index.min():bada.index.max()]


def rapport(df: pd.DataFrame) -> str:
    o = _overlapp(df)
    rader = ["# Share-diffen: realtidsröret mot efterfyllnadsröret", ""]
    if o.empty:
        hint = "Inget överlapp mellan rören ännu — ta en färsk Clarity-export så växer jämförelsen."
        return "\n".join([*rader, hint, ""])
    bada = o[o["kategori"] == "bada"]
    tappade = o[o["kategori"] == "bara_clarity"]
    n = len(bada)
    rader += [
        (f"*Överlapp {o.index.min():%Y-%m-%d %H:%M} – {o.index.max():%H:%M} · "
         f"{n} parade slots*"),
        "",
        "**Rökprov, inte tabell** — överlappet är mindre än ett dygn; en färsk "
        "Clarity-export vidgar det. Ingen av serierna är facit: diffen mäter "
        "rörens oenighet, inte vilket som har rätt." if n < 288 else
        "Ingen av serierna är facit: diffen mäter rörens oenighet, "
        "inte vilket som har rätt.",
        "",
        "| mått | värde |", "|---|---|",
        f"| parade slots (båda levererade) | {n} |",
        f"| slots bara i Clarity (realtidsröret tappade) | {len(tappade)} |",
        f"| slots bara i Share | {len(o[o['kategori'] == 'bara_share'])} |",
        f"| identiska (±{LIKA_TOLERANS} mmol/L) | {(bada['diff'].abs() <= LIKA_TOLERANS).sum()} av {n} |",
        f"| medelabsolutdiff | {bada['diff'].abs().mean():.3f} mmol/L |",
        f"| största absolutdiff | {bada['diff'].abs().max():.2f} mmol/L |",
    ]
    if len(tappade):
        natt = tappade.between_time("00:00", "06:00")
        rader.append(f"| tappade slots nattetid (00–06) | {len(natt)} av {len(tappade)} |")
    rader += ["", "Rådata per slot lämnar aldrig data/ — bara dessa aggregat.", ""]
    return "\n".join(rader)


def main() -> int:
    share, clarity = las_ror(DB)
    df = diffa(share, clarity)
    UT.parent.mkdir(parents=True, exist_ok=True)
    UT.write_text(rapport(df))
    print(f"skrev {UT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
