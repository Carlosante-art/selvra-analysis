# Studiedesign inför varje studie

Kunskapsbasen bakom designgranskningen. Den läses av skillen [`/ny-studie`](../.claude/skills/ny-studie/SKILL.md) och av granskaragenten [`studiegranskare`](../.claude/agents/studiegranskare.md) före varje studie. Det som kan räknas ut räknas av [`granska.py`](../src/selvra_analysis/granska.py), likadant varje gång, och `las` vägrar utan en godkänd granskning av exakt den versionen av filen.

Sammanställd 2026-10-27 från tre genomgångar av primärkällor. Allt märkt **[overifierat]** kommer från bakgrundskunskap och har inte lästs i en hämtad källa. Ska inte behandlas som fastslaget.

## Varför

Det första utkastet till 10 000-stegsstudien jämförde ≥10 000 steg med ≤5 000 steg på vilka dagar som helst. Carl går 10 000+ på arbetsdagar och omkring 3 500 på lediga. Det bröt två villkor samtidigt:

- **Positivitet.** B (få steg) går inte att göra på en arbetsdag, och A förekommer inte naturligt på en ledig.
- **Utbytbarhet.** Arbetsdagen påverkar både stegen och glukosen (måltider, stress, sömn, insulin).

Utöver det låg perioderna på intilliggande dagar, trots att insulinkänsligheten efter träning håller i sig 24–48 h. Den nattliga negativa kontrollen ("natten kommer före dagens steg") låg därmed i föregående A-dags eftereffekt.

Ingen av de publicerade guiderna (SPENT, CENT, SCRIBE, WWC) eller verktygen (StudyU, Self-E) kontrollerar positivitet per dagstyp, överföring mot mekanism eller minsta möjliga p. Det är det gapet granskningen fyller.

## Arbetsgången

1. **Intervjun** (skillen): frågorna nedan, i ordning. Svar som kan hämtas ur data hämtas ur data, inte ur minnet (Self-E: 15 av 16 deltagare designade före/efter-jämförelser och bara 3 tänkte på helger som störfaktor).
2. **Filen**: `studie.yml` skrivs med svaren.
3. **Maskinkontrollen**: `python -m selvra_analysis.granska <fil>` skriver `granskning.json`. STOPP blockerar låsning; varje VARNING ska bemötas i filen.
4. **Oberoende granskning**: agenten `studiegranskare` läser filen utan att ha sett intervjun och letar fel.
5. **Låsning**: Carls beslut, aldrig agentens.

## Frågorna

Varje fråga anger vad den skyddar mot och vad som görs om svaret är dåligt. Koderna (F1, C2 …) följer forskningsanteckningarna.

### 1. Fråga, tes, motbevis

| # | Fråga | Skyddar mot | Om svaret är dåligt |
|---|---|---|---|
| Q1 | Vad vill du veta, som ett tal? ("Hur mycket lägre medelglukos 07–24 …") | Vaga mål ("må bättre") | Skriv om tills frågan besvaras av en skattning med intervall |
| Q2 | Vilket resultat skulle få dig att ändra vad du gör? | En minsta relevanta effekt som valts för att den är lätt att nå | Den effekten blir `minsta_relevanta_effekt`; motbeviset formuleras ur den |
| Q3 | Kan A manipuleras, eller bara observeras? | Att kausala anspråk görs på observationsdata | Går den inte att styra (stress, sjukdom): observation, och anspråket blir "samband" |

### 2. Villkoren (A och B)

| # | Fråga | Skyddar mot | Om dåligt |
|---|---|---|---|
| I1 | A och B som dos + tid + längd, mätbart med en apparat | Villkor som inte går att verifiera (SPENT 11a, CENT 5, SCRIBE 16) | Numerisk tröskel, tidsfönster och datakälla → `design.foljsamhet` |
| F4 | Är B en egen handling, eller bara frånvaron av A? Vad gör du i stället? | Glidande jämförelse (Self-E) | Beskriv B konkret, med tak |
| I2 | Vad räknas som avvikelse? | Efterhandsomklassning | Regeln i `foljsamhet`; analysen följer lottningen (intention-to-treat), följsamheten redovisas bredvid |
| I3 | När på dygnet börjar A verka? | Ett utfallsfönster före interventionen | `design.verkan.borjar`; maskinen kontrollerar ordningen |
| I4 | Vad ska hållas konstant: insulinregler, måltider, koffein, alkohol, sömn? | Samtidiga ingrepp och kompensation | Lås reglerna i protokollet eller logga dem som sekundärutfall |
| I6 | Ändrar vetskapen om dagens villkor annat beteende? | Förväntan och reaktivitet utan blindning | Avslöja villkoret så sent som möjligt (morgonen samma dag); hela schemat hålls dolt |

