"""Språkgrinden: granska, fast för prosa.

All text som en språkmodell skriver åt en människa passerar tre deterministiska
kontroller innan den lämnar motorn. Underkänd text skickas aldrig — avsändaren
faller tillbaka på en mallad formulering istället.

1. Inga påhittade mätvärden: varje tal med enhet (mmol/L, %, slag, ms, h, min)
   i utgående text måste förekomma i källdokumenten texten bygger på. En modell
   som skriver "0,8 mmol/L" när journalen säger 0,47 stoppas här.
2. Inga råd: konstitutionen säger beskriva och bjuda in — aldrig råda. En
   förbjuden ordlista fångar rådgivningsspråk.
3. Längdtak: en tolkning som sväller är en tolkning ingen läser.

Grinden kan inte bedöma om texten är klok — bara att den är sann mot sina
källor, rådfri och lagom. Det räcker för att det pinsamma aldrig ska skickas.
"""

from __future__ import annotations

import re

FORBJUDNA = ("du borde", "ni borde", "rekommender", "öka dosen", "minska dosen",
             "öka din dos", "minska din dos", "ta mer insulin", "ta mindre insulin",
             "bör du", "du bör", "du måste", "se till att du", "du behöver ta")

# Tal följt av en mätenhet — det är de som kan vara påhittade mätvärden.
_MATVARDE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:mmol(?:/L)?|%|procent|slag|ms|mg/dL|h\b|tim|min\b|poäng|steg)",
    re.IGNORECASE)
_TAL = re.compile(r"\d+(?:[.,]\d+)?")


def _tal(s: str) -> set[float]:
    return {float(m.replace(",", ".")) for m in _TAL.findall(s)}


def _matvarden(s: str) -> set[float]:
    return {float(m.replace(",", ".")) for m in _MATVARDE.findall(s)}


# Reflektionsutdata (dialoglagret) har hårdare regler än breven: inga coach-
# mönster, inga poäng eller betyg, inga värdeord, inga normer användaren inte
# satt, inget intag-mot-förbrukning, ingen medicinsk tolkning. Hypo får aldrig
# bli en reflektionsfråga, och glukos beskrivs som mönster i tid — aldrig som
# andel utanför mål. (FAS 0, 2026-10-29.)
REFLEKTIONSFORBUD = (
    "borde", "försök att", "försök ", "kanske kan du", "har du funderat",
    "tips:", "mitt råd", "rekommenderar",
    "poäng", "betyg", "score", "/10", "av 10",
    "normalt för", "rekommenderad nivå", "du ska", "man bör",
    "kaloriunderskott", "förbränt mot intag", "kalorier in", "intag mot",
    "öka dosen", "minska dosen", "justera insulin",
)
_VARDEORD = re.compile(r"\b(bra|dålig|dåligt|dåliga|duktig|duktigt)\b", re.IGNORECASE)
_HYPO = re.compile(r"hypo|lågt blodsocker|känning", re.IGNORECASE)
_ANDEL_UTANFOR_MAL = re.compile(r"(%|procent)[^.]{0,40}(utanför|över|under)\s*mål"
                                r"|((utanför|över|under)\s*mål[^.]{0,40}(%|procent))",
                                re.IGNORECASE)


def granska_reflektion(text: str, kallor: str, max_tecken: int = 1200) -> tuple[bool, str]:
    """Dialoglagrets utdata-grind: baskontrollerna plus reflektionsförbuden."""
    ok, skal = granska_text(text, kallor, max_tecken)
    if not ok:
        return ok, skal
    lag = text.lower()
    for monster in REFLEKTIONSFORBUD:
        if monster in lag:
            return False, f"reflektionsförbud: {monster!r}"
    if traff := _VARDEORD.search(text):
        return False, f"värdeord: {traff.group(0)!r} — beskrivning, aldrig betyg"
    if _HYPO.search(text) and "?" in text:
        return False, "hypo får aldrig bli en reflektionsfråga"
    if _ANDEL_UTANFOR_MAL.search(text):
        return False, "glukos beskrivs som mönster i tid, aldrig som andel utanför mål"
    return True, "ok"


def granska_text(text: str, kallor: str, max_tecken: int = 2000) -> tuple[bool, str]:
    """(godkänd, skäl). Källorna är dokumenten texten får hämta sina siffror ur."""
    lag = text.lower()
    for ord_ in FORBJUDNA:
        if ord_ in lag:
            return False, f"rådgivningsspråk: {ord_!r}"
    if len(text) > max_tecken:
        return False, f"för lång: {len(text)} tecken (tak {max_tecken})"

    tillatna = _tal(kallor)
    for varde in _matvarden(text):
        # ±0.005 täcker avrundning; negationstecken hanteras av att journalen
        # skriver både −0.47 och intervallgränser som egna tal.
        if not any(abs(varde - t) < 0.005 or abs(abs(varde) - abs(t)) < 0.005
                   for t in tillatna):
            return False, f"mätvärdet {varde:g} finns inte i källorna"
    return True, "ok"
