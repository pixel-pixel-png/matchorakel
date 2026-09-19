# Testprotokoll — Matchorakel V12

Testat lokalt 19 september 2026. En kartläggning omfattade Flask-routes, ligamodeller, målmodell, cupscheman, språkmodell, svarskontext, CSS och JavaScript. Rättelserna omfattar validering av felaktig JSON och saknad schemadata, missvisande svar om xG/kort/skott, tyst UI-låsning vid tomt serversvar, avbrutna anrop, ogiltig utvärderingsfil och en 404-sida.

- `python -m unittest discover -s tests -q`: 46 regressioner godkända, inklusive 36 varierade kvalitetsfrågor och svar, felkoder för Groq samt en lokal HTTP-server.
- Två oberoende extra belastningsrundor: 560 kombinationer av formulering och kontext i regressionerna samt 1 200 störda HTTP-anrop utöver dessa; inga HTTP 500 i extra rundan.
- `node ui_stress.cjs` och `node ui_smoke.js`: simulerad historik, dubbla händelser, tomma/felaktiga svar, panel, favoriter, filter, ångra och matchkort godkända. JavaScript syntaxkontroll godkänd.
- Lokala HTTP-anrop till `/`, `/evaluation`, `/health`, `/api/fixtures`, `/chat` och en okänd adress provades med en separat startad Flask-process. CSS parsades med jsdom (179 regler). Textkontrast i huvudpaletten beräknades till minst 5,65:1.
- Tidigare kördes hela träningskedjan med 360 syntetiska matcher och en faktisk sparad testmodell. Dessa matcher mäter **inte** träffsäkerhet på verkliga matcher.

**Inte testat:** En riktig Groq-förfrågan, fotbollsleverantörens API med ägarens nyckel, deploy av V12 till Render och pixelvisuell kontroll i en riktig webbläsare. Chromium kunde inte laddas ned i arbetsmiljön (timeout). En ansluten modell kan fortfarande producera felaktiga påståenden; prompt och tester minskar risken men bevisar inte faktakorrekthet. Efter publicering behövs en snabb manuell mobilkontroll vid 360, 390 och 768 px och desktop vid 1024 och 1440 px.

**Datagränser:** xG, verifierade skador, startelvor, liveodds och individuell spelarprognos saknas. Cuptips använder ligahistorik och är inte särskilt validerade. Enskilda slutresultat är punktuppskattningar och inte testade marknadssannolikheter. Cuper kan saknas i gratisplanens datatäckning.
