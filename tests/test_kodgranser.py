"""Kodgränsen: separera när filen fortsätter att växa (Carls regel 2026-10-28).

En modul som passerar taket delas i lövmoduler (som rapport.py och
dreamer_minne.py) — taket höjs inte. Läsbarhet är produktens
förtroendekapital; growth by accretion är hur den förloras.
"""

from pathlib import Path

TAK_RADER = 650
SRC = Path(__file__).resolve().parent.parent / "src" / "selvra_analysis"


def test_ingen_modul_over_taket() -> None:
    for_stora = {f.name: antal for f in sorted(SRC.glob("*.py"))
                 if (antal := len(f.read_text().splitlines())) > TAK_RADER}
    assert not for_stora, (
        f"moduler över {TAK_RADER} rader: {for_stora} — separera i lövmoduler, höj inte taket")
