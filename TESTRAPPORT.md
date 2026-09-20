# Matchorakel – slutkontroll 2026-09-20

## Resultat och testgräns

Tolv numrerade omgångar är genomförda, med 30 nya fall per omgång utöver 199 grundfall. Slutkorpusen innehåller **559 fall**. Omgång 11 och 12 passerade hela den då befintliga korpusen utan nya fel. Dessutom passerade **49 unittest-metoder**, inklusive korpusen som subtester; dessa är inte 48 ytterligare oberoende användarsamtal.

Chromium körs mot riktig lokal Flask, med syntetiska matchfiler/modeller, vid 360, 390, 768, 1024 och 1440 px. Resultat, tidigare misslyckanden, omkörningar och skärmbilder finns i `qa/results`. Testerna omfattar navigation, historik, dialoger, favoriter, tangentbord, IME, stopp, retry, sena svar, chattbyte, flera flikar, modellrapport, 404 och horisontell overflow. Inga JavaScript-undantag rapporterades i de sista körningarna.

**Detta är inte 559 riktiga Gemini-svar.** Ingen Gemini-nyckel finns i testmiljön. Försöket att fråga den publicerade sidan gav timeout. Native Gemini-payload, kandidatparsning, safety, MAX_TOKENS, kvot, cache och felhantering har testats med kontrollerade API-svar. En frivillig live-runner med 30 frågor ingår. Kravet på riktiga Gemini-körningar är alltså inte uppfyllt här.

## Dokumenterade grundfel

Nedan räknas 24 avgränsade grundfel, inte antal symptom eller misslyckade parametriserade fall. Förebyggande skydd räknas inte som bevisade produktionsfel.

| Klass | Antal rättade | Grundfel |
| --- | ---: | --- |
| A: innehåll | 3 | Lagpar i en transferfråga blev prediction; fråga om framtida mål hamnade i historiksvar; ”släpper in” matchade ”lapp” och gav spelalternativ. |
| B: lag/input | 4 | Inter–Milan kollapsade till ett alias; `vs.` delade frågan; Athletic saknade alias; engelska orden real/nice träffade klubbar. |
| C: kontext | 3 | Motståndarkorrigering förlorade ursprungsparet; `borta mot … vad tror du?` missade prediction; redan levererad prediction föreslogs igen efter ett naket lagpar. |
| D: oväntade frågor | 3 | Väderfråga gick till fel reservväg; engelskt tack fick svenskt svar; ligavinnarfråga med `the` bad felaktigt om två lag. |
| E: teknik | 4 | Escape stängde både dialog och drawer; kopieraknapp läste currentTarget efter await; lagringshändelse kunde skriva tillbaka gammal historik; panelanrop med yttre abort saknade egen timeout. |
| F: data | 6 | Ogiltiga matchtal accepterades; oändliga/fraktionella spelartal accepterades; tom spelarfil tappade kolumner efter filtrering; null i utvärdering gav 500; spelad matchfråga kunde välja framtida möte; preliminär avspark behandlades som exakt klockslag. |
| G: AI-format | 1 | Filtret för svenska `Absolut` åt bara början av engelska `Absolutely`. |

Tre särskilt viktiga fel var förlorad matchkontext vid korrigering, framtida möte som svar på en spelad match och historik som kunde återuppstå mellan flikar.

## Omgångar och kontroller

| Omgång | Korpus efter utökning | Exempel på fynd/utökning |
| --- | ---: | --- |
| 1 | 229 | Separatorer, felstavningar, scope och dialog/drawer. |
| 2 | 259 | Öppna fotbollsfrågor, chattbyte, avbrott, lagringshändelser. |
| 3 | 289 | Athletic, framtida mål och upprepade predictions. |
| 4 | 319 | Engelska alias/fyllnadsfraser, ogiltiga CSV-värden. |
| 5 | 349 | Fler språk-, schema- och datakanter. |
| 6 | 379 | Cuporientering, spelade matcher, saknade uppgifter. |
| 7 | 409 | Engelskt tack, ligavinnare och avslutad match. |
| 8 | 439 | Bredare följdfrågor och felresponser. |
| 9 | 469 | Korrigering, insläppta mål, spelarfil och utvärdering. |
| 10 | 499 | Hemma/borta och suffixet ”vad tror du?”. |
| 11 | 529 | Nya kombinerade frågor, engelska resultatfrågor, datum. |
| 12 | 559 | Mellanslag, skador, venues, mål/kort och kontext. |

