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

## 2026-10-27: dold2, generaliseringsmåttet

Tolv fall skrivna av en annan agent än den som rättade granskningen, med tillgång bara till
fallformatet, skältabellen och miss-analysen ovan — avsiktligt, eftersom dold2 mäter om just
de rättningarna generaliserar. Frysta och committade (1f39762) före första körningen.
Körningen finns i `resultat/2026-10-27T043431+0000-granska-alla.json`.

| | dold2 (12) |
|---|---|
| rätt dom mot facit | 9/12 |
| falska godkännanden | inga |
| avvikelser | d05, d09, d12 — alla STOPP styrka mot facit GODKANN |

**Alla fyra rättningarna generaliserade:** d01 (B omöjlig på en rullande delmängd av tillåtna
veckodagar) stoppades ur loggade pass; d03 (dagstyp bedömd på exponeringsdagen, utfall natten
efter) stoppades som dagtyp; d06 (datumlista utan loggade pass) godkändes med varningen facit
kräver; d05:s bortfall skattades på alla dagar. Över-korrigeringssonderna höll: d02 (A aldrig
historisk men avsiktlig) och d04 (härledd exponering utan dagstypsstruktur) godkändes.

**Avvikelserna är fel i facit, inte i granskningen.** Efterhandsprövning mot motorns redovisade
aritmetik: d05 ger 9 väntade kompletta par efter sensorbortfall → 71 % styrka; d09 ger 66 % med
14 par mot SD 1,01; d12 ger 78 % med 10 par — samtliga under det låsta kravet 80 %, med behövt
antal par utskrivet (15, 18, 11). Fallförfattaren bedömde styrkan på känsla; motorn räknade.
Facit ändras inte i efterhand (regeln ovan); avvikelserna står kvar i facit och bokförs här
som facitfel. Eftersom granskningen **inte** rättades efter dold2 är uppsättningen fortfarande
orörd som mått.

**Resultatet som mening:** på tolv tidigare osedda fall gjorde granskningen noll metodfel,
släppte inget kritiskt igenom, stoppade inget giltigt — och hade rätt mot människan i alla
tre fall där de var oense.

## Språkmodellen

Ännu inte körd. Den kräver `ANTHROPIC_API_KEY` och körs lokalt:

```bash
make benchmark-llm      # samma fall, utan och med docs/studiedesign.md
```

Jämförelsen gäller samma 28 fall. Språkmodellen har inte sett dem, så för den är även utvecklingsfallen dolda.
