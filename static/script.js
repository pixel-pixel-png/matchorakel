const form = document.querySelector('#composer');
const input = document.querySelector('#message');
const sendButton = document.querySelector('#sendButton');
const scroller = document.querySelector('#chat');
const content = document.querySelector('#chatContent');
const conversationsNode = document.querySelector('#conversations');
const undoToast = document.querySelector('#undoToast');
const sidebar = document.querySelector('#sidebar');
const appShell = document.querySelector('.app-shell');
const scrim = document.querySelector('#scrim');
const openSidebarButton = document.querySelector('#openSidebar');
const panel = document.querySelector('#toolPanel');
const panelTitle = document.querySelector('#panelTitle');
const panelBody = document.querySelector('#panelBody');
const searchConversations = document.querySelector('#searchConversations');
const chatCapability = document.querySelector('#chatCapability');
const STORAGE_KEY = 'matchorakel-conversations-v1';
const FAVORITES_KEY = 'matchorakel-favorites-v1';
const LEAGUE_NAMES = {PL: 'Premier League', LL: 'La Liga', BL: 'Bundesliga', SA: 'Serie A', L1: 'Ligue 1',
  UCL: 'Champions League', FAC: 'FA Cup', CDR: 'Copa del Rey', EL: 'Europa League',
  UECL: 'Conference League', DFB: 'DFB-Pokal', CIT: 'Coppa Italia'};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function readConversations() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    return Array.isArray(saved) ? saved.filter(item => item && typeof item.id === 'string' &&
      typeof item.title === 'string' && Array.isArray(item.messages)).slice(0, 30).map(item => ({
        ...item, messages: item.messages.filter(turn => turn && typeof turn.question === 'string').slice(-100)
      })) : [];
  } catch {
    return [];
  }
}

let conversations = readConversations();
let activeId = conversations[0]?.id || null;
let busy = false;
let pendingChat = null;
let undoTimer;
let matchesFilter = 'all';
let matchesVisible = 8;
let panelRequestId = 0;
let favorites = [];
try { favorites = JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]'); } catch { favorites = []; }
if (!Array.isArray(favorites)) favorites = [];
const favoriteKey = name => String(name || '').toLowerCase().replace(/\b(fc|cf)\b/g, '').replace(/[^a-zåäö0-9]/g, ' ').trim();

function toggleFavorite(name) {
  const key = favoriteKey(name);
  favorites = favorites.includes(key) ? favorites.filter(item => item !== key) : [...favorites, key];
  try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(favorites)); } catch { /* Lokal lagring är valfri. */ }
}

function closePanel() { panel.hidden = true; panelRequestId++; }
document.querySelector('#closePanel').addEventListener('click', closePanel);

