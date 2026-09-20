# Matchorakel: karta före ändring

Flask app.py tar POST /chat, begränsar input, läser klientens kontext och historik, delar delfrågor och väljer regelbaserat svar eller language_chat.general_answer. football.py matchar lag och skapar features. Joblib-modeller från train_model.py ger 1X2, goal_model.py målmatris. fixtures.py läser fixtures.json; update_fixtures.py hämtar scheman/lagprofiler. player_data.py läser valfri spelarfil. public_start.py startar schemahämtning, deploy_build.py hämtar/tränar vid publicering.

Frontend templates/index.html → static/script.js → fetch /chat → renderPrediction/renderInsight/renderFixtures/text. localStorage innehåller chattar och favoriter. Sidopanelen öppnar matcher (API /api/fixtures), lokal uppdatering (/api/data/status, /api/data/update) och utvärdering (/evaluation). /api/match/result jämför sparad prognos mot resultat. /health och /api/chat/status anger anslutning. templates/404.html är reservsida.

## Synliga element inventerade
Behåll: Matchorakel, Ny chatt, historiksökning, chattitlar, radera/ångra, matcher/favoriter, modellresultat, lokal datauppdatering, fråga/svar, datum/arena/källa när efterfrågade, statistiketiktter, fel med återförsök, input/skicka.
Ta bort från chatten: Matchanalys, ligalista, V12, monogram/avatar framför svar, brand-dot, Fem ligor och cuper, Fråga i samma chatt, startsidans badge/hero/exempelrutnät, Fortsätt fråga, AI-anslutningsstatus, upprepade garantivarningar, extra tabeller efter varje prediction.
Flytta: tävlingar och anslutningsstatus till Om Matchorakel; metodinformation till befintlig resultatsida.

## Prioriterade risker
1. Fel ämne/lag efter kontextbyte; hemma/borta följer alltid ordordning; schemat behandlar preliminär tid som bekräftad.
2. Matchstatistik och prediktion saknas i AI-historik. API-fel döljs som vanliga svar; återförsök skapar extra tur.
3. Gemini saknar native systemInstruction/finishReason-kontroll, kvotretry och skydd mot påhittade tal.
4. Inter Miami matchas som Inter; tvetydiga lag/typos hanteras ofullständigt; många engelska frågor avvisas.
5. NaN/negativa/fractionella matchvärden accepteras, utvärdering validerar nycklar men inte värdetyper.
6. All rendering ersätter listan och drar scroll till botten; ingen stoppknapp/IME/textarea eller säker flerflikshistorik.
7. Dekoration, kompakt text, otydliga fel och avsaknad av lokal font/metadata.

## Testgräns
Inga API-nycklar finns i denna arbetsmiljö. Riktig Gemini-körning måste verifieras separat från transporter med kontrollerade svar. Syntetiska data används för reproducerbara facit; modellernas verkliga träffsäkerhet kräver historiska data och tidsordnat test.
