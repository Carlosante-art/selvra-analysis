# Metodplan: motorns nästa metodologiska steg

Prioriterad lista. Varje punkt landar enligt benchmark/PROTOKOLL.md: fall först,
fix sedan, ny dold uppsättning efter varje batch. Ingen punkt byggs för att den
är intressant — bara när den blockerar en verklig studie eller en verklig miss.

## 1. Strata-SD (j08-rättningen) — pågår, fall-först

När de tillåtna dagarna är färre än MIN_SD_DAYS poolas SD i dag över alla dagar.
Skiljer sig dagstyperna åt (arbetsdagens lunchpromenad mot helgens sovmorgon)
räknas skillnaden *mellan* dagstyper som brus, styrkan underskattas och giltiga
studier stoppas (benchmark: j08, sann styrka 84 % mot skattade 66 %).
Rättning: skatta variationen inom dagstyp (residualer efter dagstypens medel ur
loggade pass), med graciös reträtt till dagens beteende när inga pass finns.

## 2. Sekventiella stoppregler — nästa stora

I dag: fast antal par, en analys vid slutet. Modern n-of-1-praxis
(Platform-of-1 2025; Senn/Shrestha Bayesian adaptive) är för-registrerade
sekventiella gränser: avläsningspunkter och beslutsgränser låses före start,
och studien får avgöras tidigt när bevisen räcker. Bryter inte en-körning-
principen — regeln är låst, den har bara flera förutbestämda avläsningar.
Kräver: utökning av studie.yml (avlasningar + gränser), las/kor-stöd,
kalibreringstest av total felrisk, granska-kontroll av gränserna.

## 3. Hierarkisk styrkedelning — n ≥ 2-metoden

Aggregerade n-of-1 med Bayesiansk shrinkage: individer lånar styrka av
population utan att dela rådata (Shrestha & Jenkins 2021; HDSR specialnummer).
Byggs först när en andra användare finns med egna körda studier. Det är också
RWE-pitchens metodologiska ryggrad: heterogenitet i behandlingseffekt.

## 4. Mikro-randomiserade studier (MRT) — parkerad på principbeslut

Fältets standard för mobil hälsa (Murphy m.fl.): randomisering per
beslutstillfälle, hundratals per person, excursion-effekter. Enorm styrka per
kalendertid — men kräver att motorn skickar prompts vid beslutstillfällen,
vilket nuddar konstitutionens push-förbud. Möjlig linje: opt-in-prompts enbart
inom en låst studie är inte engagemangspush. **Beslutet är Carls**, inte
teknikens. Byggs inte före det beslutet.

## Byggs inte, med skäl

- **Bandit-allokering för behandlingsval** (adaptiv randomisering mot "bästa
  armen"): optimerar val, inte kunskap; svårare felkontroll; fel passform för
  bevis-varumärket innan sekventiella gränser finns.
- **LLM-bedömning i granskningen**: uppmätt sämre än deterministisk beräkning
  (RESULTAT.md: 0 mot 17–20 falska godkännanden). LLM föreslår; koden beslutar.