async function showMatches() {
  const requestId = ++panelRequestId;
  panel.hidden = false;
  panelTitle.textContent = 'Matcher och favoritlag';
  panelBody.replaceChildren(element('p', 'panel-muted', 'Hämtar publicerade matcher ...'));
  try {
    const response = await fetch('/api/fixtures');
    if (!response.ok) throw new Error('Kunde inte läsa schemat.');
    const fixtures = await response.json();
    if (requestId !== panelRequestId) return;
    if (!Array.isArray(fixtures)) throw new Error('Schemat hade ett oväntat format. Försök senare.');
    const usableFixtures = fixtures.filter(item => item && typeof item === 'object' &&
      typeof item.home === 'string' && typeof item.away === 'string' && typeof item.league === 'string');
    panelBody.replaceChildren();
    const filters = element('div', 'match-filters');
    for (const [code, label] of [['all', 'Alla'], ['favorites', 'Favoriter'], ['PL', 'Premier League'],
      ['LL', 'La Liga'], ['BL', 'Bundesliga'], ['SA', 'Serie A'], ['L1', 'Ligue 1'],
      ['UCL', 'Champions League'], ['FAC', 'FA Cup'], ['CDR', 'Copa del Rey'],
      ['EL', 'Europa League'], ['UECL', 'Conference League'],
      ['DFB', 'DFB-Pokal'], ['CIT', 'Coppa Italia']]) {
      const button = element('button', `match-filter${matchesFilter === code ? ' active' : ''}`, label);
      button.type = 'button';
      button.addEventListener('click', () => { matchesFilter = code; matchesVisible = 8; drawMatches(); });
      filters.append(button);
    }
    panelBody.append(filters);
    const list = element('div', 'match-list');
    panelBody.append(list);
    function drawMatches() {
      for (const button of filters.children) button.classList.toggle('active',
        button.textContent === ({all:'Alla', favorites:'Favoriter', ...LEAGUE_NAMES})[matchesFilter]);
      list.replaceChildren();
      const games = usableFixtures.filter(item => matchesFilter === 'all' ||
        (matchesFilter === 'favorites' ? [item.home, item.away].some(team => favorites.includes(favoriteKey(team))) : item.league === matchesFilter));
      list.append(element('p', 'panel-muted', `${games.length} kommande matcher · visa ${Math.min(matchesVisible, games.length)}`));
      if (!games.length) list.append(element('p', 'panel-muted', usableFixtures.length
        ? 'Inga matcher i detta filter. Prova Alla eller en annan liga.'
        : 'Inga framtida matcher har hämtats till servern. Sidans administratör behöver uppdatera spelschemat.'));
      for (const game of games.slice(0, matchesVisible)) {
        const row = element('div', 'match-row');
        const date = game.utc_date ? new Date(game.utc_date) : null;
        const when = date && !Number.isNaN(date.getTime())
          ? new Intl.DateTimeFormat('sv-SE', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit', timeZone:'Europe/Stockholm'}).format(date) : 'Datum saknas';
        row.append(element('span', 'match-row-date', `${when} · ${LEAGUE_NAMES[game.league] || 'Okänd tävling'}`));
        row.append(element('strong', 'match-row-teams', `${game.home} – ${game.away}`));
        row.append(element('span', 'match-row-venue', game.venue ?
          `${game.venue_confidence === 'confirmed' ? 'Arena' : 'Trolig hemmaarena'}: ${game.venue}` :
          'Spelplats saknas i källan'));
        const actions = element('div', 'match-row-actions');
        for (const team of [game.home, game.away]) {
          const star = element('button', 'favorite-button', `${favorites.includes(favoriteKey(team)) ? '★' : '☆'} ${team}`);
          star.type = 'button';
          star.setAttribute('aria-label', `${favorites.includes(favoriteKey(team)) ? 'Ta bort' : 'Lägg till'} ${team} som favorit`);
          star.addEventListener('click', () => { toggleFavorite(team); drawMatches(); });
          actions.append(star);
        }
        const ask = element('button', 'panel-ask', 'Fråga ↗');
        ask.type = 'button';
        ask.addEventListener('click', () => {
          closePanel(); closeMenu();
          input.value = `${game.home} mot ${game.away}, när spelas matchen?`;
          form.requestSubmit();
        });
        actions.append(ask);
        row.append(actions);
        list.append(row);
      }
      if (games.length > matchesVisible) {
        const more = element('button', 'panel-action', 'Visa 8 till');
        more.type = 'button';
        more.addEventListener('click', () => { matchesVisible += 8; drawMatches(); });
        list.append(more);
      }
    }
    drawMatches();
  } catch (error) { if (requestId === panelRequestId) {
    const retry = element('button', 'panel-action', 'Försök igen');
    retry.type = 'button'; retry.addEventListener('click', showMatches);
    panelBody.replaceChildren(element('p', 'panel-muted', error.message), retry);
  } }
}

async function showDataStatus() {
  const requestId = ++panelRequestId;
  panel.hidden = false;
  panelTitle.textContent = 'Uppdatera data';
  panelBody.replaceChildren(element('p', 'panel-muted', 'Hämtar status ...'));
  try {
    const response = await fetch('/api/data/status');
    if (!response.ok) throw new Error('Kunde inte hämta datastatus. Försök igen.');
    const data = await response.json();
    if (requestId !== panelRequestId) return;
    panelBody.replaceChildren(element('p', 'panel-muted', `${data.fixtures} matcher i schemat. Dina sparade data och modeller raderas inte vid en uppdatering.`));
    for (const league of Object.values(data.leagues)) {
      panelBody.append(element('p', 'panel-data-row', `${league.name}: ${league.files} säsongsfiler · modell ${league.trained ? 'klar' : 'saknas'}`));
    }
    const key = element('input', 'panel-input');
    key.type = 'password'; key.autocomplete = 'off'; key.placeholder = 'football-data.org-nyckel för spelschemat';
    key.setAttribute('aria-label', 'football-data.org-nyckel');
    panelBody.append(key);
    const fixtureButton = element('button', 'panel-action', 'Uppdatera spelschema och arenor');
    const resultsButton = element('button', 'panel-action', 'Uppdatera resultat och träna modeller');
    const status = element('p', 'panel-muted', data.job.message);
    for (const button of [fixtureButton, resultsButton]) button.disabled = data.job.running;
    async function start(kind) {
      const token = key.value;
      key.value = '';
      const result = await fetch('/api/data/update', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({kind, token})});
      const payload = await result.json();
      if (!result.ok) { status.textContent = payload.error || 'Uppdateringen kunde inte starta.'; return; }
      fixtureButton.disabled = resultsButton.disabled = true;
      status.textContent = 'Uppdateringen har startat. Den fortsätter medan du använder chatten.';
      setTimeout(() => { if (!panel.hidden && panelTitle.textContent === 'Uppdatera data') showDataStatus(); }, 5000);
    }
    fixtureButton.addEventListener('click', () => start('fixtures').catch(error => { status.textContent = error.message; }));
    resultsButton.addEventListener('click', () => start('results').catch(error => { status.textContent = error.message; }));
    panelBody.append(fixtureButton, resultsButton, status);
    for (const entry of data.job.log.slice(-8)) panelBody.append(element('p', 'panel-log', entry));
    if (data.job.running) setTimeout(() => { if (!panel.hidden && panelTitle.textContent === 'Uppdatera data') showDataStatus(); }, 6000);
  } catch (error) { if (requestId === panelRequestId) {
    const retry = element('button', 'panel-action', 'Försök igen');
    retry.type = 'button'; retry.addEventListener('click', showDataStatus);
    panelBody.replaceChildren(element('p', 'panel-muted', error.message), retry);
  } }
}

