# INTEGRITET — metoderna är öppna, människors data är det aldrig

Repot är publikt med avsikt: metodiken ska kunna granskas, återskapas och
stjälas med gott samvete. Människorna som mäts har inte gjort det valet.
Gränsen mellan de två är inte vaksamhet utan mekanik — det här dokumentet
definierar den, och `tests/test_integritetsvakt.py` håller den.

Revision 2026-10-28: hela git-historiken i selvra-analysis och selvra-landing
genomsökt (hemligheter, persondatafiler, e-postadresser, nycklar,
commit-meddelanden). Fynd: inga hemligheter eller persondatafiler har någonsin
committats; ett mätvärde i docs/MODELLEN.md avidentifierades samma dag.

## Gränsen

**Öppet (metoder):** all kod, dbt-modeller, tester, benchmark med syntetiska
scenarier (seed-styrda), protokoll och plandokument, mallar med fiktiva
exempel, sajten.

**Privat (människor):** allt under `data/` — databaser, råfiler, snapshots,
händelseloggar, personmappar (`person.yml`, `push.json`, Garmin-tokens,
förslag, körningar). Gitignorerat *och* vaktat: `.gitignore` är ett skydd,
integritetsvakten är beviset.

**Gråzonen är definierad bort:**

1. **Carls egna data** publiceras bara genom uttryckligt beslut per fall, och
   bara via de två sanktionerade kanalerna: `studies/` (hans studier, hans
   beslut att förregistrera öppet) och sajtens genererade siffror. Allt annat
   av hans data följer huvudregeln.
2. **Andra personers data publiceras aldrig** — inte mätvärden, inte domar,
   inte effektstorlekar, inte i docs, inte i commit-meddelanden, inte i
   benchmark-fall. En annan persons studieresultat får omnämnas publikt
   endast som processfakta utan mätvärden ("studien slutade motbevisad")
   och helst inte alls. Vill personen själv publicera är det personens
   beslut, dokumenterat, aldrig underförstått.
3. **Person-id:n i publik kod** (Makefile-exempel, cron-skript, tester) är
   neutrala: `testare-1`, `testare-2` osv (infört 2026-10-28; ett id som
   röjde en relation byttes ut i alla publika filer samma dag). Ett id som
   avslöjar vem en testare är — namn, relation, roll — är en personuppgift
   och fastnar i vakten. Människonamnet bor i personens gitignorerade
   `person.yml`, aldrig i repot.
4. **Syntetiskt är fritt** — allt som föds ur en seed får committas.

## Vakten

`tests/test_integritetsvakt.py` kör i varje CI-varv:

- inga spårade filer under `data/` (utom mall + .gitkeep), inga `.duckdb`,
  `push.json`, `person.yml`, `.pem`, `.env*`, snapshots- eller token-mappar;
- inget spårat innehåll som matchar hemlighetsmönstren (API-nycklar,
  tokens, privata e-postadresser, privata nycklar, ifyllda lösenordsvariabler);
- mallfilen förblir fiktiv (exempelmånaden mars 2025).

Faller vakten: åtgärda läckan. Mjuka aldrig upp vakten för att få grönt —
samma regel som gyllene dagen (UPPLEVELSEN §6).

## Incidentrutin (om något ändå når det öppna)

1. **Betrakta det läckta som läckt** — rotera/ogiltigförklara omedelbart
   (nycklar, tokens, lösenord), även om pushen "nog inte hanns läsas".
2. Ta bort ur arbetsträdet och historiken (`git filter-repo`), force-pusha,
   be GitHub Support rensa cachade vyer om innehållet var känsligt.
3. Berörd person informeras rakt: vad, när, vad som gjorts.
4. Lägg till ett vaktmönster som hade fångat exakt den läckan — produktions-
   misser blir vaktfall, samma logik som benchmarken (PROTOKOLL §6).

Prejudikat: `.env.save`-incidenten (oktober 2026) — en nano-backup med
hemligheter nådde ett lokalt commit; pushen stoppades av en slump,
`.gitignore` breddades samma dag (`.env.*`, `*.env.save`). Vaktens
`.env`-mönster är den incidentens permanenta minne.
