"""Motortest: falsk-fynd-frekvens och detektionsgrad för hela beslutskedjan, på riktig data.

Granskningsbenchmarken testar designgranskningen. Det här testar själva domslutet:
samma blockbootstrap och samma låsta beslutsregel som studiemotorn använder
(stats.block_bootstrap_difference + study.decide — ingen kopia), körda på din
riktiga CGM-historik där sanningen är känd därför att vi själva skapat den:

  placebo     exponeringsdatum lottas om — sanningen är "ingen effekt".
              Falskt fynd = "tesen håller". Att nollan "motbevisas" (intervallet
              visar mindre än minsta relevanta effekt) är ett korrekt friande.
  planterat   en känd sänkning läggs på nätterna efter lottade datum.
              Andelen "tesen håller" är detektionsgraden.

Utfallet är studie 001:s: nattmedel 00–06, exponering kvällen före (dagar_efter 1),
minsta relevanta effekt −0,5 mmol/L, blockbootstrap med 7-dagarsblock, 95 %.

LLM-armen ger samma dagstabeller till en språkmodell och frågar om den ser en
effekt — jämförelsen bakom rubriken "AI hittade mönster i ren slumpdata".

Usage:
    uv run python -m selvra_analysis.motortest            # kod-armen
    uv run python -m selvra_analysis.motortest llm        # kräver ANTHROPIC_API_KEY
    make motortest / make motortest-llm
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import anthropic
import duckdb
import numpy as np
import pandas as pd

from selvra_analysis.dreamer import _load_dotenv
from selvra_analysis.stats import block_bootstrap_difference
from selvra_analysis.study import decide

DB_DEFAULT = Path("data/selvra.duckdb")
UT_DIR = Path("benchmark/resultat")

FONSTER_KRAV = 50          # minst 50 av 72 nattvärden (≈70 %) för giltig natt
MINSTA_EFFEKT = -0.5       # studie 001:s låsta regel
BLOCK = 7
NIVA = 0.95
EXPONERINGAR = (5, 10, 15)
DELTOR = (0.5, 1.0, 1.5)
LLM_MODELL = "claude-opus-5-5"


def natt_serie(db_path: Path) -> pd.Series:
    """Nattmedel 00–06 per datum ur riktiga avläsningar; NaN när täckningen inte räcker."""
    with duckdb.connect(str(db_path), read_only=True) as con:
        df = con.execute(
            "select reading_date, avg(glucose_mmol) as natt, count(*) as n "
            "from intermediate.int_cgm_readings "
            "where extract(hour from reading_at_local) < 6 "
            "group by reading_date order by reading_date").df()
    df.loc[df["n"] < FONSTER_KRAV, "natt"] = np.nan
    s = df.set_index(pd.to_datetime(df["reading_date"]))["natt"]
    return s.asfreq("D")


def _exponering(serie: pd.Series, datum: list[pd.Timestamp]) -> pd.Series:
    """Exponerad natt = kvällen före var ett exponeringsdatum (dagar_efter 1)."""
    e = pd.Series(False, index=serie.index, dtype=object)
    for d in datum:
        natt = d + pd.Timedelta(days=1)
        if natt in e.index:
            e[natt] = True
    return e


def _dom(serie: pd.Series, datum: list[pd.Timestamp], seed: int) -> tuple[str, float]:
    est = block_bootstrap_difference(serie, _exponering(serie, datum),
                                     block_length=BLOCK, seed=seed, level=NIVA).as_dict()
    kort = decide(est, MINSTA_EFFEKT).split(":")[0].strip()
    return kort, est["estimate"]


def _mojliga_datum(serie: pd.Series) -> list[pd.Timestamp]:
    """Datum vars följande natt har giltigt utfall — de kan bära en exponering."""
    return [d - pd.Timedelta(days=1) for d in serie.dropna().index
            if (d - pd.Timedelta(days=1)) in serie.index]


def kor_arm(serie: pd.Series, reps: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    kandidater = _mojliga_datum(serie)
    ut: dict = {"placebo": {}, "planterat": {}}

    for n_exp in EXPONERINGAR:
        domar = []
        for i in range(reps):
            datum = list(rng.choice(kandidater, size=n_exp, replace=False))
            domar.append(_dom(serie, datum, seed=1000 + i)[0])
        ut["placebo"][n_exp] = {d: domar.count(d) for d in set(domar)} | {"reps": reps}

    for delta in DELTOR:
        for n_exp in EXPONERINGAR:
            traffar = 0
            for i in range(reps):
                datum = list(rng.choice(kandidater, size=n_exp, replace=False))
                planterad = serie.copy()
                for d in datum:
                    planterad[d + pd.Timedelta(days=1)] -= delta
                if _dom(planterad, datum, seed=2000 + i)[0] == "tesen håller":
                    traffar += 1
            ut["planterat"][f"{delta}|{n_exp}"] = {"traffar": traffar, "reps": reps}
    return ut


def _tabell(serie: pd.Series, datum: list[pd.Timestamp]) -> str:
    rader = ["datum       natt_mmol  handelse_kvallen_fore"]
    dset = {d + pd.Timedelta(days=1) for d in datum}
    for d, v in serie.dropna().items():
        rader.append(f"{d.date()}  {v:9.1f}  {'JA' if d in dset else 'nej'}")
    return "\n".join(rader)


def kor_llm(serie: pd.Series, reps: int, seed: int) -> dict:
    client = anthropic.Anthropic()
    rng = np.random.default_rng(seed)
    kandidater = _mojliga_datum(serie)
    system = ("Du är en noggrann dataanalytiker. Du får nattmedelvärden (mmol/L) per datum och "
              "en markering om en viss händelse inträffade kvällen före. Avgör om händelsen "
              "sänker nattmedel med minst 0,5 mmol/L. Svara med exakt en rad JSON: "
              '{"effekt_funnen": true/false, "skattning_mmol": tal}')

    def fraga(s: pd.Series, datum: list[pd.Timestamp]) -> bool:
        msg = client.messages.create(model=LLM_MODELL, max_tokens=2000, system=system,
                                     messages=[{"role": "user", "content": _tabell(s, datum)}])
        text = " ".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        try:
            return bool(json.loads(text[text.index("{"):text.rindex("}") + 1])["effekt_funnen"])
        except (ValueError, KeyError):
            return "true" in text.lower()

    ut = {"modell": LLM_MODELL, "placebo": 0, "planterat": 0, "reps": reps}
    for i in range(reps):
        datum = list(rng.choice(kandidater, size=10, replace=False))
        if fraga(serie, datum):
            ut["placebo"] += 1
        planterad = serie.copy()
        for d in datum:
            planterad[d + pd.Timedelta(days=1)] -= 1.0
        if fraga(planterad, datum):
            ut["planterat"] += 1
        print(f"  llm {i + 1}/{reps}: placebo-fynd {ut['placebo']}, "
              f"planterade fynd {ut['planterat']}", file=sys.stderr)
    return ut


def _skriv(arm: str, resultat: dict, reps: int, seed: int, n_dagar: int) -> Path:
    UT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S%z")
    ut = UT_DIR / f"motortest-{stamp}-{arm}.json"
    ut.write_text(json.dumps({"arm": arm, "reps": reps, "seed": seed,
                              "giltiga_natter": n_dagar, "utfall": "natt 00-06",
                              "minsta_effekt": MINSTA_EFFEKT, "resultat": resultat},
                             indent=2, ensure_ascii=False) + "\n")
    return ut


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("arm", nargs="?", choices=["kod", "llm"], default="kod")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    parser.add_argument("--reps", type=int, default=None)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)

    serie = natt_serie(args.db)
    n = int(serie.notna().sum())
    print(f"{n} giltiga nätter i serien.", file=sys.stderr)

    if args.arm == "llm":
        _load_dotenv()
        reps = args.reps or 20
        resultat = kor_llm(serie, reps, args.seed)
        print(f"\nLLM ({resultat['modell']}): {resultat['placebo']}/{reps} fynd i ren slumpdata, "
              f"{resultat['planterat']}/{reps} fynd av planterad −1,0 mmol/L (10 nätter).")
    else:
        reps = args.reps or 200
        resultat = kor_arm(serie, reps, args.seed)
        print("\nPlacebo (omblandade exponeringar — falskt fynd = 'håller'; 'motbevisad' är korrekt friande):")
        for n_exp in EXPONERINGAR:
            r = resultat["placebo"][n_exp]
            hall = r.get("tesen håller", 0)
            mot = r.get("tesen motbevisad", 0)
            print(f"  {n_exp:>2} exponeringar: håller {hall}/{reps}, motbevisad {mot}/{reps}, "
                  f"obestämt {r.get('obestämt', 0)}/{reps}")
        print("Planterade effekter (detektionsgrad = andel 'tesen håller'):")
        for delta in DELTOR:
            rad = "  ".join(f"n={n_exp}: {resultat['planterat'][f'{delta}|{n_exp}']['traffar']}/{reps}"
                            for n_exp in EXPONERINGAR)
            print(f"  −{delta} mmol/L   {rad}")

    ut = _skriv(args.arm, resultat, reps, args.seed, n)
    print(f"\nSparad: {ut}", file=sys.stderr)


if __name__ == "__main__":
    main()