document.querySelector('#openMatches').addEventListener('click', () => { closeMenu(); showMatches(); });
document.querySelector('#openData').addEventListener('click', () => { closeMenu(); showDataStatus(); });
function saveConversations() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations.slice(0, 30)));
  } catch {
    // Webbplatsen fungerar även om webbläsaren blockerar lokal lagring.
  }
}

function activeConversation() {
  return conversations.find(item => item.id === activeId);
}

function scrollToBottom() {
  requestAnimationFrame(() => scroller.scrollTo({top: scroller.scrollHeight, behavior: 'smooth'}));
}

function closeMenu() {
  sidebar.classList.remove('open');
  scrim.hidden = true;
  openSidebarButton.setAttribute('aria-expanded', String(!appShell.classList.contains('sidebar-collapsed') &&
    Boolean(window.matchMedia?.('(min-width: 721px)').matches)));
}

function renderSidebar() {
  conversationsNode.replaceChildren();
  if (!conversations.length) {
    conversationsNode.append(element('p', 'empty-history', 'Dina analyser visas här när du har ställt din första fråga.'));
  }
  let shown = 0;
  for (const conversation of conversations) {
    const query = searchConversations.value.trim().toLocaleLowerCase('sv');
    if (query && !conversation.title.toLocaleLowerCase('sv').includes(query) &&
        !conversation.messages.some(item => item.question.toLocaleLowerCase('sv').includes(query))) continue;
    shown++;
    const row = element('div', 'conversation-row');
    const button = element('button', `conversation${conversation.id === activeId ? ' active' : ''}`, conversation.title);
    button.type = 'button';
    button.title = conversation.title;
    button.addEventListener('click', () => {
      if (pendingChat && activeId !== conversation.id) pendingChat.abort();
      activeId = conversation.id;
      closeMenu();
      render();
    });
    const remove = element('button', 'conversation-delete', '×');
    remove.type = 'button';
    remove.title = `Radera ${conversation.title}`;
    remove.setAttribute('aria-label', `Radera chatten ${conversation.title}`);
    remove.addEventListener('click', () => {
      const position = conversations.findIndex(item => item.id === conversation.id);
      const wasActive = activeId === conversation.id;
      if (pendingChat && wasActive) pendingChat.abort();
      conversations = conversations.filter(item => item.id !== conversation.id);
      if (wasActive) activeId = null;
      saveConversations();
      render();
      clearTimeout(undoTimer);
      undoToast.replaceChildren(element('span', '', 'Chatten raderades.'));
      const undo = element('button', '', 'Ångra');
      undo.type = 'button';
      undo.addEventListener('click', () => {
        conversations.splice(position, 0, conversation);
        if (wasActive) activeId = conversation.id;
        saveConversations();
        undoToast.hidden = true;
        clearTimeout(undoTimer);
        render();
      });
      undoToast.append(undo);
      undoToast.hidden = false;
      undoTimer = setTimeout(() => { undoToast.hidden = true; }, 8000);
    });
    row.append(button, remove);
    conversationsNode.append(row);
  }
  if (conversations.length && !shown) conversationsNode.append(element('p', 'empty-history', 'Inga chattar matchar sökningen.'));
}
searchConversations.addEventListener('input', renderSidebar);

