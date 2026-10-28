> **SYNTETISKT EXEMPEL — ingen människas mätvärden.**
> Datan är seedad demodata (`make demo`), skapad utan promenadeffekt. Formatet är
> exakt det en riktig studie får; siffrorna visar bara hur en rapport ser ut.
> Granskningsmotorn stoppar medvetet studier på demodata ("siffrorna säger inget
> om dig"), så den här rapporten är byggd utanför studielivscykeln — samma
> beräkning som CI:s reproduce-kontroll — och kan aldrig förväxlas med en dom.

# Promenad efter middag och kvällsglukos (exempel)

*randomiserat n-of-1-försök med parade perioder · studie `000-exempel-promenad` · låst 2026-10-27 · körd 2026-10-28*

## Svar

**Tesen motbevisad: hela intervallet visar en mindre effekt än den minsta relevanta, eller en effekt åt andra hållet.** Skattning +0,31 mmol/L (95 % intervall -0,83 till +1,45).

*Tillförlitlighet (GRADE): hög — randomiserad och förregistrerad; nivå 1-bevis för personen (OCEBM 2011).*

## Fråga och tes (låsta i förväg)

- **Fråga:** Sänker en promenad på 40 minuter efter middagen medelglukos 19–22 jämfört med vila?
- **Tes:** Promenaden sänker medelglukos 19–22 med minst 1,0 mmol/L.
- **Motbevis:** Hela intervallet visar en sänkning mindre än 1,0 mmol/L (eller ingen).
- **Minsta relevanta effekt:** -1,00 mmol/L

## Metod

- **A:** Promenad 40 minuter, start 18:30 ± 15 min, efter middagen
- **B:** Ingen promenad, vila efter middagen
- **Design:** 12 par om två perioder à 2 dagar, ordningen inom varje par lottad före start; 1 tvättdag(ar) per period räknas inte.
- **Utfall:** medel glukos 19:00–22:00 lokal tid, medel per period.
- **Analys:** parvis randomiseringstest (exakt), intervall genom testinvertering. Lottat villkor gäller oavsett följsamhet.

## Resultat

| | |
|---|---|
| Kompletta par | 12 (bortfall 0) |
| Skattning A − B | +0,31 mmol/L |
| Intervall | -0,83 till +1,45 |
| p (ingen effekt) | 0,5488 |
| AB-par / BA-par | -0,14 / +0,64 |

Skiljer sig AB- och BA-paren mycket åt kan en eftereffekt mellan perioderna finnas.

## Negativ kontroll

medel glukos 07:00–10:00 lokal tid: Morgonen kommer före kvällens promenad samma dag och kan inte påverkas av den.

Skattning -0,00 (95 % intervall -1,11 till +1,08); intervallet täcker noll, som förväntat.

## Protokoll (CENT 2015)

- **Periodeffekt:** Parade perioder om två dagar intill varandra; långsam drift (säsong, sensorålder) påverkar båda villkoren i ett par lika.
- **Överföring:** Första dagen i varje period räknas inte (tvätt); skattningen redovisas separat för AB- och BA-par.
- **Stoppregel:** Avbryts vid upprepad hypoglykemi nivå 2 under promenad eller sjukdom; avbrott redovisas.
- **Ändringar efter låsning:** inga

## Spårbarhet

- Studiefil sha256 `ea1c4f96a7c02a31`, pipeline-commit `6d552ca7f719`
- Dataversion `5977c5055b6cd3aa` (3 källor)
- Körd vid commit `0efd8a1a7a2d`
