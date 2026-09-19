# Matchorakel – fotboll och samtal i samma chatt

En webbchatt som visar **uppskattade** sannolikheter för hemmavinst, oavgjort och bortavinst. Premier League, La Liga, Bundesliga, Serie A och Ligue 1 har egna matchfiler, modeller och testresultat. Du behöver inte välja liga: skriv lagnamnen och fortsätt med följdfrågor i samma chatt. Sidan kan visa form, mål, lagens skott på mål eller gula kort, hållna nollor och tidigare målrika matcher när uppgifterna finns. Frågor utanför fotboll får ett kort hänvisande svar. Chattar sparas lokalt i webbläsaren och kan raderas i sidomenyn.

För en publicerad sajt kan du använda en egen `GROQ_API_KEY` på Groqs gratisnivå. Servern skickar bara aktuell fråga, kort samtalshistorik och relevant underlag till språkmodellen; nyckeln skickas inte till webbläsaren. Lokalt kan du även ansluta [Ollama](https://docs.ollama.com/windows) eller använda `OPENAI_API_KEY` (som kan kosta pengar). Football-data.org-nyckeln används bara för spelscheman. Inget språkmodellssvar garanterar korrekta aktuella fakta; matchdata hämtas separat.

Version 11 behåller en gemensam chatt. Den visar konkreta men osäkra resultattips för ligamatcher och analyserar även FA Cup, Copa del Rey ("Copa España"), Europa League, Conference League, DFB-Pokal och Coppa Italia i samma chatt. Resultattips för cuper är grova uppskattningar från ligahistorik, inte validerade cupmodeller. Enskilda slutresultat har inte separat validerats; procentsatserna för 1X2 kommer från den tränade ligamodellen. Cuper visas i matchpanelen endast när datakällan lämnat matcherna. [Kontrollera football-data.orgs täckning för din plan](https://www.football-data.org/pricing): gratisnyckeln behöver inte ge tillgång till alla cuper. Gränssnittet visar också när AI-anslutningen misslyckas; tillgänglig matchfakta fortsätter att fungera.

Version 12 har mörkt och avskalat gränssnitt, kortare fotbollssvar och en tydlig resultatrad före statistik. Den hänvisar frågor utanför fotboll till matchanalys. Version 12 förtydligar också svar på enskilda lag och frågor om insläppta mål och xG. Målfrågor får en markerad grov uppskattning när just den målmarknaden inte klarade valideringen. Framtidsfrågor om skott och gula kort visar tidigare utfall med tillräckligt underlag, tydligt skilt från en tränad matchprognos. Felaktig samtalskontext, trasig historik, ofullständiga spelscheman och saknade statistikfält hanteras utan att låsa chatten. AI-status visar den faktiska HTTP-koden efter ett fel; ett lagrat API-värde betyder inte att anslutningen har testats.

## Publicera gratis så andra kan chatta

Den här utgåvan kan publiceras med [Render Free Web Service](https://render.com/docs/free) för webbsidan och [Groq Free Plan](https://console.groq.com/docs/rate-limits) för språkmodellen. Båda har begränsningar. Render kan ta omkring en minut att vakna efter 15 minuters vila, har ett tillfälligt filsystem och kan pausa tjänsten när gratiskvoten tar slut. Groqs gratisgränser delas av alla besökare. Ingen betalning behövs om du väljer gratisplanerna och undviker att lägga till ett betalningssätt. Läs alltid de aktuella villkoren innan du aktiverar ett konto.

**Förbered:** Du behöver egna gratis konton hos GitHub, Render och Groq; skapa din **egen** Groq-nyckel i [Groq Console](https://console.groq.com/keys). Din befintliga football-data.org-nyckel kan anges separat som hemlighet om du vill visa aktuella scheman. Dela aldrig dessa nycklar i chattar eller filer. Har en nyckel redan skickats till någon bör du ersätta den hos leverantören.

1. Öppna [GitHub](https://github.com/new), skapa ett nytt publikt repository, exempelvis `matchorakel`, och välj **Create repository**. Skapa ingen README automatiskt.
2. På den tomma repositorysidan välj **uploading an existing file**. Öppna din uppdaterade `matchorakel`-mapp i Utforskaren, markera filerna och mapparna **inne i den** och dra dem till GitHubs uppladdningsyta. **Lägg inte upp `.env`, dina CSV-filer, `artifacts` eller `data/fixtures.json`; kontrollera listan innan du trycker Commit changes.** På repositoryts första sida ska `app.py` och `render.yaml` ligga på samma nivå. Om GitHubs webbuppladdning inte klarar hela mappstrukturen, använd GitHub Desktop för att publicera mappen.
3. Gå till [Render Dashboard](https://dashboard.render.com/), välj **New → Blueprint**, koppla ditt nya GitHub-repository och välj filen `render.yaml`. Render ska visa `plan: free`. Skriv in din Groq-nyckel i hemligheten `GROQ_API_KEY` när Render ber om den och starta publiceringen. Om du använder Web Service i stället för Blueprint: välj Python och Free, **Build Command** `pip install -r requirements.txt && python deploy_build.py`, **Start Command** `gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 90 public_start:app` och skapa miljövariablerna `PYTHON_VERSION=3.13.4`, `MATCHORAKEL_PUBLIC=1` och `GROQ_API_KEY`.
4. Vänta tills byggloggen visar att alla fem ligamodeller tränats och sidan blir **Live**. Öppna Render-länken som slutar på `.onrender.com`. Fråga först `Barcelona mot Real Madrid` och sedan `Vad tror du att det slutar?`. Det är **en och samma chatt** för båda.
5. Valfritt: i Render, öppna tjänstens **Environment** och lägg till `FOOTBALL_DATA_TOKEN` med en **ny privat** football-data.org-nyckel. Starta om tjänsten. Den hämtar då tillgängliga liga- och cupscheman samt ordinarie hemmaarenor i bakgrunden vid start. Saknar din plan åtkomst till en cup visas ingen påhittad match. Eftersom gratisservern tappar lokala filer när den somnar hämtas schemat på nytt efter uppvakning; det kan ta några minuter innan ett schema visas.

`deploy_build.py` hämtar ligadata och tränar modellerna vid publicering; detta tar tid och misslyckas synligt om en ligamodell inte kan tränas. `public_start.py` hämtar vid behov separat spelschema när servern startar. Render lagrar de byggda modellerna för varje publicering, men **uppdaterar inte resultat automatiskt** förrän du publicerar om sidan. Varje besökares chattar finns bara i den egna webbläsaren. En publicerad sida använder endast en serverprocess; chattbegränsningen nollställs när servern startar om. För många samtidiga användare eller permanent lagring krävs en annan driftlösning.

### Om din Render-sida redan finns

**Skapa inte en ny tjänst.** Ersätt programfilerna i det GitHub-repository som den befintliga tjänsten använder. Det enklaste tillförlitliga sättet när filer redan finns är [GitHub Desktop](https://desktop.github.com/): välj **File → Clone repository** för ditt befintliga `matchorakel`-repository, packa upp senaste publiceringsarkivet och kopiera innehållet i dess `matchorakel`-mapp in i den klonade mappen. Ersätt befintliga filer. I GitHub Desktop skriver du en kort text under **Summary**, klickar **Commit to main** och sedan **Push origin**. Render publicerar normalt GitHub-ändringen automatiskt. Kontrollera under **Deploys** att det är den senaste ändringen som är Live.

På Render: öppna **Environment** för din befintliga tjänst och kontrollera att `GROQ_API_KEY` finns där som hemlighet. `football-data.org`-nyckeln är **inte** en AI-nyckel. Matchprognoser och sparad statistik fungerar utan Groq; externa AI-svar på öppna fotbollsfrågor behöver en fungerande språkmodell. Om nyckeln finns men öppna fotbollsfrågor misslyckas: kontrollera **Logs** efter `Groq svarade med HTTP ...`. `401` betyder normalt fel nyckel; `429` betyder att en anropsgräns nåtts; `403` kräver kontroll hos Groq eller Render, särskilt när Playground fungerar men servern nekas. Loggen visar HTTP-status och svarstyp, aldrig själva nyckeln. En valfri, **ny egen** `FOOTBALL_DATA_TOKEN` i Environment hämtar tillgängliga liga- och cupscheman vid serverstart. Utan den kan matchhistorik fungera medan datum saknas.

## Uppdatera en befintlig installation

1. Stäng webbservern i terminalen med **Ctrl+C**.
2. Spara `Matchorakel-uppdatera-v12.py` i Downloads och kör i PowerShell:

```powershell
py "$env:USERPROFILE\Downloads\Matchorakel-uppdatera-v12.py"
```

Uppdateraren byter programfiler, behåller dina `data`- och `artifacts`-mappar och tränar modellerna med dina matchfiler. Vänta på att den blir färdig. Kör sedan de startkommandon som visas i PowerShell och ladda om sidan med **Ctrl+F5**. Om du saknar CSV-filer, kör `py fetch_data.py` och sedan `py train_model.py` i projektmappen.

Om VS Code visar "Import could not be resolved" trots att `py app.py` fungerar: kör `py -c "import sys; print(sys.executable)"` i PowerShell. Öppna sedan kommandopaletten i VS Code med **Ctrl+Shift+P**, välj **Python: Select Interpreter** och välj Python-filen vars sökväg kommandot skrev ut. Ladda om VS Code-fönstret. Kör `py -m pip install -r requirements.txt` om paketen saknas även med rätt Python.

För språkmodellssvar på öppna fotbollsfrågor **lokalt utan API-nyckel**: installera Ollama för Windows från länken ovan och kör `ollama pull gemma3:4b` i PowerShell. Modellen är cirka 3,3 GB och kräver ytterligare diskutrymme. Ladda sedan om hemsidan. Ollama på din dator är inte tillgänglig för andra på den publicerade servern. Där använder du en servernyckel till en hostad språkmodell som Groq.

För att köra de lokala kontrollerna själv: `py -m unittest discover -s tests -v`. De testar bland annat HTTP-svaren, Champions League-frågor och följdfrågor med ett konstgjort spelschema. De kräver ingen API-nyckel.

För **aktuella matchdatum, arena och Champions League-matcher** finns ett separat steg med en egen nyckel. Se "Spelschema" längre ner. Installationen fungerar även utan nyckel, men visar då inte påhittade schemauppgifter.

Senare kan du trycka **Uppdatera data** på sidan eller köra `py refresh.py` för nya ligamatcher och omträning. Schemat uppdateras separat med football-data.org-nyckeln. Efter terminalkommandon, starta om webbservern.

## Ny installation

Öppna mappen `matchorakel` i VS Code. I terminalen:

```powershell
py -m pip install -r requirements.txt
py fetch_data.py
py train_model.py
py app.py
```

Om `py` saknas, använd `python` i stället. Låt terminalen med `py app.py` vara öppen när du använder sidan. För publicering används Gunicorn och `MATCHORAKEL_PUBLIC=1`; Flask-utvecklingsservern är endast till för datorn hemma.

## Data och uppdatering

Källa: [Football-Data.co.uk](https://www.football-data.co.uk/). Hämtningsskriptet tar `E0` (Premier League), `SP1` (La Liga), `D1` (Bundesliga), `I1` (Serie A) och `F1` (Ligue 1) från säsong 2022/23 till aktuell säsong. Redan sparade äldre säsonger lämnas i fred. Mapparna är `data/`, `data/la-liga/`, `data/bundesliga/`, `data/serie-a/` och `data/ligue-1/`. Källfilerna ingår inte i projektpaketet.

För att få med **nya resultat under pågående säsong**, kör:

```powershell
py fetch_data.py
py train_model.py
```

Starta om servern efteråt. Befintliga äldre säsonger hämtas inte om. Notera källa, säsonger och datum då ni hämtade data i rapporten. Om nedladdningen misslyckas, hämta CSV-filerna manuellt från länkarna ovan och lägg dem i rätt mappar. Filerna måste innehålla `Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, `FTR`.

### Spelschema för ligor och cuper

[football-data.org](https://www.football-data.org/coverage) har scheman för de fem ligorna och vissa cuper beroende på din plan. Programmet försöker även hämta FA Cup, Copa del Rey, Europa League, Conference League, DFB-Pokal och Coppa Italia. För att använda API:et behöver du registrera en egen nyckel där. Kör i projektmappen:

```powershell
py update_fixtures.py
```

Enbart Champions League, utan väntan mellan ligorna:

```powershell
py update_fixtures.py --league UCL
```

Enbart en annan cup, till exempel FA Cup eller Copa del Rey:

```powershell
py update_fixtures.py --league FAC
py update_fixtures.py --league CDR
```

Skriv nyckeln när terminalen frågar (den visas inte på skärmen). Dela inte nyckeln i chatten. Skriptet hämtar publicerade matcher för API:ets aktiva säsong, sparar uppgifterna i `data/fixtures.json` direkt efter varje lyckad liga och visar en förklaring om API:et svarar med ett fel. Vid hämtning av alla ligor väntar det mellan anrop för att passa gratisnivån. Starta om `py app.py` efteråt. Kör kommandot på nytt när du vill uppdatera schemat; det uppdaterar **inte** den tränade matchmodellen. För nya spelade resultat: kör även `py fetch_data.py` följt av `py train_model.py` och starta om appen.

Om matchen saknar publicerad arena försöker uppdateringen även hämta hemmaalagets ordinarie arena. Den markeras tydligt som **trolig**, eftersom matchen kan spelas på annan arena. Om inte heller lagprofilen anger en arena står det att arenan saknas. Uppdateringen använder extra API-anrop och kan ta några minuter. Schemat och dess hämtningsdatum visas separat från äldre ligastatistik. Champions League har ingen egen tränad matchmodell. Nyckeln hämtar endast publicerat schema och lagprofiler; den tränar inte modellen och ger inte en fri chattbot. Lämna aldrig nyckeln i en chatt eller i projektfilernas källkod.

## Metod för gymnasiearbetet

`py train_model.py` skapar för **varje liga**:

- `artifacts/evaluation_XX.json`: antal matcher, datumintervall, validering, test och förväxlingsmatris.
- `artifacts/test_predictions_XX.csv`: varje testmatch med facit och modellens tre sannolikheter.
- `artifacts/model_XX.joblib`: modeller för hemsidan. `XX` är `PL`, `LL`, `BL`, `SA` eller `L1`. Läs bara modeller ni själva skapat.

Modellen jämför tre uppsättningar faktorer: fem senaste **redan spelade** matcher; även tidigare hemma- och bortastyrka; även löpande Elo-lagstyrka och antal vilodagar inför match. Elo bygger på tidigare ligamatcher under flera säsonger och uppdateras efter varje matchdag, så matcher på samma datum kan inte se varandras resultat. Högst 21 vilodagar används. Vilka extrafaktorer som får ingå avgörs av valideringen; om de försämrar sannolikheterna väljs en enklare modell. Matcher utan tillräcklig tidigare statistik ingår inte i träningen. Tidigare skott och kort redovisas separat och ingår inte i vinnarmodellen.

Matchdagarna delas kronologiskt i ungefär **60 % träning, 20 % validering och 20 % test**. Logistisk regression, Random Forest, deras kombination och en Poissonmodell för mål jämförs på valideringsperiodens log loss med de tre faktoruppsättningarna. Sedan tränas den valda modellen på träning + validering och jämförs på den senare testperioden mot två baslinjer: tidigare utfallsfrekvens och lika sannolikhet (1/3 per utfall). Accuracy visar andelen rätt vald utfallsklass; log loss och Brier granskar sannolikheterna. Lägre log loss och Brier är bättre. En separat målmodell ger sannolikheter för över 1,5 mål, över 2,5 mål och båda lagen gör mål bara för marknader där den slagit träningsperiodens frekvens på validering. Först **efter** utvärderingen tränas webbmodellernas slutversioner på all tillgänglig data.

Om CSV-filerna innehåller `AvgH`, `AvgD` och `AvgA` finns även en **separat oddsjämförelse** på de testmatcher där alla tre odds är tillgängliga. Programmet räknar om 1/odds till sannolikheter och normaliserar bort marginalen. Modellen och marknaden jämförs bara på *samma* matcher. Odds ingår aldrig i modellens features eller träning. Jämförelsen handlar om prognoskvalitet, inte spelråd.

**Gräns för tolkningen:** Den äldre versionen av projektet använde senare Premier League-matcher för modellval. Därför är omkörningen av samma data inte ett helt nytt blindat experiment, även om den nya koden separerar perioderna korrekt. Helt nya matcher behövs för det. Modellen kan ge en teoretisk matchprognos utan bekräftat schema, och tar inte hänsyn till skador, startelvor eller liveinformation. En skada ändrar inte procenttalen utan verifierad spelarhistorik och en testad justeringsmodell. En hög sannolikhet innebär varken garanti eller att ett spel är lönsamt. För sådan bedömning behövs aktuella odds och deras marginal.

Frågan `Vad är säkrast att hända i den här matchen?` rangordnar återkommande mål, lagskott och lagkort från lagens senaste **upp till 20 ligamatcher**, och visar både antal och historisk andel. Rangordningen tar hänsyn till stickprovsstorleken men är **inte en prognosmodell för dessa specifika händelser**. Med färre än 12 matcher säger appen att det saknas underlag. Den förutspår inte vem som får kort, om en viss spelare skjuter eller hur en skadad motspelare påverkar målchansen. Sådana faktorer kräver verifierade uppställningar och spelardata, testade före avspark; appen justerar inga procentsatser på fri text om skador.

## Chattens format

Skriv exempelvis `Arsenal mot Chelsea`, `Inter mot Milan` eller `PSG mot Marseille`. Första laget antas spela hemma. Appen känner igen ligan och du kan sedan fråga om ett annat lag i en annan liga i samma chatt. Lag från olika ligor ger ett förklarande svar; ligamodellen har inte tränats för sådana matcher. Tidigare frågor sparas endast i samma webbläsares lokala lagring, inte på en server. Klicka på **×** bredvid en chatt för att radera den. All matchfakta i svaret kommer från inlästa CSV-filer.

Exempel på följdfrågor i samma chatt: `Varför?`, `Hur är Barcelonas form?`, `Jämför lagens form`, `Vad är säkrast att hända?`, `Hur många skott på mål har Barcelona haft?`, `Hur många gula kort har lagen fått?`, `Hur ofta höll Bayern nollan?`, `Hur många matcher hade över 2,5 mål?`, `När spelar Barcelona mot Real Madrid?`, `Vilken arena?`, `När spelar Barcelona i Champions League?`, `Hur bra är modellen?`. Frågor om skott och kort visar hur många tidigare matcher som hade uppgiften. CSV-filerna kan innehålla lagens skott på mål (`HST`, `AST`) och gula kort (`HY`, `AY`); dessa tal gäller laget. Målrika matcher och hållna nollor är historik, inte särskilt tränade sannolikheter för nästa match.

### Spelare: valfri egen datafil

För frågor som `Får Raphinha skott på mål?` räcker inte ligafilerna: de saknar enskilda spelares matcher. Utan spelarfil får du därför ett ärligt svar om att underlag saknas. Om du har en **laglig, kontrollerad källa** med spelarmatcher kan du skapa `data/player_stats.csv` med en rad för varje faktisk medverkan och dessa rubriker:

```csv
date,league,player,team,minutes,shots_on_target,yellow_cards
```

Datum skrivs `ÅÅÅÅ-MM-DD`; `league` skrivs `PL`, `LL`, `BL`, `SA` eller `L1`, `minutes` anger spelade minuter, `shots_on_target` och `yellow_cards` är heltal. Starta om `py app.py` efter att du ändrat filen. Chatten visar då observerat antal under spelarens senaste fem registrerade ligamatcher, **inte en utlovad eller tränad sannolikhet för nästa match**. Lägg bara in riktiga, verifierade matcher; filen följer inte med uppdateringen. En aktuell prognos för spelare skulle dessutom behöva startelvor, förväntade minuter och en kontrollerad historisk utvärdering. Ingen API-nyckel krävs för appen som den är.