function renderWelcome() {
  const welcome = element('section', 'welcome');
  welcome.append(element('span', 'welcome-badge', 'Matchorakel'));
  const heading = element('h1');
  heading.append('Vilken match vill du analysera?');
  welcome.append(heading);
  welcome.append(element('p', '', 'Skriv två lag eller fråga om form, mål och matchdatum.'));
  welcome.append(element('div', 'suggestion-title', 'Exempel'));
  const suggestions = element('div', 'suggestions');
  const examples = ['Barcelona mot Real Madrid', 'Barcelona mot PSG, vad är vanligast?',
    'När spelar Barcelona i Champions League?', 'Bayern mot Dortmund'];
  for (const example of examples) {
    const button = element('button', 'suggestion');
    button.type = 'button';
    button.append(element('span', '', example), element('span', '', '↗'));
    button.addEventListener('click', () => {
      input.value = example;
      form.requestSubmit();
    });
    suggestions.append(button);
  }
  welcome.append(suggestions);
  content.append(welcome);
}

function responseHeader(box) {
  const top = element('div', 'response-top');
  top.append(element('span', 'bot-mark', 'M'), element('span', 'response-meta', 'Matchorakel'));
  box.append(top);
}

function renderFixture(item) {
  const row = element('div', 'fixture-card');
  const when = item.utc_date ? new Date(item.utc_date) : null;
  const date = when && !Number.isNaN(when.getTime())
    ? new Intl.DateTimeFormat('sv-SE', {dateStyle: 'full', timeStyle: 'short', timeZone: 'Europe/Stockholm'}).format(when)
    : 'Datum saknas';
  row.append(element('span', 'fixture-date', `${date} · svensk tid`));
  row.append(element('strong', 'fixture-pair', `${item.home} – ${item.away}`));
  const venueText = item.venue_confidence === 'likely_home'
    ? `Trolig hemmaarena: ${item.venue} · inte bekräftad för matchen`
    : item.venue ? `Bekräftad arena: ${item.venue}` : 'Arena ännu inte bekräftad';
  row.append(element('span', 'fixture-venue', venueText));
  const lastSync = item.synced_at ? new Date(item.synced_at) : null;
  row.append(element('small', 'fixture-source', `Källa: ${item.source || 'okänd'} · hämtat ${lastSync && !Number.isNaN(lastSync.getTime()) ? lastSync.toLocaleDateString('sv-SE') : 'okänt datum'}`));
  return row;
}

function renderFixtures(box, data) {
  box.append(element('div', 'result-kicker', `${data.league_name} · PUBLICERAT SPELSCHEMA`));
  box.append(element('h2', 'result-title', data.title || 'Kommande matcher'));
  if (data.summary) box.append(element('p', 'result-summary', data.summary));
  for (const match of (Array.isArray(data.fixtures) ? data.fixtures : []))
    if (match && typeof match.home === 'string' && typeof match.away === 'string') box.append(renderFixture(match));
  if (['UCL', 'FAC', 'CDR', 'EL', 'UECL', 'DFB', 'CIT'].includes(data.league))
    box.append(element('p', 'source-note', `${data.league_name} visas som spelschema. Ingen separat modell har tränats för den cupen.`));
}

