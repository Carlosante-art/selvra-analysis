"""Frågeväxlingen: brevets fråga — en per morgon, roterad, grindad.

Dialoglagrets fråge-bibliotek (FAS 1-skelett, byggt FAS-0-säkert 2026-10-30):
deterministiska mallar, ingen LLM, ingen inkorg, ingen riktig data, INGET
skickas härifrån. Modulen väljer nästa frågetyp enligt rotation och formaterar
mallen — varje utdata passerar reflektionsgrinden innan den returneras.

Fyra typer (forskningsgrund i docs/privat/brevvaxling-design.md):
  gap           — datan saknar kontext (systemet tjänar)
  kalibrering   — validerat enfrågemått mot eget normal (båda tjänar)
  bekraftelse   — sagt-loopen: "sparade '…' — stämmer?" (journalen tjänar)
  intention     — uppföljning mot personens egen sagda avsikt (personen tjänar)

Disciplin: högst EN fråga per brev, samma typ aldrig två brev i rad, tystnad
är standard. Kalibreringsfrågor är alltid relativa eget normal — aldrig
siffer-skalor (DESIGN §4). Den som faktiskt kopplar detta till morgonbrevet
byggs i FAS 1, bakom studie 002-låsning + api-inventering.
"""

from __future__ import annotations

from dataclasses import dataclass

from selvra_analysis import sprakgrind

ROTATION = ("gap", "kalibrering", "bekraftelse", "intention")


@dataclass(frozen=True)
class Fraga:
    typ: str
    text: str
    oppen_rad: str = "Du kan också skriva vad du vill — det sparas ordagrant."


def _gap(kontext: str) -> str:
    # kontext = neutral beskrivning av det omätta, t.ex. "ett pass 17:04 i går"
    return f"Selvra såg {kontext}, men vet inte vad det var. Vill du berätta?"


def _kalibrering(matt: str) -> str:
    # alltid relativt eget normal, aldrig skala
    fraga = {"somn": "Kändes natten bättre, som vanligt eller sämre än vanligt?",
             "ork": "Hur är orken i dag jämfört med en vanlig dag?",
             "aterhamtning": "Känns kroppen utvilad, som vanligt eller tröttare än vanligt?"}
    return fraga.get(matt, "Hur känns dagen jämfört med en vanlig dag?")


def _bekraftelse(citat: str) -> str:
    return f"Jag sparade ”{citat}” som något du vill. Stämmer det?"


def _intention(citat: str) -> str:
    return f"Du skrev att du vill {citat}. Hur har det gått de senaste dagarna?"


def valj_typ(senaste_typ: str | None, tillgangliga: set[str]) -> str | None:
    """Nästa typ i rotationen som är tillgänglig och inte var den förra.
    None = tystnad (inget att fråga om). Tystnad är standard, inte ett fel."""
    if not tillgangliga:
        return None
    start = ROTATION.index(senaste_typ) + 1 if senaste_typ in ROTATION else 0
    for i in range(len(ROTATION)):
        typ = ROTATION[(start + i) % len(ROTATION)]
        if typ in tillgangliga:
            return typ
    return None


def forma_fraga(typ: str, argument: str) -> Fraga:
    """Formatera en fråga av given typ och grinda den. Reser aldrig ogrindad."""
    byggare = {"gap": _gap, "kalibrering": _kalibrering,
               "bekraftelse": _bekraftelse, "intention": _intention}
    if typ not in byggare:
        raise ValueError(f"okänd frågetyp: {typ}")
    text = byggare[typ](argument)
    ok, skal = sprakgrind.granska_reflektion(text, argument)
    if not ok:
        raise ValueError(f"frågan föll på reflektionsgrinden ({skal}): {text!r}")
    return Fraga(typ=typ, text=text)