### 3. Positivitet och dagstyper

**Positivitet:** varje exponeringsnivå måste vara möjlig på varje nivå av störfaktorerna (Daza 2018). Strukturella brott kan inte modelleras bort; anspråket måste begränsas (Petersen m.fl. 2012).

| # | Fråga | Skyddar mot | Om dåligt |
|---|---|---|---|
| F1 | Hur ofta gjorde du A respektive B de senaste 8 veckorna, per dagstyp? **Ur data.** (`granska` gör det) | A eller B omöjligt på vissa dagar | Begränsa `design.dagar` till dagstyper där båda går, eller definiera om villkoret relativt dagstypen (t.ex. A = +4 000 steg över dagstypens egen nivå) |
| F2 | Vilka dagar är tillåtna, och kan du göra A eller B på vilken som helst av dem, enbart styrt av lotten? | Deterministisk tilldelning bakom en lottning | Snävare dagar; tillåtna dagar bestäms **före** lottningen (från schemat), aldrig "hoppa över om jag mår dåligt" |
| F2b | **Rullande schema:** vilka dagar är lediga, enligt schemat, och hur långt fram är det känt? | Veckodag som dagstyp när den inte säger något | `design.dagar.datum` = lediga dagar ur schemat, satt före lottningen; `minsta_avstand` sprider dem enligt verkan (träning 3). Logga passen som händelse `arbete` (`make import-kalender`), annars kan `granska` bara gissa dagstyp ur veckodag |
| F3 | Vad skiljer annars dina naturliga A-dagar från B-dagar? | Att arbetsdag jämförs med ledig dag i stället för steg med steg | Par inom samma dagstyp; negativ kontroll som följer dagstypen men inte interventionen |
| F5 | Ligger ditt naturliga beteende redan på A eller B? | Att kontrasten bara skapas genom att trycka ned beteendet, eller att B är skadligt | Kontrasten relativt egen baslinje; kontrollera att den fortfarande når minsta relevanta effekt |
| F6 | Om en dag blir omöjlig (sjuk, resa): stryks paret, ersätts det, eller analyseras det som lottat? | Ad hoc-uteslutning | Förregistrera: paret faller bort; inget ersättningspar utanför schemat |

Kostnaden för att begränsa dagarna: färre tillåtna dagar sträcker ut kalendern (säsong, drift), och skattningen gäller bara de dagarna. Begränsad randomisering kan också sänka styrkan kraftigt (Manolov & Tanious 2024: 0,72 mot 1,00 vid 10 % slumpvariation). Referensfördelningen i testet måste vara exakt den lottning som gjordes (Edgington & Onghena **[overifierat]**; Manolov & Solanas 2008). Motorn gör så: tecken byts bara inom par.

### 4. Överföring, tvätt och periodlängd

n-of-1 passar behandlingar med snabb verkan och kort eftereffekt vid stabila tillstånd (AHRQ). Eftereffekt är interferens över tid (Daza 2018). Tvätten mäts på utfallets klocka, inte kalenderns.

| Verkan (`design.verkan.typ`) | Eftereffekt | Kontroll i `granska`: kalenderdagar mellan analyserade dagar |
|---|---|---|
| `traning` | Insulinkänsligheten förhöjd upp till 24–48 h, hypoglykemirisk minst 24 h, nattlig risk störst efter eftermiddagsträning (Riddell 2017) | STOPP under 2, VARNING under 3 |
| `alkohol` | Fördröjd hypoglykemi morgonen efter, signifikant 07–11 (White 2017, om Lange och Turner) | STOPP under 2 |
| `somn` | En natt med 4 h sömn: glukosupptaget cirka 20 % lägre och den egna glukosproduktionen cirka 22 % högre dagen efter (Donga 2010, friska; T1D-studien **[overifierad]**) | VARNING under 2 |
| `maltid` | Kort för en enskild måltid; en kvällspromenad kan ändå höja känsligheten över natten | inget krav |

| # | Fråga | Om dåligt |
|---|---|---|
| C1 | Hur snabbt börjar och slutar effekten? Mekanism och tidsskala | Periodlängd ≥ verkan + stabilisering; tvätt ≥ avklingning |
| C2 | Kan effekten bestå (träningsanpassning, vikt, inlärning)? | Flerdagsblock per villkor; ett steg-mål liknar höjd daglig energiförbrukning mer än enskilda pass, så block om ≥1 vecka kan passa bättre än växling dag för dag |
| C3 | Är tillståndet stabilt under studien (ingen planerad terapiändring, ny pump eller sensormodell, säsongsskifte)? | Skjut upp eller korta |
| C4 | Ligger dag t:s utfallsfönster inom dag t−1:s eftereffekt? | Tvättdagar eller flytta fönstret |
| C5 | Inlärning, tillvänjning eller nyhetseffekt? | Balanserade par; redovisa AB mot BA |