function renderPrediction(box, data) {
  const {home, away, probabilities: p} = data;
  if (typeof home !== 'string' || typeof away !== 'string' ||
      !p || !['H', 'D', 'A'].every(key => p[key] !== null && p[key] !== undefined &&
        Number.isFinite(Number(p[key])) && Number(p[key]) >= 0 && Number(p[key]) <= 100) ||
      Math.abs(['H', 'D', 'A'].reduce((sum, key) => sum + Number(p[key]), 0) - 100) > 0.3) {
    box.append(element('p', 'answer-text', 'Prognosens data saknas eller är ogiltig. Försök igen efter att modellerna uppdaterats.'));
    return;
  }
  const f = data.features || {};
  const labels = {H: `${home} vinner`, D: 'Oavgjort', A: `${away} vinner`};
  const favorite = ['H', 'D', 'A'].reduce((best, key) => p[key] > p[best] ? key : best, 'H');
  box.append(element('div', 'result-kicker', `${data.league_name} · MATCHPROGNOS`));
  const fixture = element('div', 'fixture-heading');
  fixture.append(teamBadge(home), element('h2', 'result-title', `${home} – ${away}`), teamBadge(away));
  box.append(fixture);
  if (data.fixture) box.append(renderFixture(data.fixture));
  const hasScoreline = data.scoreline && Number.isInteger(data.scoreline.home) && Number.isInteger(data.scoreline.away);
  if (hasScoreline) {
    const score = element('div', 'score-pick');
    const label = element('div', 'score-pick-label', 'Prediction');
    const value = element('strong', 'score-pick-value', `${home} ${data.scoreline.home}–${data.scoreline.away} ${away}`);
    const explanation = element('p', 'score-pick-detail',
      `${labels[favorite]} ${Number(p[favorite]).toFixed(1)} %. ${data.scoreline.source || 'Uppskattat målantal'}.`);
    score.append(label, value, explanation);
    box.append(score);
  }
  if (!hasScoreline) box.append(element('p', 'result-summary', `${labels[favorite]} ${Number(p[favorite]).toFixed(1)} %. Exakt resultattips saknas.`));
  if (['home_points','away_points','home_scored','away_scored','home_conceded','away_conceded'].every(key => Number.isFinite(f[key]))) {
    const compared = [];
    if (f.home_points !== f.away_points) {
      const stronger = f.home_points > f.away_points ? home : away;
      compared.push(`${stronger} har tagit ${Math.abs(f.home_points - f.away_points)} fler poäng på de fem senaste ligamatcherna.`);
    }
    if (f.home_scored !== f.away_scored) {
      const attack = f.home_scored > f.away_scored ? home : away;
      compared.push(`${attack} har gjort ${Math.abs(f.home_scored - f.away_scored)} fler mål under samma period.`);
    }
    if (f.home_conceded !== f.away_conceded) {
      const defense = f.home_conceded < f.away_conceded ? home : away;
      compared.push(`${defense} har släppt in ${Math.abs(f.home_conceded - f.away_conceded)} färre mål.`);
    }
    if (compared.length) box.append(element('p', 'result-summary', compared.slice(0, 2).join(' ')));
  }
  const outcomes = element('div', 'outcomes');
  for (const key of ['H', 'D', 'A']) {
    const card = element('div', `outcome${key === favorite ? ' best' : ''}`);
    card.append(element('div', 'outcome-label', labels[key]));
    card.append(element('div', 'outcome-number', `${Number(p[key]).toFixed(1)} %`));
    const track = element('div', 'outcome-track');
    const fill = element('div', 'outcome-fill');
    fill.style.width = `${Math.max(0, Math.min(100, Number(p[key])))}%`;
    track.append(fill);
    card.append(track);
    outcomes.append(card);
  }
  box.append(outcomes);
  const markets = data.goal_markets && typeof data.goal_markets === 'object' ?
    Object.entries(data.goal_markets).filter(([key, value]) =>
      ['over_1_5', 'over_2_5', 'both_score'].includes(key) && Number.isFinite(Number(value))) : [];
  if (markets.length) {
    const summary = element('p', 'result-summary', 'Målmodell: ' +
      markets.map(([key, value]) => `${{over_1_5:'minst 2 mål',over_2_5:'minst 3 mål',both_score:'båda lagen gör mål'}[key]} ${Number(value).toFixed(1)} %`).join(' · ') + '.');
    box.append(summary);
  }
  const facts = element('div', 'facts');
  for (const [team, points, scored, conceded, recent] of [
    [home, f.home_points, f.home_scored, f.home_conceded, data.recent?.home],
    [away, f.away_points, f.away_scored, f.away_conceded, data.recent?.away]
  ]) {
    const block = element('div');
    block.append(element('h3', 'fact-heading', `${team} · senaste 5`));
    const record = recent && [recent.wins, recent.draws, recent.losses].every(Number.isFinite)
      ? `${recent.wins} vinster, ${recent.draws} oavgjorda, ${recent.losses} förluster. ` : '';
    block.append(element('p', 'fact-text', [points, scored, conceded].every(Number.isFinite)
      ? `${record}${points} av 15 poäng · ${scored} gjorda mål · ${conceded} insläppta mål i ligan.`
      : 'Lagstatistik saknas i svaret.'));
    if (Array.isArray(recent?.sequence)) {
      const strip = element('div', 'form-sequence');
      const games = recent.sequence.filter(game => game && typeof game === 'object');
      strip.setAttribute('aria-label', `Form, äldst först: ${games.map(game => game.points === 3 ? 'vinst' : game.points === 1 ? 'oavgjort' : 'förlust').join(', ')}`);
      for (const game of games) {
        const status = game.points === 3 ? 'win' : game.points === 1 ? 'draw' : 'loss';
        const pill = element('span', `form-pill ${status}`, status === 'win' ? 'V' : status === 'draw' ? 'O' : 'F');
        pill.setAttribute('aria-hidden', 'true');
        strip.append(pill);
      }
      block.append(strip);
    }
    facts.append(block);
  }
  box.append(facts);
  if (data.additional_factors && Number.isFinite(Number(data.additional_factors.home_elo)) && Number.isFinite(Number(data.additional_factors.away_elo)))
    box.append(element('p', 'source-note', `Lagstyrka i modellen: ${Math.round(data.additional_factors.home_elo)} / ${Math.round(data.additional_factors.away_elo)} Elo.`));
  box.append(element('p', 'source-note', `${data.league_name || 'Liga'} · senaste resultat ${data.as_of || 'okänt'}`));
  if (data.fixture?.utc_date) {
    if (data.actual_result?.status === 'finished') {
      const result = data.actual_result;
      const predicted = ['H','D','A'].reduce((best, key) => p[key] > p[best] ? key : best, 'H');
      box.append(element('p', 'source-note', `Facit: ${result.home_goals}–${result.away_goals}. Modellens mest troliga resultat var ${labels[predicted].toLowerCase()} och blev ${predicted === result.outcome ? 'rätt' : 'fel'}. Källa: ${result.source}.`));
    } else {
      const verify = element('button', 'result-check', 'Kontrollera utfallet efter matchen');
      verify.type = 'button';
      verify.addEventListener('click', async () => {
        verify.disabled = true;
        try {
          const args = new URLSearchParams({league: data.league, home: data.home, away: data.away, date: data.fixture.utc_date});
          const response = await fetch(`/api/match/result?${args}`);
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || 'Resultatet kunde inte kontrolleras.');
          data.actual_result = result;
          saveConversations();
          if (result.status === 'finished') render();
          else verify.textContent = result.status === 'not_played' ? 'Matchen har inte börjat än' : 'Inget bekräftat resultat hittades';
        } catch (error) { verify.textContent = error.message; }
      });
      box.append(verify);
    }
  }
}

