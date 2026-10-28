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

## Klart: wearable-only-läget (2026-10-27)

Dagsryggraden är nu unionen av CGM- och wearable-dagar; glukoskolumnerna är null på
dagar utan CGM, och utfallsgiltighet bedöms per kolumn (wearable-utfall gäller när
värdet finns, CGM-utfall kräver giltig CGM-dag). Kolumn-utfall tillåts i n1.
En person utan CGM får därmed hela kedjan: marts (159/159 tester på pappas databas),
studievalidering, granskning med power ur egen variation. Första beviset: granskaren
stoppade p01-promenad-vilopuls korrekt — 35 dagars baslinje ger 1 väntat komplett par
av 12. `make person-build PERSON=namn` bygger en persons marts.

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

## 5. Prior-bibliotek för design — vilande tills ett förslag behöver det

Publicerad statistik (metaanalyser, MCID-värden) som litet bibliotek
(YAML per påstående: källa, population, effektstorlek, KI) — läst av
**förslagsgrinden, aldrig av domen**. Tre legitima användningar: rangordna
vilka frågor som är värda att ställa, förankra `minsta_relevanta_effekt`
när personens baslinje är tunn, och sätta realistiska styrkeförväntningar
(litteraturen förutsade p00: dagseffekt av promenad på vilopuls är liten).
Gräns satt av uppmätt resultat: kunskapsbas i *bedömningen* gjorde LLM-
granskaren sämre (RESULTAT.md, 20 falska godkännanden) — litteratur får
forma frågan, aldrig fria svaret. Mot ditt eget normala, aldrig en norm.
Grind: byggs först den dag ett konkret förslag behöver en litteratur-
förankrad effektstorlek. Relaterat: T1DEXI/OhioT1DM/DiaTrend (Carls
Vivli-ansökan) laddas när de beviljas — men in i **benchmarken** som
planterade effekter på riktiga serier, inte som priors.

## Bevisaxlarna — vad som är en slutsats på riktigt (källgranskat 2026-10-28)

Carls krav: "vi måste kunna reglera vad som är en slutsats på riktigt — inte
bara: efter 1 timme, nej, det finns ingen korrelation, sen var studien över."
Djupsökningen visar att fältet inte använder en trappa utan **två axlar**, och
att måttet aldrig är kalendertid utan design + täckta lottade dagar.

### Axel 1 — design (OCEBM 2011, frågan "hjälper insatsen?")

Oxford-nivåerna, ordagrant ur tabellen (CEBM Levels of Evidence 2.1):
nivå 1 = *"systematic review of randomized trials or n-of-1 trials"*,
nivå 2 = randomiserad studie (eller observation med dramatisk effekt),
nivå 3 = icke-randomiserad kohort, nivå 4 = fallserier/case-control,
nivå 5 = mekanismresonemang. För biverkningsfrågan är nivå 1 uttryckligen
*"n-of-1 trial with the patient you are raising the question about"*.

Det avgörande: **en randomiserad n-of-1 på personen själv är nivå 1-bevis för
den personen** — inte en svagare kusin till "riktiga" studier. Selvras
kärndesign sitter alltså högst på axeln, för exakt den fråga Selvra ställer.

Mappning: skanner-mönster = nivå 5 (mekanism/hypotes — aldrig en slutsats);
retrospektiv självkontrollerad körning (p00) = observationsstudie;
prospektiv lottad förregistrerad n-of-1 (001, p02) = nivå 1 för personen.

### Axel 2 — tillförlitlighet (GRADE)

Fyra betyg: hög, måttlig, låg, mycket låg. Randomiserat startar **hög**;
observation startar **låg**. Nedgradering (fem domäner): risk för bias,
inkonsistens, indirekthet, imprecision, publikationsbias. Uppgradering
(endast observation): stor effekt, dos–respons, motriktad confounding.

Selvras maskineri är redan GRADE-format utan att ha hetat så:
"**obestämt**" = imprecision (intervallet rymmer både relevant och irrelevant
effekt); dagstyp-VARNING = risk för bias; negativ kontroll = bias-detektion;
periodeffekt-avsnittet = indirekthet. Konsekvensen för p00: en retrospektiv
dom startar **låg** och kan aldrig bli hög hur snäv skattningen än är —
därför är den en dörr, inte ett lås.

### Replikationens två platser (här satt utkastet fel)

- **Inom personen:** replikationen är paren/cyklerna i n-of-1-designen själv —
  fler lottade par = starkare dom. Det är *tidens* legitima roll: tid köper
  par, inte mognad. 24 lottade dagar över tio veckor slår 32 historiska nätter
  beräknade på en timme — av designskäl, inte av kalenderskäl.
- **Mellan personer:** aggregering (hierarkisk modell, §3) svarar på en
  *annan* fråga — populationseffekt och heterogenitet — och är ingen "högre
  nivå" för individen. Generaliserbarhet och individuell bevisstyrka är
  olika axlar och ska aldrig blandas i språket.

### Regler i drift

1. **Varje slutrapport och tolkning anger båda axlarna**: design i rubriken
   (görs redan: "retrospektiv observation") och tillförlitlighet i
   Svar-avsnittet. Tillförlitlighetsraden läggs till nästa gång rapportmallen
   ändå rörs — inte som egen utryckning.
2. **En observationsdom (låg tillförlitlighet) stänger aldrig frågan** — den
   kvalificerar eller diskvalificerar den för en nivå 1-prövning. p00:s nej
   betyder: inte värt 24 lottade dagar på vilopuls, pröva sömnen. Det är dess
   hela auktoritet.
3. **Retrospektiva körningar följer target trial-emulering** (Hernán m.fl.):
   protokollet — tidsnoll, regel, utfall, analys — låses före beräkning, som
   p00 gjorde. Ramverket botar tidsnoll-fel men aldrig confounding; därav
   startbetyget låg.
4. **Snabbhet får bara komma från förregistrering, aldrig från iver.**
   Sekventiella gränser (§2) kortar kalendertid via i förväg låsta
   avläsningspunkter; de sänker aldrig paren under golvet och flyttar inget
   på axlarna.
5. **Grinden får vägra av underlagsskäl** — p02-stoppet är axel 2 i förväg:
   hellre en senare nivå 1-dom än en som föds obestämd.

Källor: OCEBM Levels of Evidence Working Group, "The Oxford 2011 Levels of
Evidence" (CEBM 2.1-tabellen); GRADE handbook-domänerna (BMJ-serien);
Hernán m.fl., "Target Trial Emulation" (JAMA 2022); Kravitz & Duan (red.),
*Design and Implementation of N-of-1 Trials: A User's Guide* (AHRQ 2014);
CENT 2015 (redan motorns rapportstandard).

## Byggs inte, med skäl

- **Bandit-allokering för behandlingsval** (adaptiv randomisering mot "bästa
  armen"): optimerar val, inte kunskap; svårare felkontroll; fel passform för
  bevis-varumärket innan sekventiella gränser finns.
- **LLM-bedömning i granskningen**: uppmätt sämre än deterministisk beräkning
  (RESULTAT.md: 0 mot 17–20 falska godkännanden). LLM föreslår; koden beslutar.