### 5. Utfallet

| # | Fråga | Om dåligt |
|---|---|---|
| O1 | Ett primärt mått och ett lokalt tidsfönster, och varför just det fönstret? | Lås ett; övriga är explorativa |
| O2 | Fångar fönstret mekanismen? G7 har cirka 3,5 min sensorfördröjning plus 5–10 min fysiologisk (Garg 2022; tillverkarmaterial) | Fönster ≥ 1–2 h; för korta exponeringar förläng 15–30 min efter |
| O3b | Kommer mätningen från en och samma apparat hela studien? Oura och Garmin räknar steg olika, och `hr_lowest_bpm` är nattens lägsta på Oura men dygnets vilopuls på Garmin | En apparat; `granska` varnar om historiken blandar `wearable_source` |
| O3 | Hur mycket varierar måttet dag till dag utan ingrepp? (`granska` räknar) | Mått närmare mekanismen, längre fönster eller fler par |
| O4 | Vilken täckning krävs per fönster? | ≥70 % per fönster (Battelinos 70 % anpassat; konsensus gäller 14 dagar, inte korta fönster) |
| O5 | Negativ kontroll: något A inte kan påverka men som samma störfaktorer påverkar? | Fönster före `verkan.borjar` samma dag, och utanför föregående exponerings eftereffekt (`granska` kontrollerar båda) |
| O6 | Vilket resultat hoppas du på, och vad skulle du göra annorlunda på A-dagar? | Objektivt mått; schemat dolt till dagen; logga kolhydrater och insulin |
| O7 | Kan insulin eller kolhydrater ta upp effekten? | Insulin- och kolhydratsummor som obligatoriska sekundärutfall |

**Sensordagar.** G7, MARD per bärdag (arm/buk): dag 1 11,9/12,9 %, dag 2 8,4/8,6 %, dag 4 7,2/7,7 %, dag 10 7,6/9,3 % (Garg 2022). Vid 40–60 mg/dL: %15/15 bara 85,1/77,1 %. Battelino 2023: kasta inte de första 12–24 h och inte kompressionsartefakter; gör känslighetsanalys. Blanda aldrig G6 och G7 i en studie.

**Battelino 2023:** natt 00:00–05:59, dag 06:00–23:59. Kärnmått: TIR 3,9–10, TBR <3,9 och <3,0, TAR >10 och >13,9, medel, SD, CV. Kliniskt meningsfull individuell förändring: ≥5 procentenheter TIR. Över ett 3-timmarsfönster är 5 procentenheter bara cirka 9 minuter, så medelglukos är oftast känsligare där.

### 6. Antal par, styrka, analys

| # | Fråga | Om dåligt |
|---|---|---|
| S1 | Hur många giltiga par efter väntat bortfall, och når minsta möjliga p (2/2^k) under α? | Fler par. k = 5 ger 0,0625 tvåsidigt, så minst 6 krävs (motorn kräver 6) |
| S2 | Styrka mot egen variation och minsta relevanta effekt? (`granska` simulerar) | Fler par, mindre brus, eller gör det till en skattningsstudie och säg det i tesen |
| S3 | Permuterar analysen exakt lottningsschemat? | Schemat lottas en gång vid låsning med fröet sparat; ingen omlottning |
| S5 | Väntade trender (säsong, sensorålder, kondition)? | Intilliggande par; studier över fyra månader får VARNING |
| S7 | Kommer du titta på resultat under studien? | `status` visar aldrig effekten; ingen interimsanalys |

**Väntade effektstorlekar (priors):**
- T1DEXI, cirka 30-minuterspass hemma: aerobt −18 ± 39 mg/dL (≈ −1,0 mmol/L), intervall −14 ± 32, styrka −9 ± 36 under passet. TIR 24 h efter: 76 % mot 70 %. Spridningen är ungefär dubbla medeleffekten, vilket kräver många par.
- Promenad efter måltid mot stående: d = −0,30 (Buffey 2022, mest överviktiga utan diabetes).
- T1D med hybrid closed-loop, 20 min promenad före middag: TIR −2 till +4 h 79,3 % → 84,9 % (Turner 2023, n = 11, masteruppsats). På MDI kan effekten vara större.
- Ett heldagsmått som medel 07–24 för ett stegmål: några mg/dL upp till cirka 1 mmol/L är rimligt. Dag-till-dag-SD är ofta 1,5–3 mmol/L **[overifierat]**. Därför avgör `granska` med Carls egna data.