function teamBadge(name) {
  const badge = element('span', 'team-badge', name.split(' ').map(word => word[0]).slice(0, 2).join('').toUpperCase());
  badge.title = name;
  badge.setAttribute('aria-label', name);
  return badge;
}

function renderInsight(box, data) {
  box.append(element('div', 'result-kicker', `${data.league_name} · MATCHFAKTA`));
  box.append(element('h2', 'result-title', data.title));
  box.append(element('p', 'result-summary', data.summary));
  if (data.fixture) box.append(renderFixture(data.fixture));
  const grid = element('div', 'insight-grid');
  for (const item of (Array.isArray(data.cards) ? data.cards : [])) {
    if (!item || typeof item !== 'object') continue;
    const card = element('div', 'insight-card');
    card.append(element('span', 'insight-label', item.label));
    card.append(element('strong', 'insight-value', item.value));
    card.append(element('span', 'insight-detail', item.detail));
    grid.append(card);
  }
  box.append(grid);
  if (Array.isArray(data.teams) && data.teams.length) {
    const teams = element('div', 'insight-teams');
    for (const team of data.teams) {
      if (!team || typeof team.name !== 'string') continue;
      const line = element('div', 'insight-team');
      line.append(teamBadge(team.name), element('span', 'insight-team-name', team.name));
      const games = element('div', 'form-sequence');
      for (const game of (Array.isArray(team.sequence) ? team.sequence : [])) {
        if (!game || typeof game !== 'object') continue;
        const status = game.points === 3 ? 'win' : game.points === 1 ? 'draw' : 'loss';
        const pill = element('span', `form-pill ${status}`, status === 'win' ? 'V' : status === 'draw' ? 'O' : 'F');
        pill.title = `${status === 'win' ? 'Vinst' : status === 'draw' ? 'Oavgjort' : 'Förlust'} · ${game.scored}–${game.conceded}`;
        games.append(pill);
      }
      line.append(games);
      teams.append(line);
    }
    box.append(teams);
  }
  box.append(element('p', 'source-note', `${data.source_note || 'Historiska ligamatcher'} · senast ${data.as_of || 'okänt'}`));
}

