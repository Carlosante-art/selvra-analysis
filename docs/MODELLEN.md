# MODELLEN — kartan som syr ihop allt

De andra dokumenten är konstitutioner för var sitt lager: benchmark/PROTOKOLL.md
för metodiken, docs/UPPLEVELSEN.md för det som når en människa, docs/METODPLAN.md
för statistikens nästa steg. Det här dokumentet är kartan ovanför dem: vad
modellen *är*, i vilken ordning den byggs, och hur den förbättrar sig själv.
Läses i början av varje session som rör riktning. Uppdateras när ett lager
byter läge — inte oftare.

Senast uppdaterad: 2026-10-28.

## Modellen i en mening

Selvra gör vardagsdata till bevisade svar om en person — domar, inte insikter —
och håller tyst när täckning saknas. Positionen (kanon): *Selvra är ett
protokoll med stora databaser, som connectas med MCP:er. Selvra-app är dess
första klient. Selvra Diabetes är dess första vertikal.*

## Lagren

| # | Lager | Vad det är | Läge 2026-10-28 |
|---|-------|-----------|------------------|
| L0 | **Data** | Källor → raw → marts per person (Dexcom Share, Nightscout, Garmin; dbt-kontrakt, 159 tester) | Live, n=2 (Carl CGM+klocka, testare-1 klocka) |
| L1 | **Motor** | fråga → granska → lås → kör en gång → dom (block bootstrap, randomiseringstest, negativ kontroll, styrka ur egen variation) | Live, benchmarkad (motortest, chaos monkey, LLM-arm) |
| L2 | **Upplevelse** | brev, push, morgonvy, förslagsgrind, språkgrind | Live; grindad (gyllene dagen, make syn) |
| L3 | **Distribution** | selvra.ai, studiesidan (ScholarlyArticle, engelska), Substack | Sajt live; Substack vilande (Carls beslut) |
| L4 | **Integration** | MCP-läslager (andra system frågar Selvra), protokollskrivning | Byggs ej ännu; ~/selvra på is tills tenant-spärr |

Värdet flödar nedifrån och upp: utan L0-baslinje ingen L1-dom, utan dom inget
att visa i L2/L3, utan domregister inget värt att integrera i L4. Därför byggs
och förbättras lagren i den ordningen när de konkurrerar om tid.

## Bevisat hittills (därför är modellen trovärdig)

- Motorn fäller hellre än friar: första förslagsstudien på en wearable-person
  (p00) slutade **motbevisad** med negativ kontroll godkänd — och domen
  skickades till personen som den var. (Mätvärdena är personens egna och bor i
  den gitignorerade personmappen, inte här — se docs/INTEGRITET.md.)
- Granskaren stoppar på riktigt: p01 stoppad (1 väntat komplett par av 12),
  rate-fix skrotad när datan inte bar.
- Benchmarken biter sin författare: f17/f18-cykeln, styrka-rättningen,
  LLM-jämförelsen (0 falska godkännanden mot 13–20 för råa modeller).
- Onboarding av person nr 2 tog en kväll; första dom inom ett dygn
  (retrospektivt) tack vare wearable-only-läget.

## Planen — grindar, inte datum

Varje steg har en grind som öppnar nästa. Datum är prognoser; grindarna är
beslut.

**Nu (oktober–november 2026)**
1. **Testare-1:s p02 (promenad → sömn)** genom hela cykeln: inbjudan → lås → 24
   studiedagar → dom. Grind: testare-1 tackar ja. Detta är modellens första
   *prospektiva* n=1 på en wearable-person — hela kedjan på riktigt.
2. **Carls klocka (torsdag)** → hans steg/sömn/puls-baslinje börjar växa →
   studie 003 (träning, prospektiv) designas när granskaren släpper igenom.
3. **Sekventiella stoppregler** (METODPLAN §2) — största enskilda
   UX-förbättringen: kortare tid till dom utan att fella felrisken. Byggs
   fall-först enligt PROTOKOLL. Grind: p02/003 behöver den på riktigt.
4. **dold4** författas av någon som inte sett styrka/strata-fixarna (inte
   Claude i denna session). Grind för varje framtida motorändring.

**Nästa (vintern 2026/27)**
5. **n = 3–5**: fler personer (vänner/familj, Garmin/klocka räcker).
   Onboarding är redan ~15 min + cron. Grind: p02 har visat att en
   wearable-person kan gå hela varvet utan Carl som driftstekniker.
6. **Hierarkisk styrkedelning** (METODPLAN §3) när minst två personer har
   körda studier — individer lånar styrka utan att dela rådata.
7. **MCP-läslager** (L4): läs-bara verktyg ovanpå körjournaler och marts, så
   att andra system kan fråga "vad är bevisat?". Grind: de tre filtren
   (pilot-blocker? efterfrågan? bandbredd?) måste säga ja — byggs inte på
   spekulation.

**Sedan (2027)**
8. **iOS/HealthKit H1 2027** (Framna-beslutet ligger hos Carl) — tar bort
   Garmin-inloggningen som friktionsgolv och öppnar Apple Watch-världen.
9. **Pilot Selvra Diabetes** — tekniskt redo sedan maj; externa blockers är
   Carls (kliniska kontakter). Motorn fortsätter bevisa sig på n=2–5 under
   tiden.
10. **Vertikaler bortom hälsa** (ERP/Business-sporet) — först när domregistret
    och MCP-lagret finns. "Ditt data vet redan svaret. Selvra bevisar det"
    gäller även en verksamhet — men inte före bevis på människor.

## Förbättringsloopen — hur modellen förbättrar sig själv

"Hela tiden förbättra" är inte ambition utan mekanik; varje lager har sin loop:

- **L1:** produktionsmissar blir benchmarkfall (PROTOKOLL §6); varje
  motorändring möter fall-först + motortest + chaos monkey; dolda uppsättningar
  förbrukas och ersätts blint.
- **L2:** gyllene dagen-testet i CI + `make syn` före deploy + språkgrinden i
  körning. Assertioner mjukas aldrig upp i smyg (UPPLEVELSEN §6).
- **Kunskap:** varje dom skrivs till Dreamers minne → nästa förslag ställer en
  bättre fråga. Registret av domar *är* produkten som växer.
- **Metod:** METODPLAN:s prioritering styrs av verkliga studiers behov, aldrig
  av vad som är intressant.

## Vad vi säger nej till (lika viktigt som planen)

- **Tre filter före allt nytt:** pilot-blocker? klinisk/verklig efterfrågan?
  bandbredd? Minst ett ja, annars nej.
- **Slowburn-pakten:** konstitution före tillväxtkurva. Aldrig push, streaks,
  scores, FOMO. Framsteg mäts i tid *utanför* appen.
- **Repo-fokus:** selvra-analysis + selvra-diabetes. ~/selvra rörs inte före
  tenant-spärren.
- **Byggs inte-listan** (METODPLAN): bandit-allokering, LLM-bedömning i
  granskningen. LLM föreslår; koden beslutar.

## Måtten som räknas

Inte MAU. I ordning:
1. **Tid till första dom** per ny person (nu: ~1 dygn retrospektivt, mål:
   dagar även prospektivt via sekventiella gränser).
2. **Domar i registret** (nu: 3 körda studier, varav 1 motbevisad — nejen
   räknas lika mycket).
3. **Andel dagar med giltig data** per person (synkvakt försvarar den).
4. **Benchmarkens träffsäkerhet** (falska godkännanden = 0 försvaras).

## Ändringslogg

- 2026-10-28: Första versionen.
