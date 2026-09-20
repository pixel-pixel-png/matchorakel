# Matchorakel

En mörk fotbollschatt med matchprognoser, statistik, spelscheman och Gemini. Chattar och favoritlag sparas i den egna webbläsaren. Tävlingar och anslutningsstatus finns under **Om Matchorakel**.

## Starta på Windows

Öppna PowerShell. Kör en rad i taget:

```powershell
cd "$env:USERPROFILE\Downloads\Matchorakel-v1\matchorakel"
py -m pip install -r requirements.txt
py app.py
```

Öppna `http://127.0.0.1:5000`. Låt PowerShell-fönstret vara öppet. Stoppa servern med Ctrl+C innan du uppdaterar filer. Appen läser miljövariabler från Windows/Render; `.env.example` är en lista över namn och laddas inte automatiskt.

Om matchmodellerna saknas, kör före `py app.py`:

```powershell
py fetch_data.py
py train_model.py
```

Vid uppdatering behåll dina `data`- och `artifacts`-mappar. Hämta/träna igen när du vill få med nya matchresultat. En koduppdatering gör inte gammal matchdata aktuell.

## Publicera uppdateringen i ditt befintliga GitHub-repository

1. Packa upp paketet och öppna mappen `matchorakel`. Inne i den finns `app.py`, `render.yaml`, `templates`, `static`, `tests` och `qa`.
2. Öppna ditt repository på GitHub. Välj **Add file → Upload files**.
3. Dra innehållet i mappen till uppladdningen. Dra mapparna `templates` och `static` som hela mappar. Kontrollera att listan visar `templates/index.html`, `static/style.css`, `static/script.js` och `static/fonts/InterVariable.woff2`. HTML/CSS-filerna ska inte hamna bredvid `app.py`.
4. Ladda bara upp programfilerna från paketet. Lägg inte upp egna nycklar, `.env`, CSV-matchfiler eller modeller.
5. Klicka **Commit changes**. Render ska därefter bygga samma ändring. Kontrollera att senaste commit är Live under **Events/Deploys**. Välj **Manual Deploy → Deploy latest commit** om automatisk publicering är avstängd.
6. Öppna din Render-länk och tryck Ctrl+F5.

Om GitHubs uppladdning inte bevarar mappar: öppna först `templates` på GitHub och ladda upp HTML-filerna där. Gör samma sak i `static`, och därefter `static/fonts` för fonten och licensen. `app.py` och `render.yaml` ska ligga i repositoryts rot. Mappen `matchorakel` inuti ett äldre repository används inte när Render startar rotens `public_start:app`.

## Render och Gemini

Behåll den tjänst och nyckel som redan fungerar. Sätt hemligheter direkt i **Render → din tjänst → Environment**.

| Namn | Användning |
| --- | --- |
| `GEMINI_API_KEY` | Din privata Gemini-nyckel; krävs för öppna fotbollsfrågor. |
| `MATCHORAKEL_GEMINI_MODEL` | `gemini-3.1-flash-lite` är standard och matchar den tidigare fungerande inställningen. |
| `FOOTBALL_DATA_TOKEN` | Valfri privat football-data.org-nyckel för spelscheman och lagarenor. |
| `MATCHORAKEL_PUBLIC` | `1` på Render, `0` eller utelämnad på din egen dator. |
| `PYTHON_VERSION` | `3.13.4` i den medföljande Render-konfigurationen. |

Build Command:

```text
pip install -r requirements.txt && python deploy_build.py
```

Start Command:

```text
gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 90 public_start:app
```

Modellnamnet finns i [Googles modellbeskrivning](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite). Ändra inte en fungerande modell bara för att en ny modell lanserats.

Öppna `/health` på din egen server. `status: ok` anger att Flask svarar; det betyder inte att Gemini har testats. `ai_health` är `unconfigured`, `unverified`, `ok` eller `failed`. Ställ en öppen fotbollsfråga, exempelvis ”Förklara hög press”, och kontrollera därefter hälsan.