function renderTurn(turn, latest) {
  const wrapper = element('section', 'turn');
  wrapper.append(element('div', 'question', turn.question));
  const box = element('div', `response${turn.error ? ' error-response' : ''}`);
  responseHeader(box);
  if (turn.combined) {
    (Array.isArray(turn.combined.parts) ? turn.combined.parts : []).forEach((part, index) => {
      if (!part || typeof part !== 'object') return;
      if (index) box.append(element('hr', 'answer-divider'));
      if (part.kind === 'prediction') renderPrediction(box, part);
      else if (part.kind === 'insight') renderInsight(box, part);
      else if (part.kind === 'fixtures') renderFixtures(box, part);
      else box.append(element('p', 'answer-text', part.response || 'Jag behöver ett tydligare underlag för den delen.'));
    });
  }
  else if (turn.prediction) renderPrediction(box, turn.prediction);
  else if (turn.insight) renderInsight(box, turn.insight);
  else if (turn.fixtures) renderFixtures(box, turn.fixtures);
  else if (turn.text) {
    box.append(element('p', 'answer-text', turn.text));
    if (turn.source) box.append(element('p', 'source-note', turn.source));
  }
  else if (turn.error) box.append(element('p', '', turn.error));
  else {
    const loading = element('div', 'loading-row', 'Tittar på frågan');
    const dots = element('span', 'dots');
    dots.append(element('span'), element('span'), element('span'));
    loading.append(dots);
    box.append(loading);
  }
  if (turn.error) {
    const retry = element('button', 'result-check', 'Försök igen');
    retry.type = 'button';
    retry.addEventListener('click', () => { if (!busy) { input.value = turn.question; form.requestSubmit(); } });
    box.append(retry);
  }
  wrapper.append(box);
  if (latest && !turn.error && Array.isArray(turn.suggestions) && turn.suggestions.length) {
    const section = element('div', 'followups');
    section.append(element('span', 'followups-label', 'Fortsätt fråga'));
    for (const suggestion of turn.suggestions.slice(0, 3)) {
      if (typeof suggestion !== 'string' || !suggestion.trim()) continue;
      const button = element('button', 'followup', suggestion);
      button.type = 'button';
      button.addEventListener('click', () => {
        if (busy) return;
        input.value = suggestion;
        form.requestSubmit();
      });
      section.append(button);
    }
    wrapper.append(section);
  }
  content.append(wrapper);
}

function render() {
  input.placeholder = 'Fråga om en match eller ett lag ...';
  renderSidebar();
  content.replaceChildren();
  const conversation = activeConversation();
  if (!conversation?.messages.length) renderWelcome();
  else conversation.messages.forEach((turn, index) => renderTurn(turn, index === conversation.messages.length - 1));
  scrollToBottom();
}

