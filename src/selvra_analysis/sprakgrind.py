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
