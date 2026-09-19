const form = document.querySelector('#composer');
const input = document.querySelector('#message');
const sendButton = document.querySelector('#sendButton');
const scroller = document.querySelector('#chat');
const content = document.querySelector('#chatContent');
const conversationsNode = document.querySelector('#conversations');
const undoToast = document.querySelector('#undoToast');
const sidebar = document.querySelector('#sidebar');
const scrim = document.querySelector('#scrim');
const openSidebarButton = document.querySelector('#openSidebar');
const panel = document.querySelector('#toolPanel');
const panelTitle = document.querySelector('#panelTitle');
const panelBody = document.querySelector('#panelBody');
const searchConversations = document.querySelector('#searchConversations');
const chatCapability = document.querySelector('#chatCapability');
const STORAGE_KEY = 'matchorakel-conversations-v1';
const FAVORITES_KEY = 'matchorakel-favorites-v1';
const LEAGUE_NAMES = {PL: 'Premier League', LL: 'La Liga', BL: 'Bundesliga', SA: 'Serie A', L1: 'Ligue 1'};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function readConversations() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    return Array.isArray(saved) ? saved.filter(item => item && typeof item.id === 'string' && Array.isArray(item.messages)).slice(0, 30) : [];
  } catch {
    return [];
  }
}

let conversations = readConversations();
let activeId = conversations[0]?.id || null;
let busy = false;
let undoTimer;
let matchesFilter = 'all';
let matchesVisible = 8;
let favorites = [];
try { favorites = JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]'); } catch { favorites = []; }
if (!Array.isArray(favorites)) favorites = [];
const favoriteKey = name => String(name || '').toLowerCase().replace(/\b(fc|cf)\b/g, '').replace(/[^a-zåäö0-9]/g, ' ').trim();

function toggleFavorite(name) {
  const key = favoriteKey(name);
  favorites = favorites.includes(key) ? favorites.filter(item => item !== key) : [...favorites, key];
  try { localStorage.setItem(FAVORITES_KEY, JSON.stringify(favorites)); } catch { /* Lokal lagring är valfri. */ }
}

function closePanel() { panel.hidden = true; }
document.querySelector('#closePanel').addEventListener('click', closePanel);