### 7. Säkerhet

Fasta regler, inte förhandlingsbara i en studie:
- **Aldrig studievariabel utan vården:** basal- eller bolusdoser, kolhydratkvot, korrektionsfaktor, att hoppa över eller skjuta upp insulin, fasta med insulin ombord, alkohol som "dos", regler för behandling av hypoglykemi.
- Insulin doseras enligt Carls vanliga, med vården överenskomna, praxis. Avvikelser loggas och lottas aldrig.
- CGM-larm på under hela studien. Lita på Dexcoms larm.

**Före varje träningsdag/A-dag med aktivitet** (Riddell 2017):

| Startglukos | Regel |
|---|---|
| < 5,0 mmol/L | 10–20 g glukos, vänta tills > 5,0 |
| 5,0–6,9 | 10 g före aerobt arbete |
| 7–10 | Målintervall för start |
| 10,1–15 | Aerobt kan starta |
| > 15 oförklarat | Ketoner: ≤1,4 bara lätt < 30 min; **≥1,5 kontraindicerat**; ≥3,0 akut |

Allvarlig hypoglykemi senaste 24 h är kontraindikation.

**Stoppregel** (paus och genomgång):
- Allvarlig hypoglykemi.
- Ketoner ≥1,5 eller DKA.
- ≥1 händelse nivå 2 (<3,0 mmol/L ≥15 min, Battelino 2023) som kan kopplas till A.
- Nattlig TBR i A-armen tydligt över baslinjen (>4 % <3,9 eller >1 % <3,0).
- Upprepat behov av kolhydrater under eller efter passen.

**Involvera vården** när:
- Ett villkor rimligen kräver insulinjustering (≥60 min, intensivt, kvällspass).
- Alkohol är exponering, eller det handlar om fasta eller mycket lite kolhydrater.
- Han nyligen haft återkommande eller allvarliga hypoglykemier.
- Villkoret höjer den nattliga risken och han sover ensam.

**Etik:** forskning på sig själv utan publicering är i regel utanför etikprövningslagen. Publicering eller fler deltagare ändrar det; fråga Etikprövningsmyndigheten.

### 8. Observationsstudier

Exponeringen styrs inte, så anspråket är alltid "samband". Krav och tekniker (Daza 2019; Lipsitch 2010 **[overifierat]**):
- **Jämför inom dagstyp.** `granska` varnar om helgandelen skiljer mer än 25 procentenheter mellan exponerade dagar och jämförelsedagar, och stoppar över 50: då följer exponeringen dagstypen och observationsdata kan inte skilja dem åt (strukturellt positivitetsbrott). Det gäller t.ex. `hoga_steg` för den som går 10 000 på arbetsdagar. Skannern jämför därför bara inom vardag och inom helg.
- **Placebodatum.** Kör samma analys på dagen *före* händelsen. En "effekt" där tyder på selektion eller omvänd orsak.
- **Omvänd orsak.** Förutsäger gårdagens glukos dagens exponering ("dålig dag → långpromenad i morgon")?
- **Regression mot medelvärdet.** Loggas händelser efter extrema dagar? Jämför baslinjen före händelsen med helheten.
- **Säsong och brott.** Bryt vid sensor-, insulin- och pumpbyten.
- **Passiva exponeringar** (steg, sömn ur apparat) före manuella loggar.
- **När ett samband ska prövas i ett experiment:** exponeringen går att styra, båda villkoren går att göra på någon dagstyp, kontrollerna flaggade inget som lottning inte löser, och det finns tillräckligt många tillåtna par.

**Formuleringsmallar:**
- Observation: "Under [kontext] hade dagar efter [händelse] [mått] X mot Y på jämförbara dagar (samband; ej prövat kausalt; möjlig störning av …)."
- Experiment: "I k lottade par på [tillåtna dagar] ändrade [protokoll A] mot [protokoll B] [mått] med Δ (intervall …, p …). Gäller [dagstyp] och protokollet så som det genomfördes."

Källattribuering i all text ("Dexcom visade …", "Oura räknade …").

## Kända luckor