Kör `py -m unittest discover -s tests -v` och `py qa/run_cases.py --round manual`. Browser-runnern kräver Playwright och Chromium. Testdata är tydligt syntetisk och används aldrig i produktionsstarten.

## Design och Gemini

Dekorativa ligalistor, statusprickar, avatarer och etiketter är borttagna ur chatten. Tävlingar finns i Om Matchorakel. Neutral mörk palett, lokalt Inter, 768 px innehåll, mobil drawer, växande input, en följdfråga och diskreta övergångar. Dov grågrön accent används i prognosstaplar för att framhäva siffror utan att dominera chatten.

Gemini använder systemInstruction, korrekta user/model-roller, begränsad historik, låg temperatur, thinking-inställning, begränsad retry och cache. Fel loggas utan nyckel. Tal valideras mot underlaget; resultat och sannolikheter kommer från Pythonmodellen. Fullständiga svar valideras före visning, därför används inte streaming. Nuvarande `GEMINI_API_KEY` och `MATCHORAKEL_GEMINI_MODEL` behålls; ingen namnändring krävs.

## Inte verifierat / kända begränsningar

- Riktiga Gemini-svars kvalitet, safetybeteende och fördröjning efter denna uppdatering. Kontrollerade API-svar ersätter inte liveprov.
- Ingen ny träningskörning eller förbättrad träffsäkerhet på verkliga matcher har verifierats. Nedladdning av matchfiler lyckades inte i miljön. Befintliga lokala data/modeller bevaras av uppdateraren.
- Ingen publicering till ditt GitHub/Render-konto, ingen inspektion av din privata konfiguration eller fullständiga git-historik.
- Ingen fysisk iPhone/Android eller Safari: viewporttester kan inte bevisa tangentbordsbeteendet där.
- Ingen garanti för sanningen i alla fria AI-formuleringar. Sifferkontrollen verifierar förekomst, inte hela betydelsen. Inga nycklar är inkluderade i paketet.
- Aktuella startelvor, skador, xG och målskyttsmodeller saknas där datakällan saknar dem. Cupbedömningar är märkta uppskattningar från ligahistorik.
- Minnesbaserade kvoter kräver en process och nollställs vid omstart. Stopp kan inte återkalla beräkningar leverantören redan utfört.

Ingen känd blockerande regression återstår i de genomförda lokala testerna. Projektet kan inte ärligt betecknas som garanterat felfritt eller fullständigt liveverifierat.

## Visuell uppdatering efter slutkontrollen

Sidopanelen fick enhetliga linjeikoner för ny chatt, matcher, sökning, modellresultat och information. Mobilens toppfält fick en egen knapp för ny chatt. Sidopanelens avstånd, länkar och sökfält justerades; chattens rubrik, meddelanden och skrivfält verifierades mot samma mittlinje. En CSS-regel visade först mobilknappen även på desktop; detta rättades innan leverans. Chromiumkontroller 16 och 17 passerade vid 360, 390, 768, 1024 och 1440 px utan rapporterade JavaScript-fel. Samtliga 49 unittest-metoder passerade efter den visuella ändringen.

## Namnmatchning i Bundesliga

Importerat spelschema kan kalla klubben `SV Werder Bremen`, medan ligamodellen använder `Werder Bremen`. Enheten kopplas nu till samma lag vid schemafrågor. Regressionstest frågar exakt ”Borussia Dortmund mot SV Werder Bremen i Bundesliga, när spelas matchen?” med kontrollerad framtida match och verifierar hemma- och bortalag. Detta bekräftar namnmatchningen men inte att en viss användares sparade schema innehåller matchen.