async function showMatches() {
  panel.hidden = false;
  panelTitle.textContent = 'Matcher och favoritlag';
  panelBody.replaceChildren(element('p', 'panel-muted', 'Hämtar publicerade matcher ...'));
  try {
    const response = await fetch('/api/fixtures');
    if (!response.ok) throw new Error('Kunde inte läsa schemat.');
    const fixtures = await response.json();
    panelBody.replaceChildren();
    const filters = element('div', 'match-filters');
    for (const [code, label] of [['all', 'Alla'], ['favorites', 'Favoriter'], ['PL', 'Premier League'],
      ['LL', 'La Liga'], ['BL', 'Bundesliga'], ['SA', 'Serie A'], ['L1', 'Ligue 1'], ['UCL', 'Champions League']]) {
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
        button.textContent === ({all:'Alla', favorites:'Favoriter', ...LEAGUE_NAMES, UCL:'Champions League'})[matchesFilter]);
      list.replaceChildren();
      const games = fixtures.filter(item => matchesFilter === 'all' ||
        (matchesFilter === 'favorites' ? [item.home, item.away].some(team => favorites.includes(favoriteKey(team))) : item.league === matchesFilter));
      list.append(element('p', 'panel-muted', `${games.length} kommande matcher · visa ${Math.min(matchesVisible, games.length)}`));
      if (!games.length) list.append(element('p', 'panel-muted', 'Inga matcher här ännu. Prova en annan liga eller uppdatera spelschemat.'));
      for (const game of games.slice(0, matchesVisible)) {
        const row = element('div', 'match-row');
        const date = game.utc_date ? new Date(game.utc_date) : null;
        const when = date && !Number.isNaN(date.getTime())
          ? new Intl.DateTimeFormat('sv-SE', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit', timeZone:'Europe/Stockholm'}).format(date) : 'Datum saknas';
        row.append(element('span', 'match-row-date', `${when} · ${LEAGUE_NAMES[game.league] || 'Champions League'}`));
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
  } catch (error) { panelBody.replaceChildren(element('p', 'panel-muted', error.message)); }
}

async function showDataStatus() {
  panel.hidden = false;
  panelTitle.textContent = 'Uppdatera data';
  panelBody.replaceChildren(element('p', 'panel-muted', 'Hämtar status ...'));
  try {
    const response = await fetch('/api/data/status');
    const data = await response.json();
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
  } catch (error) { panelBody.replaceChildren(element('p', 'panel-muted', error.message)); }
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
  openSidebarButton.setAttribute('aria-expanded', 'false');
}

function renderSidebar() {
  conversationsNode.replaceChildren();
  if (!conversations.length) {
    conversationsNode.append(element('p', 'empty-history', 'Dina analyser visas här när du har ställt din första fråga.'));
  }
  for (const conversation of conversations) {
    const query = searchConversations.value.trim().toLocaleLowerCase('sv');
    if (query && !conversation.title.toLocaleLowerCase('sv').includes(query) &&
        !conversation.messages.some(item => item.question.toLocaleLowerCase('sv').includes(query))) continue;
    const row = element('div', 'conversation-row');
    const button = element('button', `conversation${conversation.id === activeId ? ' active' : ''}`, conversation.title);
    button.type = 'button';
    button.title = conversation.title;
    button.addEventListener('click', () => {
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
}
searchConversations.addEventListener('input', renderSidebar);

function renderWelcome() {
  const welcome = element('section', 'welcome');
  welcome.append(element('span', 'welcome-badge', 'Din matchanalys börjar här'));
  const heading = element('h1');
  heading.append('Få ett nytt perspektiv på ');
  heading.append(element('em', '', 'nästa match.'));
  welcome.append(heading);
  welcome.append(element('p', '', 'Fem stora ligor i samma chatt. Skriv två lag för en match, eller fråga om form, mål, skott och kort. Jag hittar ligan och du kan fortsätta med följdfrågor.'));
  welcome.append(element('div', 'suggestion-title', 'PROVA EN FRÅGA'));
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
  top.append(element('span', 'bot-mark', 'M'), element('span', 'response-meta', 'MATCHORAKEL · ANALYS'));
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
  const stale = !lastSync || Number.isNaN(lastSync.getTime()) || Date.now() - lastSync.getTime() > 48 * 3600 * 1000;
  row.append(element('small', 'fixture-source', `Schema: ${item.source || 'okänt'} · hämtat ${lastSync && !Number.isNaN(lastSync.getTime()) ? lastSync.toLocaleDateString('sv-SE') : 'okänt datum'}. ${item.venue_confidence === 'likely_home' ? `Arena: ${item.venue_source || 'lagprofil'} · lagets ordinarie arena kan skilja sig från spelplatsen. ` : ''}${stale ? 'Uppgiften kan vara föråldrad – uppdatera spelschemat. ' : ''}Tider och arena kan ändras.`));
  return row;
}

function renderFixtures(box, data) {
  box.append(element('div', 'result-kicker', `${data.league_name} · PUBLICERAT SPELSCHEMA`));
  box.append(element('h2', 'result-title', data.title || 'Kommande matcher'));
  if (data.summary) box.append(element('p', 'result-summary', data.summary));
  for (const match of data.fixtures || []) box.append(renderFixture(match));
  if (data.league === 'UCL') box.append(element('p', 'source-note', 'Champions League visas som spelschema. Ingen separat Champions League-modell är tränad ännu.'));
}

function renderPrediction(box, data) {
  const {home, away, probabilities: p, features: f} = data;
  const labels = {H: `${home} vinner`, D: 'Oavgjort', A: `${away} vinner`};
  const favorite = ['H', 'D', 'A'].reduce((best, key) => p[key] > p[best] ? key : best, 'H');
  box.append(element('div', 'result-kicker', `${data.league_name} · MATCHPROGNOS`));
  const fixture = element('div', 'fixture-heading');
  fixture.append(teamBadge(home), element('h2', 'result-title', `${home} – ${away}`), teamBadge(away));
  box.append(fixture);
  if (data.fixture) box.append(renderFixture(data.fixture));
  box.append(element('p', 'result-summary', `Modellen ger ${labels[favorite].toLowerCase()} högst sannolikhet. Alla tre utfall är fortfarande möjliga.`));
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
  if (data.goal_markets && Object.keys(data.goal_markets).length) {
    const summary = element('p', 'result-summary', 'Målmarknader där en separat målmodell slog baslinjen på valideringsperioden: ' +
      Object.entries(data.goal_markets).map(([key, value]) => `${{over_1_5:'minst 2 mål',over_2_5:'minst 3 mål',both_score:'båda lagen gör mål'}[key]} ${Number(value).toFixed(1)} %`).join(' · ') + '.');
    box.append(summary);
  }
  const facts = element('div', 'facts');
  for (const [team, points, scored, conceded, recent] of [
    [home, f.home_points, f.home_scored, f.home_conceded, data.recent?.home],
    [away, f.away_points, f.away_scored, f.away_conceded, data.recent?.away]
  ]) {
    const block = element('div');
    block.append(element('h3', 'fact-heading', `${team} · senaste 5`));
    const record = recent ? `${recent.wins} vinster, ${recent.draws} oavgjorda, ${recent.losses} förluster. ` : '';
    block.append(element('p', 'fact-text', `${record}${points} av 15 poäng · ${scored} gjorda mål · ${conceded} insläppta mål i ligan.`));
    if (recent?.sequence) {
      const strip = element('div', 'form-sequence');
      strip.setAttribute('aria-label', `Form, äldst först: ${recent.sequence.map(game => game.points === 3 ? 'vinst' : game.points === 1 ? 'oavgjort' : 'förlust').join(', ')}`);
      for (const game of recent.sequence) {
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
  if (data.additional_factors && Object.keys(data.additional_factors).length) {
    box.append(element('p', 'source-note', `Modellen väger också in längre lagstyrka (hemma ${Math.round(data.additional_factors.home_elo)}, borta ${Math.round(data.additional_factors.away_elo)}) och antal vilodagar före matchen (hemma ${data.additional_factors.home_rest_days}, borta ${data.additional_factors.away_rest_days}). Dessa värden byggs enbart av tidigare ligamatcher.`));
  }
  box.append(element('p', 'source-note', `${data.league_name} · ${data.model} · Senaste match i modellens underlag: ${data.as_of}. ${data.fixture ? 'Datum och arena kommer från separat spelschema.' : 'Inget kommande datum har verifierats för den här matchen.'} Skador, startelvor och liveinformation ingår inte.`));
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
  for (const item of data.cards || []) {
    const card = element('div', 'insight-card');
    card.append(element('span', 'insight-label', item.label));
    card.append(element('strong', 'insight-value', item.value));
    card.append(element('span', 'insight-detail', item.detail));
    grid.append(card);
  }
  box.append(grid);
  if (data.teams?.length) {
    const teams = element('div', 'insight-teams');
    for (const team of data.teams) {
      const line = element('div', 'insight-team');
      line.append(teamBadge(team.name), element('span', 'insight-team-name', team.name));
      const games = element('div', 'form-sequence');
      for (const game of team.sequence || []) {
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
  box.append(element('p', 'source-note', `${data.source_note || 'Källa: historiska ligamatcher' } · Senaste resultat i underlaget: ${data.as_of || 'okänt datum'}. Historiken är inte en garanti för nästa match.`));
}

function renderTurn(turn, latest) {
  const wrapper = element('section', 'turn');
  wrapper.append(element('div', 'question', turn.question));
  const box = element('div', `response${turn.error ? ' error-response' : ''}`);
  responseHeader(box);
  if (turn.combined) {
    turn.combined.parts.forEach((part, index) => {
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
  if (turn.analysisId) box.append(element('small', 'source-note', `Svar ${turn.analysisId} · ${new Date(turn.createdAt).toLocaleString('sv-SE')}`));
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
  input.placeholder = 'Fråga om vad du vill ...';
  renderSidebar();
  content.replaceChildren();
  const conversation = activeConversation();
  if (!conversation?.messages.length) renderWelcome();
  else conversation.messages.forEach((turn, index) => renderTurn(turn, index === conversation.messages.length - 1));
  scrollToBottom();
}

openSidebarButton.addEventListener('click', () => {
  const expanded = sidebar.classList.toggle('open');
  scrim.hidden = !expanded;
  openSidebarButton.setAttribute('aria-expanded', String(expanded));
});
document.querySelector('#closeSidebar').addEventListener('click', closeMenu);
scrim.addEventListener('click', closeMenu);
document.querySelector('#newChat').addEventListener('click', () => {
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
  saveConversations();
  render();
  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: question, context, history})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Kunde inte analysera matchen.');
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
    turn.error = error.message || 'Kunde inte ansluta till servern.';
  } finally {
    busy = false;
    sendButton.disabled = false;
    saveConversations();
    if (activeId === requestedId) render();
    input.focus();
  }
});

render();
fetch('/api/chat/status').then(reply => reply.json()).then(data => {
  document.querySelector('#openData').hidden = Boolean(data.public);
  chatCapability.textContent = data.language_model
    ? 'Fråga om vad du vill · matchfakta kommer från sparade källor'
    : 'Samtal om alla ämnen kräver en AI-anslutning på servern';
}).catch(() => { chatCapability.textContent = 'Matchorakel · kontrollera att anslutningen fungerar'; });