- Ingen källa ger tvättlängd för korsade träningsförsök specifikt i T1D. 24–48 h kommer från insulinkänslighetens varaktighet (Riddell 2017).
- Ingen dos–respons glukos per 1 000 steg i T1D hittades.
- Inga CGM-effektstorlekar för kvällsalkohol hittades.
- RoBiNT-skalans exakta formuleringar, Moser 2020 (EASD/ISPAD om CGM och träning) och ADA Standards of Care 2026 har inte lästs **[overifierat]**.
- Täckningskravet 70 % per kort fönster är en anpassning, inte konsensus.

## Källor

- Porcino AJ m.fl. SPENT 2019. BMJ 2020;368:m122. [PDF](https://www.nof1sced.org/_files/ugd/75c51c_d660ca3443f54b96833f1a499eec76ca.pdf)
- Shamseer L m.fl. CENT 2015 E&E. BMJ 2015;350:h1793. [PDF](https://www.nof1sced.org/_files/ugd/75c51c_fe07a98028fb463886e83d0b84c53c37.pdf)
- Kravitz RL, Duan N (red.). Design and Implementation of N-of-1 Trials: A User's Guide. AHRQ 2014. [PDF](https://www.aafp.org/content/dam/AAFP/documents/patient_care/nrn/design-implementation-n1-trials.pdf)
- Tate RL m.fl. SCRIBE 2016 E&E. Arch Sci Psychol 2016;4:10–31. [PDF](https://open.bu.edu/bitstreams/024cc964-c8f3-4f8c-ae6e-ab22a76439fd/download)
- Kratochwill TR m.fl. Single-Case Designs Technical Documentation. WWC 2010. [PDF](https://files.eric.ed.gov/fulltext/ED510743.pdf)
- Daza EJ. Causal analysis of self-tracked time series data … Methods Inf Med 2018. [Författarversion](https://statsof1.netlify.com/2018_daza_latexversion.pdf)
- Daza EJ. Person as Population. arXiv:1901.03423. [arXiv](https://arxiv.org/abs/1901.03423)
- Petersen ML m.fl. Diagnosing and responding to violations in the positivity assumption. Stat Methods Med Res 2012;21:31–54. [Länk](https://journals.sagepub.com/doi/10.1177/0962280210386207)
- Manolov R, Solanas A. Randomization tests for ABAB designs. Psicothema 2008;20:297–303. [PDF](https://www.psicothema.com/pdf/3464.pdf)
- Manolov R, Tanious R. Behav Res Methods 2024;56:3637–3657. [PDF](https://diposit.ub.edu/dspace/bitstream/2445/220837/1/836581.pdf)
- Heyvaert M, Onghena P. J Contextual Behav Sci 2014;3:51–64. [Länk](https://contextualscience.org/publications/randomization_tests_for_singlecase_experiments_sta)
- Daskalova N m.fl. Self-E. CHI '21. [PDF](https://jeffhuang.com/papers/SelfE_CHI21.pdf)
- Konigorski S m.fl. StudyU. JMIR 2022;24:e35884. [PDF](https://jmir.org/2022/7/e35884/PDF)
- Riddell MC m.fl. Exercise management in type 1 diabetes. Lancet Diabetes Endocrinol 2017;5:377–390. [PDF](https://ddg.info/fileadmin/user_upload/Riddel_Exercise_Management_in_type_1_diabetes_Lancet_2017.pdf)
- T1DEXI, Diabetes Care. [Figur](https://diabetesjournals.figshare.com/articles/figure/The_Type_1_Diabetes_and_EXercise_Initiative_T1DEXI_Examining_the_acute_glycemic_effects_of_different_types_of_structured_exercise_sessions_in_type_1_diabetes_in_a_real-world_setting/21799550/3)
- Buffey AJ m.fl. Sports Med 2022;52:1765–1787. [PubMed](https://pubmed.ncbi.nlm.nih.gov/35147898/)
- Turner LV. The Timing of Walking and Post-Meal Blood Sugar Levels in Adults with T1D. York University 2023. [Länk](https://yorkspace.library.yorku.ca/items/45a24ad2-b616-4d16-a1f8-c8cc7bbf79f3/full)
- White ND. Alcohol Use in Young Adults With T1D. Am J Lifestyle Med 2017;11:433–435. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6125008/)
- Donga E m.fl. JCEM 2010;95:2963–2968. [Länk](https://academic.oup.com/jcem/article/95/6/2963/2598601)
- Garg SK m.fl. Dexcom G7 accuracy. Diabetes Technol Ther 2022;24:373–380. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9208857)
- Battelino T m.fl. CGM metrics for clinical trials. Lancet Diabetes Endocrinol 2023;11:42–57. [PDF](https://www.binasss.sa.cr/bibliotecas/bhm/ene23/46.pdf)
