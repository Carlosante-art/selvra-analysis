# Resultat

Varje körning ligger i `resultat/` med manifestets kontrollsumma. Här sammanfattas vad de betyder.

## 2026-10-27: första körningen, designgranskningen

Fallen frystes och committades (e0f8322) innan något kördes. Första körningen är det ärliga måttet. Den finns i `resultat/2026-10-27T041854+0000-granska-alla.json`.

| | utveckling (16) | dolda (12) |
|---|---|---|
| rätt dom | 15/16 | 8/12 |
| falska godkännanden | f13 | h01, h10 |
| falska stopp | inga | h08, h11 |
| rätt dom, fel skäl | f05 | inga |

**Vad som missades och varför:**

| Fall | Miss | Orsak |
|---|---|---|
| h01 | Tisdagar och fredagar med rullande schema godkändes | Tillåtna veckodagar delades inte upp efter loggade arbetspass, och `genomforbarhet` ursäktade att B aldrig förekom. B är den vanliga dagen; bara A kan skapas med en avsiktlig handling. |
| h10, f13 | Exponering som följer arbetsdagen i observationsstudier godkändes | Dagstyp bedömdes som helgandel på den analyserade dagen. Den ska bedömas ur loggade pass, och på exponeringsdagen när utfallet är dagen efter. |
| h08, h11 | Giltiga studier stoppades för bortfall eller styrka | Bortfallet skattades på bara de tillåtna dagarna, 26 dagar där slumpen gav 4 ogiltiga. Täckning är en egenskap hos sensorn och skattas nu på alla dagar. |
| f05 | Datumlista utan loggade pass godkändes utan varning | Att dagstypen inte går att verifiera stod bara i en notering, inte som varning. |

Efter rättningarna (commiten efter e0f8322) blir alla 28 rätt, men **det säger inget om generalisering**: de dolda fallen är förbrukade som mått i samma stund som granskningen rättades efter dem. Utvecklingsfallen körs sedan dess i CI som regressionstest.

**Nästa ärliga mått:** en ny dold uppsättning (`dold2/`), skriven utan tillgång till granskningen *efter* rättningarna.

## Språkmodellen

Ännu inte körd. Den kräver `ANTHROPIC_API_KEY` och körs lokalt:

```bash
make benchmark-llm      # samma fall, utan och med docs/studiedesign.md
```

Jämförelsen gäller samma 28 fall. Språkmodellen har inte sett dem, så för den är även utvecklingsfallen dolda.
