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
# Kontroller för version 9

Den publika varianten har testats med `python -m unittest discover -s tests -q`: 22 tester passerar, inklusive HTTP för chatt, begränsning per besökare, att administratörens uppdatering blockeras och en simulerad hostad AI som får tidigare repliker utan att API-nyckeln skickas i frågetexten. `node --check static/script.js` passerar. Ett webbläsarsimulerat gränssnittstest bekräftar att vanligt samtal, förslag och matchfråga ligger i samma chatt och att dataverktygen döljs för publika besökare. Extern Render-publicering och ett skarpt Groq-anrop kan först testas när egna konton och en giltig privat nyckel anslutits.
