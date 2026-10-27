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

**Omprövning mot sann styrka.** Den första skrivningen här lät granskningen själv avgöra att facit hade fel. Det är systemet som testas som dömer, och det räknas inte. Scenariot definierar den sanna datan (dag-till-dag-SD och täckning), så den sanna styrkan går att simulera oberoende av både facit och granskningens skattning:

| Fall | Sann styrka | Granskningen | Facit | Rätt |
|---|---|---|---|---|
| d05 | 90 % | 71 %, STOPP | godkänn | facit: falskt stopp |
| d09 | 70 % | 66 %, STOPP | godkänn | granskningen |
| d12 | 84 % | 78 %, STOPP | godkänn | facit: falskt stopp |

**dold2 efter omprövning: 10/12, inga falska godkännanden, två falska stopp.**

## 2026-10-27: dold3, det renaste måttet

Tolv fall av en agent som varken sett granskningen, rättningarna eller resultaten. Frysta och committade (3d04309) före första körningen, och körda på exakt samma kod som dold2.

| | dold3 (12) |
|---|---|
| rätt dom mot facit | 10/12 |
| falska godkännanden | inga (7/7 stoppade, alla av rätt skäl) |
| avvikelser | j04 (underlag), j08 (styrka), STOPP mot facit GODKANN |

Omprövning mot sann styrka:

| Fall | Sann styrka | Granskningen | Rätt |
|---|---|---|---|
| j04 | 76 % (6 par: ett enda förlorat par gör p < 0,05 omöjligt; 22 % risk) | STOPP underlag | granskningen |
| j08 | 84 % | 66 %, STOPP | facit: falskt stopp |

**dold3 efter omprövning: 11/12.**

## Sammanfattning efter rättningarna (dold2 + dold3, 24 fall)

- **Falska godkännanden: 0 av 13** fall som skulle stoppas. Inget kritiskt fel släpptes igenom.
- **Falska stopp: 3 av 11** giltiga fall (d05, d12, j08). Alla tre gäller styrka nära 80-procentsgränsen.
- **Orsaken är densamma i alla tre:** granskningen är för pessimistisk när den skattar styrkan. Väntat antal par avrundas nedåt, och SD skattad på få dagar används som om den vore exakt. Rättningen är att räkna styrkan över fördelningen av kompletta par och att varna i stället för att stoppa när osäkerheten i skattningen omfattar 80 %. Görs den förbrukas dold2 och dold3 som mått för styrkekategorin, och nästa mätning kräver en ny uppsättning.

## 2026-10-27: styrka-rättningen

Rättningen ur sammanfattningen ovan är genomförd: väntad styrka beräknas nu över den
binomiala fördelningen av kompletta par (inte vid dess golv), och när SD-skattningens
osäkerhet (normalapproximation på n dagar) rymmer 80 % blir domen VARNING med rådet
kvar — inte STOPP. Körning efter rättningen: `resultat/` (granska-alla, efter commit).

| Fall | Före | Efter | Skiljedom (sann styrka) |
|---|---|---|---|
| d05 | STOPP 71 % | **GODKANN** (varning) | 90 % — rättningen korrekt |
| d12 | STOPP 78 % | **GODKANN** (varning) | 84 % — rättningen korrekt |
| d09 | STOPP 66 % | STOPP | 70 % — granskningen har rätt, facit fel |
| j04 | STOPP underlag | STOPP underlag | 22 % risk för omöjligt p — granskningen har rätt |
| j08 | STOPP 66 % | STOPP | 84 % — **kvarstående äkta falskt stopp** |

j08:s rotorsak är en annan: när de tillåtna dagarna är för få poolas SD över alla dagar,
och skiljer sig dagstyperna åt överskattas bruset. Den rättningen är inte gjord.

**Protokollet:** granskningen ändrades efter att dold2 och dold3 setts — båda är därmed
förbrukade som mått för styrka/underlag-kategorierna. Utvecklingsfallen fortsätter som
regressionstest (18/18 gröna efter rättningen; inga andra kategorier påverkades).
Nästa ärliga styrkemått kräver en dold4 skriven av en författare som inte sett rättningen
— inte av den som skrev den.

## 2026-10-27: strata-SD-rättningen — protokollets första cykel, efter boken

Första efterlevnaden av PROTOKOLL.md, inklusive att protokollet bet sin egen författare:

1. **f17 skrevs, frystes och committades före fixen** — och visade sig passera: SD-osäkerhets-
   bandet från förra rättningen täcker ett dagstypsgap på 2,4 mmol/L. Frysta fall justeras
   aldrig efter resultat, så f17 står kvar som regressionsfall för bandet.
2. **f18 (gap 3,6 mmol/L) frystes och committades (f0799ae), och fallerade**: poolad SD 1,80
   mot sann lördags-SD 0,9 gav STOPP vid 53 % där sann styrka är ~97 %.
3. **Rättningen:** när tillåtna dagar är färre än MIN_SD_DAYS skattas variationen inom dagstyp
   (residualer efter dagstypens medel, dagstyp ur loggade pass via samma källa som positiviteten),
   med reträtt till gamla beteendet när pass saknas.
4. **Efter:** f18 GODKANN, f17 kvar grön, regressionssviten 18/18, inga nya falska godkännanden.

**Observation på förbrukade uppsättningar** (inte ett mått — dold2/dold3 är förbrukade för
styrka-kategorin sedan förra rättningen): j08, det sista äkta falska stoppet, blev grönt.
Kvarvarande avvikelser mot facit är d09 och j04, båda skiljedömda som facitfel.
**Granskningen har därmed inga kända äkta fel: 30/30 stopp av rätt skäl, 0 falska godkännanden,
0 skiljedömda falska stopp.** Nästa ärliga mått kräver dold4 av en blind författare.

## 2026-10-27: språkmodellen, båda armarna

Körd med `claude-opus-5-5` — frontier-modellen, inte en liten — på samtliga 52 fall
(utveckling + dold + dold2 + dold3). Modellen har aldrig sett fallen, så alla är dolda för den.
Körningarna: `resultat/2026-10-27T063542+0000-llm-alla.json` och `…-llm+kunskap-alla.json`.

| | granska | LLM (opus-5-5) | LLM + kunskapsbas |
|---|---|---|---|
| stoppade av fall som ska stoppas | 30/30 | 13/30 | 10/30 |
| **falska godkännanden** | **0** | **17** | **20** |
| falska stopp (av 22 giltiga) | 3* | 0 | 0 |
| godkända med rätt flaggor | — | 17/22 | 17/22 |

\* granskas tre falska stopp är styrka-gränsfall (se omprövningen ovan), på fall där den
redovisar sin aritmetik öppet.

**Vad språkmodellen släppte igenom:** dagtypsconfounding (f13, d03, h10), överföring mellan
intilliggande dagar (f06, d07, j07), saknad negativ kontroll (j03), negativ kontroll efter
verkans början (j05), för lite underlag (f15, j11, d11) — alltså precis de fel som förstör
en studies svar. Modellen godkänner i princip allt som ser välskrivet ut: 0 falska stopp
eftersom den nästan aldrig stoppar.

**Kunskapsbasen gjorde modellen sämre, inte bättre** (17 → 20 falska godkännanden):
mer text att resonera kring ledde till mer välvilja, inte mer skärpa.

**Slutsatsen, en mening:** på 52 fall missade den deterministiska granskningen inget
kritiskt fel; frontier-LLM:en släppte igenom 17–20 av 30 — och det är skillnaden mellan
att beräkna metodfel ur egen data och att bedöma dem på känsla.
