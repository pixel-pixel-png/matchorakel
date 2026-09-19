# Matchorakel V8 – samtalskontroll

Genomförd 19 september 2026 med konstgjorda, framtida testmatcher. Inga verkliga tränade modeller eller privata API-nycklar användes.

| Kontroll | Antal | Resultat |
| --- | ---: | --- |
| Flerturssamtal, ordinarie regressionskontroll | 50 | 50 gick igenom, 3 meddelanden per samtal |
| Adversariella samtal, separat provning | 195 | 76 fick det svar som förväntades utan språkmodell |
| Fria frågor utanför fotboll i den adversariella provningen | 120 | 119 fick begränsningsmeddelandet: ingen språkmodell ansluten |
| Arenafrågor om exempelmatchen | 20 | 20 rätt svarstyp och trolig hemmaarena |
| Datumfrågor om exempelmatchen | 20 | 20 rätt svarstyp |
| Byten från Champions League till La Liga | 15 | 15 rätt liga |
| Frågor med flera delar | 20 | 20 fick svar på delarna |
| Automatiska regressionstester | 19 | 19 godkända |

Under felsökningen framkallades mer än 100 otillräckliga svar. De var **inte över 100 skilda kodfel**: majoriteten var olika fria frågor med samma underliggande begränsning, nämligen att ingen språkmodell var ansluten. Kodfel som hittades och rättades omfattade kvarhängande UCL-kontext, saknade sociala svar, förväxlade ligor, frågor om datum eller arena som blev prognoser, analyser utan vald UCL-match, sammansatta frågor och flera meningar som tappade kontext.

För fri konversation måste en lokal Ollama-modell installeras eller en egen `OPENAI_API_KEY` anges. Appen ansluter automatiskt till en redan installerad Ollama-modell; API-anrop och konversationshistorik har provats med en simulerad lokal modell. **Modellens verkliga samtalskvalitet och matchdata på användarens Windows-dator kan inte verifieras från den här testmiljön.** En ansluten modell kan fortfarande göra fel. Fotbollsprognoserna validerades inte mot nya verkliga matcher i detta samtal.

`py tests/manual_adversarial.py` kör de 195 adversariella testdialogerna. Alla använder tillfälliga fixtures. `py -m unittest discover -s tests -v` kör regressionstesterna.
## Kontroller för version 10

28 automatiska tester passerar i denna version, inklusive samtalssekvensen ”hej hur mår du idag” → ”bra tack”, Barcelona–PSG utan spelschema → ”i Champions League”, ”Atlético” som lagnamn och rättelse, uppföljningsfrågan ”vem gör mål tror du” efter Sevillas och Barcelonas skottstatistik, samt högre målgränser från validerad målmodell eller tydligt angiven historik. Ett simulerat `HTTP 401` från språkmodellen ger en felsignal i serverloggen utan att skriva ut API-nyckeln. För riktig fri chatt på Render krävs att `GROQ_API_KEY` finns i tjänstens Environment; den kontakten kan bara kontrolleras med ägarens nyckel efter publicering.

I denna version passerar 28 tester, `node --check static/script.js` och två simulerade gränssnittstester. Bland kontrollerna finns HTTP för chatt, begränsning per besökare, blockering av administratörens uppdatering på publika sidan och en simulerad hostad AI som får tidigare repliker utan att API-nyckeln skickas i frågetexten. Samma chatt visar samtal, förslag och matchfrågor. Extern Render-publicering och ett skarpt Groq-anrop kan först testas när ägarens konto och en giltig privat nyckel anslutits; en lyckad simulering bevisar inte att nyckeln i Render fungerar.
