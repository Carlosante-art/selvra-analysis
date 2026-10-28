# UPPLEVELSEN — regler för allt som når en människa

PROTOKOLL.md skyddar metodiken. Det här dokumentet skyddar upplevelsen: breven,
notiserna, tolkningarna, morgonvyn, sajten. Reglerna är skrivna innan pressen
kommer, så att varje framtida ändring läses mot dem — inte mot smak för dagen.

Principen bakom alla åtta: **cleant förblir cleant när fulhet inte kan passera
en grind.** Skönhet som bara bevakas med omdöme förfaller; skönhet med tester
består.

## 1. Tystnad före brus

Motorn säger bara något när den har täckning. Ett morgonbrev utan nya värden
säger det rakt ut. Förslagsgrinden tänder inbjudan först när granskaren
godkänner — fram tills dess: inte ett ord. En pågående studie tjatas aldrig om.
Tystnad är inte ett felläge, det är standardläget.

## 2. Varje mening är mall eller grindad

Text som når en människa är antingen (a) deterministisk mall skriven av en
människa och testad i CI, eller (b) AI-text som passerat **språkgrinden**
(`sprakgrind.granska_text`): inga mätvärden som saknas i källdokumenten, inget
rådgivningsspråk, längdtak. Underkänd AI-text skickas aldrig — reserven är
rapportens eget, motorskrivna svar. Det finns ingen tredje kategori.

## 3. Varje tal är spårbart

Ett tal i ett brev, en notis eller på sajten ska gå att följa till en
körjournal, en mart eller ett rått mätvärde. Sajtens siffror genereras
(`generate.py` felar högt om markörer saknas), aldrig handskrivna. Ett tal som
inte kan spåras är ett tal som ska bort.

## 4. Beskriva och bjuda in — aldrig råda

"Garmin mätte vilopulsen till 51" — ja. "Du borde röra på dig mer" — aldrig.
Rådgivningsspråk stoppas maskinellt (språkgrindens förbjudna ordlista), men
regeln gäller även mallarna: nya mallar skrivs beskrivande, och inbjudningar
formuleras som frågor personen kan tacka nej till.

## 5. Mot ditt eget normala, aldrig en norm

Band och jämförelser byggs av personens egen historik (P10–P90, rullande
fönster, median under uppbyggnad) — aldrig befolkningsreferenser. Innan
baslinjen bär (STAGE2_DAYS) sägs det ärligt: "hittills brukar det vara …
(N dagar)". Relevans är arkitektur, inte kuratering: en rad visas bara när
dess data finns (`utfallsgiltig`), och saknad data sägs som saknad.

## 6. Gyllene dagen bryts aldrig

`tests/test_gyllene_dagen.py` kör hela morgonen end-to-end: syntetisk person →
duckdb → brev → payload → grind. Rätt fakta, rätt ordning, varning när klockan
tystnat, rådfritt språk. Ändringar i kedjan som får testet att falla ändrar
upplevelsen — då ändras testet medvetet i samma PR, aldrig genom att
assertionerna mjukas upp i smyg.

## 7. Ögon på varje yta

`make syn` renderar morgonvyn och selvra.ai i mobil- och desktopbredd till
`data/syn/`. Körs efter varje HTML/CSS-ändring; skärmbilderna granskas innan
deploy. Layoutbrott ska upptäckas där — inte på en telefon av en människa som
inte bett om att vara testare.

## 8. En yta per person, och friktion med avsikt

Pappa har notisen och morgonsidan — inte terminalen, inte dashboarden, inte
repo:t. Nya ytor läggs bara till när en fråga inte ryms i de som finns.
Flödet är friktionsfritt; konsekvens har avsiktlig friktion (att låsa en
studie kräver ett aktivt ja till Carl, aldrig ett tryck i en notis).

---

*Tillkom 2026-10-28, samtidigt med språkgrinden, gyllene-dagen-testet och
`make syn`. Ändringar i det här dokumentet loggas nedan.*

## Ändringslogg

- 2026-10-28: Första versionen, åtta regler.
