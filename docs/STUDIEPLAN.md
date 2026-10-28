# STUDIEPLAN — statistiken, en detalj i taget, ur egen kodbas

Målet: Carl ska kunna stå för varje dom motorn fäller — förklara den för en
CTO som trycker tillbaka, utan AI i rummet. Metoden är repots egen: bygga och
testa, inte kurs. Varje modul har ett **kvitto** — Carl förklarar *innan* han
får se svaret. Chatten är examinator.

**Regler (gäller även Claude i framtida sessioner):**
1. En modul i taget, i ordning. Kvittot godkänt innan nästa öppnas.
2. **Claude ger aldrig svaret före kvittot.** Frågor möts med motfrågor och
   pekare till kod/tester — aldrig med facit. Det är språkgrindens princip
   applicerad på undervisning: hjälpen får forma frågan, aldrig fria svaret.
3. Ett kvitto är godkänt när förklaringen är korrekt *och* skulle övertyga en
   skeptisk utomstående. "Nästan rätt" är inte godkänt — det är modulens poäng.
4. Bocka av med datum. Planen är ett dokument, inte en känsla.

---

## Modul 1 — Osäkerhet och intervall: vad ett KI faktiskt lovar

**Läs:** `src/selvra_analysis/stats.py` (bootstrap-kärnan), `docs/exempelrapport.md`.
**Gör:** `make demo && make reproduce` — samma siffror varje gång; fundera på varför.
**Kvitto:** Förklara (a) vad "95 % intervall −0,83 till +1,45" i exempelrapporten
*betyder* — och två vanliga feltolkningar; (b) varför exempelstudiens dom blev
"motbevisad" fast skattningen är +0,31, inte 0. ☐

## Modul 2 — Blockbootstrap: varför dagar inte är oberoende

**Läs:** `block_bootstrap_difference` i stats.py; motortest-avsnittet i
`benchmark/RESULTAT.md` (natt-SD 4,97-fyndet).
**Gör:** Kör `make motortest` och läs JSON-utfallet.
**Kvitto:** Förutsäg — *innan* du provar — vad som händer med intervallbredden
om blocklängden sänks från 7 till 1 på autokorrelerad data, och förklara varför
fel blocklängd ger ett *ärligt utseende* men *falskt smalt* intervall. ☐

## Modul 3 — Randomiseringstest och testinvertering (n1-kärnan)

**Läs:** `src/selvra_analysis/n1.py`, `_estimate` i study.py, `tests/test_n1.py`.
**Kvitto:** (a) Förklara varför `design.par: minst 6` är ett matematiskt golv,
inte en smakgräns — vad är minsta möjliga p med 5 par? (b) Förklara skillnaden
exakt test mot Monte Carlo i körjournalens `exact`-fält. ☐

## Modul 4 — Styrka: väntade par, SD-osäkerhet, och f17-läxan

**Läs:** `_expected_power`, `_pairs_needed`, `_check_power` i granska.py;
benchmark-fallen f17/f18 (filerna, inte RESULTAT-texten ännu).
**Kvitto:** Förklara — *före* du läser RESULTAT.md-avsnittet — varför f17
(2,4 mmol/L-gap) passerade granskningen medan f18 (3,6) fällde den, och varför
svaret heter "osäkerhetsband på SD-skattningen". Sedan: läs facit och rätta dig
själv skriftligt. ☐

## Modul 5 — Bias: dagstyper, överföring, negativa kontroller

**Läs:** `_check_time`, dagstyps-logiken i granska.py; p00:s slutrapport
(testare-1:s mapp, lokalt); METODPLAN "target trial-emulering".
**Kvitto:** (a) Förklara p00:s negativa kontroll (gårdagens steg) och exakt vad
ett utslag där hade avslöjat. (b) Förklara varför "regeln låstes före
beräkningen" inte skyddar mot confounding i en retrospektiv studie — och vad
som skyddar i en lottad. ☐

## Modul 6 — Bevisaxlarna: OCEBM-design och GRADE-tillförlitlighet

**Läs:** METODPLAN "Bevisaxlarna"; `_tillforlitlighet` i rapport.py.
**Kvitto:** Jag ger dig tre påhittade studiebeskrivningar; du sätter design-nivå
och GRADE-betyg på var och en och försvarar nedgraderingarna. Facit är
Oxford-tabellen, inte min åsikt. ☐

## Modul 7 — Sekventiella gränser (lärs genom att byggas, METODPLAN §2)

**Läs:** METODPLAN §2 + Pocock/O'Brien-Fleming-grunderna (läses *efter* kvittot a).
**Kvitto:** (a) Förklara — innan litteraturen — varför "titta på datan varje
vecka och stoppa när p < 0,05" ökar falsklarmsrisken, och skissa din egen
lösning. (b) När §2 byggs: formulera kalibreringstestet som bevisar att den
totala felrisken hålls. Det här kvittot är på riktigt — det blir en del av bygget. ☐

## Modul 8 — Domare och deras fel: LLM-armen, motortestet, chaos monkey

**Läs:** benchmark/PROTOKOLL.md regel 7–8; LLM-avsnittet i RESULTAT.md;
`motortest.py`.
**Kvitto:** (a) Förklara varför "motbevisad" under nollhypotes är ett *korrekt
frikännande* och inte ett falskt fynd — felet Claude själv gjorde och rättades
på i motortestet. (b) Förklara varför kunskapsbasen gjorde LLM-domaren sämre,
med RESULTAT-siffrorna som stöd. ☐

---

**Efter modul 8:** Carl kan försvara variant 1-granskningen (design-review)
själv. Modul 7b byggs in i sekventiella-gränser-arbetet när det startar.
Avbockade kvitton loggas här med datum, så planen är sitt eget bevis.

*Tillkom 2026-10-29 på Carls beslut: "studieplanen startar". Vattenpasset
stiger genom att bygga och testa, inte genom kurs.*