openSidebarButton.addEventListener('click', () => {
  if (window.matchMedia?.('(min-width: 721px)').matches) {
    appShell.classList.toggle('sidebar-collapsed');
    openSidebarButton.setAttribute('aria-expanded', String(!appShell.classList.contains('sidebar-collapsed')));
    return;
  }
  const expanded = sidebar.classList.toggle('open');
  scrim.hidden = !expanded;
  openSidebarButton.setAttribute('aria-expanded', String(expanded));
});
document.querySelector('#closeSidebar').addEventListener('click', closeMenu);
scrim.addEventListener('click', closeMenu);
document.querySelector('#newChat').addEventListener('click', () => {
  if (pendingChat) pendingChat.abort();
  activeId = null;
  closeMenu();
  render();
  input.focus();
});
form.addEventListener('submit', async event => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question || busy) return;
  if (!activeConversation()) {
    const conversation = {id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, title: question, messages: []};
    conversations.unshift(conversation);
    activeId = conversation.id;
  }
  const conversation = activeConversation();
  const turn = {question};
  const previous = [...conversation.messages].reverse().find(item => item.topicReset || item.combined?.context || item.prediction?.context || item.prediction?.home || item.insight?.context || item.fixtures?.context || item.context);
  const rawContext = previous?.combined?.context || previous?.prediction?.context || previous?.insight?.context || previous?.fixtures?.context || previous?.context ||
    (previous?.prediction ? {home: previous.prediction.home, away: previous.prediction.away} : null);
  const context = previous?.topicReset ? null : rawContext ? {...rawContext, league: rawContext.league || previous?.prediction?.league || conversation.league} : null;
  const history = conversation.messages.slice(-20).map(item => ({question: item.question,
    answer: item.text || item.insight?.summary || item.combined?.parts?.map(part => part.summary || part.response || '').join(' ') || ''}));
  conversation.messages.push(turn);
  const requestedId = conversation.id;
  input.value = '';
  busy = true;
  sendButton.disabled = true;
  const controller = new AbortController();
  pendingChat = controller;
  const timeout = setTimeout(() => controller.abort(), 60000);
  saveConversations();
  render();
  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: question, context, history}), signal: controller.signal
    });
    const data = await response.json().catch(() => { throw new Error('Servern gav ett ogiltigt svar. Försök igen.'); });
    if (controller.signal.aborted) return;
    if (!response.ok) throw new Error(data.error || 'Kunde inte analysera matchen.');
    if (!data || typeof data !== 'object' || typeof data.kind !== 'string') throw new Error('Svaret saknar matchdata. Försök igen.');
    if ((data.kind === 'text' && (typeof data.response !== 'string' || !data.response.trim())) ||
        (data.kind === 'fixtures' && !Array.isArray(data.fixtures)) ||
        (data.kind === 'insight' && !Array.isArray(data.cards)) ||
        (data.kind === 'combined' && !Array.isArray(data.parts)) ||
        (data.kind === 'prediction' && (!data.probabilities || typeof data.probabilities !== 'object')) ||
        !['text','fixtures','insight','combined','prediction'].includes(data.kind))
      throw new Error('Servern gav ett ofullständigt svar. Försök igen.');
    turn.suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
    turn.analysisId = data.analysis_id;
    turn.createdAt = data.created_at;
    if (data.kind === 'text') {
      turn.text = data.response;
      turn.context = data.context;
      turn.source = data.source;
      turn.topicReset = Boolean(data.topic_reset);
    } else if (data.kind === 'insight') {
      turn.insight = data;
    } else if (data.kind === 'fixtures') {
      turn.fixtures = data;
    } else if (data.kind === 'combined') {
      turn.combined = data;
      turn.topicReset = Boolean(data.topic_reset);
    } else {
      turn.prediction = data;
    }
  } catch (error) {
    turn.error = controller.signal.aborted ? 'Anropet avbröts eller tog för lång tid. Försök igen.' : error.message || 'Kunde inte ansluta till servern.';
  } finally {
    clearTimeout(timeout);
    if (pendingChat === controller) pendingChat = null;
    busy = false;
    sendButton.disabled = false;
    saveConversations();
    if (activeId === requestedId) render();
    input.focus();
    refreshCapability();
  }
});

render();
function refreshCapability() { return fetch('/api/chat/status').then(reply => reply.json()).then(data => {
  document.querySelector('#openData').hidden = Boolean(data.public);
  chatCapability.textContent = data.ai_health === 'failed'
    ? `AI-tjänsten svarar inte${Number.isInteger(data.ai_error_code) ? ` (HTTP ${data.ai_error_code})` : ''} · matchfakta fungerar fortfarande`
    : data.ai_health === 'ok'
    ? 'AI-anslutningen fungerar'
    : data.language_model
    ? 'AI är inställd men anslutningen är ännu inte testad'
    : 'Fotbollsfrågor fungerar utan AI-anslutning';
}).catch(() => { chatCapability.textContent = 'Matchorakel · kontrollera att anslutningen fungerar'; }); }
refreshCapability();