Vid problem: kopiera loggrader som börjar med `Gemini HTTP` eller `Gemini:` och felet från `/health`. Dela aldrig nyckeln. HTTP 404 kan bero på fel modellnamn, 403 på åtkomst, och 429 på kvot. Kontrollera [Google AI Studio](https://aistudio.google.com/) och serverns miljövariabler. Om en nyckel har exponerats: ersätt den i AI Studio, uppdatera Environment och publicera om tjänsten.

## Så behandlas en fråga

`/chat` validerar input och anropsgränser → `chat_logic.py` matchar lag, tävling, språk och kontext → strukturerade fakta eller matchmodellen ger numeriska svar → Gemini används för öppna förklaringar → `script.js` visar ett komplett svar. `conversation.py` hjälper med delfrågor och en relevant följdfråga.

- Gemini får native `systemInstruction` och högst åtta kompletta user/model-par. Aktuella uppgifter skickas separat från användarens påståenden.
- Låg temperatur, begränsad thinking och outputgräns. Avkapade svar försöks en gång med större tokenbudget. Transienta HTTP-fel får högst ett kort återförsök; längre Retry-After respekteras genom att avstå.
- Tomma/blockerade/ofullständiga svar och tal som saknas i underlaget visas som ett hanterat fel. Sifferkontrollen är inte ett bevis på att varje formulering är sann.
- Resultat och 1X2 kommer från Pythonmodellerna. En exakt resultatrad är en osäker punktprognos, inte ett säkert utfall. En mest sannolik enskild resultatrad kan vara oavgjord även när hemmaseger är den största sammanlagda utfallsklassen.
- Ingen falsk skrivmaskinsanimation. Svaret visas efter fullständig validering; denna version streamar inte text. Stopp avbryter webbläsaranropet och begär att servern stänger en aktiv AI-anslutning. Redan utförd beräkning hos leverantören kan inte återkallas.
- Fel sparas separat från svar. Återförsök ersätter samma tur. Byte av chatt avbryter gamla anrop och sena svar ignoreras.

## Data och metod

Ligamodeller finns för Premier League, La Liga, Bundesliga, Serie A och Ligue 1. Källan är [football-data.co.uk](https://www.football-data.co.uk/). Träningen jämför logistisk regression, Random Forest, en kombination och Poisson med form, hemma/bortahistorik samt Elo och vila. Valideringen avgör modellvalet. Testperioden ligger senare än tränings- och valideringsperioderna; därefter tränas den publicerade modellen på all tillgänglig historik. Se **Modellresultat** för faktiska utvärderingar. Äldre projektversioner har redan tittat på delar av materialet: detta är inte ett nytt blindtest.

Modellerna innehåller inte aktuell startelva, skador, spelarnas förväntade minuter eller uppmätt xG. Förklaringen ska ange när sådant underlag saknas. En språkmodell tillför inte en verifierad datakälla för dessa uppgifter.

En valfri `data/player_stats.csv` kan innehålla verifierad spelarhistorik:

```csv
date,league,player,team,minutes,shots_on_target,yellow_cards
```

Använd riktiga uppgifter och datum `YYYY-MM-DD`. Detta möjliggör historiska observationer, inte en tränad målskyttsmodell.

Spelschema hämtas separat från [football-data.org](https://www.football-data.org/coverage):

```powershell
py update_fixtures.py
```

Programmet försöker hämta de fem ligorna och Champions League, FA Cup, Copa del Rey, Europa League, Conference League, DFB-Pokal och Coppa Italia. Åtkomst och tävlingskoder beror på leverantörens stöd och din plan. Ingen lyckad hämtning betyder inte att en match saknas i verkligheten. `SCHEDULED` visas utan exakt avspark; `TIMED` kan visas i svensk tid. En lagprofils ordinarie arena markeras som trolig, aldrig som bekräftad för matchen.

Render-starten hämtar tillgängliga scheman om datanyckeln är satt. Modellerna uppdateras vid byggning eller lokal datauppdatering, inte efter varje besökarfråga.

## Skydd och begränsningar

Högst 2 000 tecken per fråga, 32 KiB per request och åtta kontextpar till Gemini. På publik server: åtta frågor per minut och IP, tjugo per minut totalt och tvåhundra per dygn totalt. Dessutom högst två samtidiga anrop per IP. Gränserna ligger i minnet och kräver en serverprocess; delade IP-adresser delar kvot. Omstart nollställer räknarna. Detta är inte en garanti mot distribuerat missbruk eller leverantörskostnader. Kontrollera budget och kvot i AI Studio. Lokal statistik fungerar utan Gemini.

En gratis värdtjänst kan vila, bli långsam eller få slut på kvot. En fungerande lokal testsvit garanterar inte att externa tjänster alltid svarar. Aktuella villkor finns hos [Render](https://render.com/docs/free) och [Google](https://ai.google.dev/gemini-api/docs/rate-limits).

## Tester

```powershell
py -m unittest discover -s tests -v
py qa/run_cases.py --round manual
```

Reproducerbara tester använder tydligt syntetiska data i `qa/support.py`; dessa laddas aldrig av produktionsstarten. Riktiga webbläsartester kräver Playwright separat:

```powershell
py -m pip install playwright
py -m playwright install chromium
py qa/browser_check.py --round 9
```

För frivillig kontroll mot **riktig Gemini** på en miljö där nyckeln redan är satt:

```powershell
py -m qa.live_gemini --limit 5
```

Runnern har trettio olika fotbollsfrågor, små batcher, minst tio sekunders paus och diskcache för redan utförda frågor. Den stoppar vid fel för att inte förbruka kvoten. Riktiga svar kräver också manuell faktagranskning. Testgränser och faktiskt utförda kontroller står i `TESTRAPPORT.md`.

## Font

Inter laddas lokalt från `static/fonts/InterVariable.woff2`. Licensen finns i `static/fonts/OFL.txt` och originalprojektet på [Inter](https://rsms.me/inter/).
