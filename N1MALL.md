# N-of-1-mall: experiment på en person

Använd den här mallen när frågan är **orsak**: *gör X skillnad för mig?* Observationsanalyser (`ANALYSMALL.md`) visar vad som följer på vad. Ett experiment där slumpen bestämmer när du gör X kan visa att X orsakar skillnaden, för just dig, under just de förhållandena.

Strukturen följer SPENT 2019 (protokoll för n-of-1-försök, Porcino m.fl., *BMJ* 2020;368:m122) och rapporteringen CENT 2015 (Vohra m.fl., *BMJ* 2015;350:h1738). Verktygen finns i [`src/selvra_analysis/n1.py`](src/selvra_analysis/n1.py).

**Ordningen är inte förhandlingsbar:** protokollet committas, schemat lottas och dess kontrollsumma committas, *sedan* börjar experimentet. Analyskoden skrivs och fryses som i `ANALYSMALL.md` steg 4b.

---

## Protokoll (committas innan experimentet startar)

### 1. Fråga och skäl för n-of-1

- **Fråga:** gör *[intervention]* jämfört med *[jämförelse]* skillnad för *[utfall]*?
- **Varför n-of-1:** effekten antas vara individuell, snabb och övergående. (Om effekten tar veckor att byggas upp eller är permanent passar designen inte.)
- **Beslut:** om A … / om B …

### 2. Deltagare och förutsättningar

- Diagnos, behandling (insulinregim, pump/penna, sensor) under hela experimentet.
- **Hålls konstant:** … (t.ex. basaldos, måltidstider). Ändras något, logga det.

### 3. Intervention och jämförelse

| | A (intervention) | B (jämförelse) |
|---|---|---|
| Vad exakt | t.ex. promenad 40 min | ingen promenad |
| När | t.ex. start 18:30 ± 15 min, efter middag | samma tid: vila |
| Dos som inte får över-/underskridas | | |

> Dosen är det du testar. "40 minuter" säger inget om 50 eller 60. Vill du veta det är det ett nytt experiment med fler armar.

### 4. Utfall

- **Primärt utfall** (exakt ett), med tidsfönster: t.ex. medelglukos 19:00–22:00 lokal tid samma dag (`n1.window_outcomes`).
- **Varför det fönstret:** det ska ligga där mekanismen verkar. Ett helt dygn späds ut av allt annat som händer.
- **Sekundära utfall** (explorativa): …
- **Säkerhetsutfall:** hypohändelser nivå 2 under A respektive B.

> Välj utfall efter brus, inte efter vad som låter bäst. Kör `python -m selvra_analysis.n1 sd` på din befintliga data för kandidaterna. På den syntetiska datan är dygns-TIR så brusigt att en effekt på 10 procentenheter bara hittas i 30 % av fallen med 20 par; medelglukos i ett kvällsfönster ger betydligt bättre chans med färre par. Gör samma jämförelse på din egen data innan du väljer.

### 5. Design

- **Perioder:** parvisa. Varje par har en A-period och en B-period i lottad ordning.
- **Periodlängd:** … dagar. **Tvätt:** de första … dagarna i varje period räknas inte (analytisk tvätt), för att en eventuell eftereffekt av förra perioden inte ska hamna i fel villkor.
- **Antal par:** … (se 6).
- **Blindning:** inte möjlig för beteenden. Konsekvens: förväntan kan påverka. Motverkas av objektivt utfall (CGM, inte självskattning) och av att utfallet och analysen är låsta i förväg.

### 6. Underlag (antal par)

- **Minsta effekt som spelar roll:** … (utfallets enhet).
- **Variation per period**, mätt på din data: `python -m selvra_analysis.n1 sd --window 19:00 22:00 --outcome mean_mmol --days <analyserade dagar>` → …
- **Styrka:** `python -m selvra_analysis.n1 power --pairs N --effect E --sd S` → välj N så att styrkan är minst 80 %.
- **Golv:** med n par kan p aldrig bli lägre än 2/2ⁿ. Under 6 par kan testet aldrig nå 5 %.

### 7. Randomisering

```bash
python -m selvra_analysis.n1 schedule --start ÅÅÅÅ-MM-DD --pairs N \
    --period-days D --washout-days W --out analyses/NNN-namn/schema.csv
```

Fröet dras från operativsystemets slump och sparas i filen. Committa `schema.csv` och citera kontrollsumman här:

- **Schema:** *(fylls i av kommandot)*

### 8. Följsamhet och avvikelser

- Logga varje genomförd intervention i händelseloggen (`traning`, med minuter i noteringen).
- Avvikelser (missad promenad, sjukdom, sensorbyte mitt i ett fönster) loggas samma dag, aldrig i efterhand när resultatet syns.
- **Avbrottsregler:** säkerhet går före protokollet. Hypo under A eller B behandlas som vanligt och loggas.

### 9. Analys

- **Primär:** parvis randomiseringstest (`n1.randomisation_test`) på periodernas medelvärden, enligt schemat (*intention to treat*: lottat villkor, oavsett följsamhet). Rapporteras: skattning A − B, 95 % intervall genom testinvertering, p-värde, antal par.
- **Beroende mellan dagar:** testet bygger på den lottning som faktiskt gjordes, så det kräver inte oberoende dagar.
- **Eftereffekt och ordning:** analytisk tvätt enligt 5; skattningen redovisas separat för AB- och BA-par. Skiljer de sig mycket åt tyder det på eftereffekt.
- **Saknade data:** perioder utan giltiga fönsterdagar räknas som saknade; paret faller bort och redovisas. Ingen imputering.
- **Känslighet** (bestäms nu): endast perioder med genomförd intervention (*per protocol*); utan artefaktflaggade värden; …
- **Beslutsregel:** effekten finns om …; ingen praktiskt relevant effekt om hela intervallet ligger under minsta relevanta effekt; annars obestämt.

### 10. Frusen analyskod

**Frusen analyskod:** *(se ANALYSMALL steg 4b)*

---

## Rapport (CENT 2015, efter experimentet)

1. **Titel och sammanfattning:** "n-of-1-försök", fråga, design, resultat i en mening med siffra och intervall.
2. **Metod:** allt ovan, med avvikelser från protokollet redovisade och motiverade.
3. **Flöde:** planerade och genomförda par, bortfallna perioder och varför.
4. **Följsamhet:** andel A-perioder där interventionen faktiskt gjordes.
5. **Resultat:** skattning, intervall, p; per par i en tabell; AB mot BA.
6. **Skador:** hypohändelser per villkor.
7. **Tolkning:** gäller dig, under de förhållandena, för den dosen. Inte andra personer, inte andra doser.
8. **Körningspost:** länk till `korningar/` (commit, frusen commit, dataversion).

---

### Kodexempel

```python
import duckdb
from selvra_analysis import n1
from selvra_analysis.provenance import run_analysis

con = duckdb.connect("data/selvra.duckdb", read_only=True)
schema = n1.read_schedule(HERE / "schema.csv")
daily = n1.window_outcomes(con, "19:00", "22:00")
periods = n1.period_outcomes(schema, daily, "mean_mmol")
result = n1.randomisation_test(periods)
run_analysis(HERE, con, {"primart": result.as_dict(), "perioder": periods.to_dict("records")})
```
