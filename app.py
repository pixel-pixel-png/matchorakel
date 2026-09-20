"""Lokal webbserver med en gemensam chatt för ligor och cuper."""
import json
import math
import os
import re
import threading
import time
import uuid
import sys
import socket
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from conversation import football_followup, parts_of_question, suggestions
from football import ALIASES, FEATURES, LEAGUES, clean_name, feature_row, find_teams, load_matches, parse_teams, recent_form, team_display
from fixtures import CUP_ALIASES, CUP_NAMES, fixture_public, home_venue, normalize_team, read_fixtures, upcoming_fixtures
from goal_model import GoalModel
from language_chat import connection_error_code, connection_health, general_answer, language_status, request_cancel, request_error, Cancelled
from chat_logic import route_question, resolve
from player_data import player_summary

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32768
PUBLIC_SITE = os.environ.get('MATCHORAKEL_PUBLIC') == '1'
if PUBLIC_SITE:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
states = {}
job_lock = threading.Lock()
chat_lock = threading.Lock()
chat_requests = defaultdict(deque)
total_requests = deque()
daily_requests = deque()
active_requests = {}
model_lock = threading.RLock()
job_status = {'running': False, 'message': 'Inga uppdateringar pågår.', 'log': []}


def model_path(league):
    candidate = ROOT / 'artifacts' / f'model_{league}.joblib'
    if league == 'PL' and not candidate.exists():
        # Äldre installationer kan fortfarande använda sin första PL-modell.
        return ROOT / 'artifacts' / 'model.joblib'
    return candidate


def get_state(league='PL'):
    if league not in LEAGUES:
        raise ValueError('Okänd liga.')
    if league not in states:
        path = model_path(league)
        if not path.exists():
            raise ValueError(f'Modellen för {LEAGUES[league]["name"]} saknas. Kör py fetch_data.py och py train_model.py.')
        # Ladda bara egna modeller: joblib-filer från andra kan innehålla kod.
        with model_lock:
            if league not in states:
                states[league] = joblib.load(path)
    return states[league]


def predict_match(home_team: str, away_team: str, league='PL') -> dict:
    saved = get_state(league)
    home, away = parse_teams(f'{home_team} mot {away_team}', saved['teams'], league)
    scheduled = upcoming_fixtures(ROOT, league, home, away)
    kickoff = scheduled[0]['utc_date'] if scheduled else datetime.now(timezone.utc).date().isoformat()
    features = feature_row(home, away, saved['history'], saved.get('venue_history'),
                           saved.get('ratings'), saved.get('last_played'), kickoff[:10])
    if features is None:
        raise ValueError('Det finns inte fem tidigare ligamatcher för båda lagen i underlaget.')
    model = saved['model']
    feature_names = saved.get('feature_names', FEATURES)
    probability = model.predict_proba(pd.DataFrame([features], columns=feature_names))[0]
    values = dict(zip(model.classes_, probability))
    if set(values) != {'H', 'D', 'A'} or any(not math.isfinite(float(v)) or not 0 <= float(v) <= 1 for v in values.values()) or abs(sum(values.values())-1) > .001:
        raise ValueError('Matchmodellens sannolikheter är ogiltiga.')
    if any(not math.isfinite(float(v)) for v in features.values()):
        raise ValueError('Matchstatistiken är ofullständig.')
    goal_markets = {}
    # En exakt resultatrad är en osäker punktprognos från målmodellen.
    # Den validerade 1X2-modellen nedan får behålla sina egna sannolikheter.
    score_source = 'Poissonmodell för mål · enskilda resultat ej separat validerade'
    if (saved.get('goal_model') and saved.get('goal_features') and
            hasattr(saved['goal_model'], 'home_') and hasattr(saved['goal_model'], 'away_')):
        goal_rows = pd.DataFrame([features], columns=saved['goal_features'])
        home_rate = float(saved['goal_model'].home_.predict(goal_rows)[0])
        away_rate = float(saved['goal_model'].away_.predict(goal_rows)[0])
    else:
        home_rate = (features['home_scored'] + features['away_conceded']) / 10
        away_rate = (features['away_scored'] + features['home_conceded']) / 10
        score_source = 'Grov uppskattning från lagens senaste fem matcher · ej validerad'
    if any(not math.isfinite(rate) or rate < 0 for rate in (home_rate, away_rate)):
        raise ValueError('Målmodellens värden är ogiltiga.')
    home_rate, away_rate = (max(.05, min(8., rate)) for rate in (home_rate, away_rate))
    score_matrix = GoalModel.matrix(home_rate, away_rate)
    most_likely = max(((h, a) for h in range(8) for a in range(8)),
                      key=lambda score: score_matrix[score[0], score[1]])
    if saved.get('goal_model') and saved.get('goal_market_enabled'):
        raw = saved['goal_model'].goal_markets(pd.DataFrame([features], columns=saved['goal_features']))[0]
        goal_markets = {market: round(raw[market] * 100, 1)
                        for market, enabled in saved['goal_market_enabled'].items() if enabled and market in raw and math.isfinite(float(raw[market])) and 0 <= raw[market] <= 1}
    return {
        'home': team_display(home, league), 'away': team_display(away, league),
        'league': league, 'league_name': LEAGUES[league]['name'],
        'probabilities': {label: round(float(values[label]) * 100, 1) for label in ('H', 'D', 'A')},
        'goal_markets': goal_markets,
        'scoreline': {'home': most_likely[0], 'away': most_likely[1],
                      'home_expected': round(home_rate, 2), 'away_expected': round(away_rate, 2),
                      'source': score_source},
        'as_of': saved['last_match'], 'model': saved['model_name'],
        'features': {name: features[name] for name in FEATURES},
        'additional_factors': {name: features[name] for name in ('home_elo', 'away_elo', 'home_rest_days', 'away_rest_days')
                               if name in feature_names},
        'recent': {'home': recent_form(saved['history'][home]),
                   'away': recent_form(saved['history'][away])},
        'fixture': fixture_public(scheduled[0], ROOT) if scheduled else None,
    }


def context_for(league, home=None, away=None):
    return {'league': league, 'home': home, 'away': away}


def text_response(message, league=None, home=None, away=None):
    return {'kind': 'text', 'response': message, 'league': league,
            'context': context_for(league, home, away) if league else None}


def insight(title, summary, league, cards, teams=None, home=None, away=None, as_of=None):
    return {'kind': 'insight', 'title': title, 'summary': summary,
            'league': league, 'league_name': CUP_NAMES.get(league, LEAGUES.get(league, {}).get('name')),
            'cards': cards, 'teams': teams or [], 'as_of': as_of,
            'context': context_for(league, home, away)}


def detect_league(message, context=None):
    """Prioritera hela lagnamn, sedan en uttrycklig liga, sist chattens kontext."""
    normalized = clean_name(message)
    ready = {code: get_state(code) for code in LEAGUES if model_path(code).exists()}
    names = {'PL': ('premier league', 'engelska ligan'),
             'LL': ('la liga', 'spanska ligan'),
             'BL': ('bundesliga', 'tyska ligan'),
             'SA': ('serie a', 'italienska ligan'),
             'L1': ('ligue 1', 'franska ligan')}
    explicit = [code for code, variants in names.items()
                if any(re.search(r'\b' + re.escape(value) + r'\b', normalized) for value in variants)]
    hits = {code: find_teams(message, state['teams'], code) for code, state in ready.items()}
    paired = [code for code, found in hits.items() if len(found) == 2]
    single = [code for code, found in hits.items() if len(found) == 1]
    if len(explicit) > 1:
        return None, 'Nämn en liga i taget så att jag vet vilka matchfiler du menar.'
    if len(paired) == 1:
        code = paired[0]
        if explicit and explicit[0] != code:
            return None, 'Lagen verkar höra till en annan liga än den du angav. Skriv två lag i samma liga.'
        return code, None
    if len(paired) > 1:
        return None, 'Jag hittade matchande namn i flera ligor. Skriv ligan eller ett tydligare lagnamn.'
    if len(single) > 1:
        return None, 'Lagen verkar spela i olika ligor. Modellerna är tränade på ligamatcher, så jag kan inte ge en trovärdig prognos för den matchen.'
    if single:
        code = single[0]
        if explicit and explicit[0] != code:
            return None, 'Laget och ligan du skrev verkar inte höra ihop. Kontrollera frågan.'
        return code, None
    if explicit:
        return explicit[0], None
    if isinstance(context, dict) and context.get('league') in ready:
        return context['league'], None
    return None, None


def requested_player(normalized, teams, league):
    """Identifiera namn i spelarfrågor utan att förväxla lagfrågor med spelare."""
    match = re.search(
        r'(?:far|kommer|har|kan|gor)\s+([a-z]+(?:\s+[a-z]+){0,2}?)\s+'
        r'(?:ett?\s+|minst\s+ett?\s+)?(?:skott|gult|gula|mal|assist)', normalized)
    if match and not find_teams(match.group(1), teams, league):
        return match.group(1)
    match = re.search(r'([a-z]+(?:\s+[a-z]+){0,2}?)\s+(?:gor|far)\s+(?:ett?\s+)?(?:mal|skott|gult|gula)', normalized)
    if match and not find_teams(match.group(1), teams, league):
        return match.group(1)
    for player in ('raphinha', 'mbappe', 'lewandowski', 'haaland', 'salah'):
        if re.search(r'\b' + player + r'\b', normalized):
            return player
    return None


def team_snapshot(saved, team, league):
    recent = recent_form(saved['history'][team])
    games = recent['sequence']
    return {
        'name': team_display(team, league), 'points': sum(game['points'] for game in games),
        'wins': recent['wins'], 'draws': recent['draws'], 'losses': recent['losses'],
        'scored': sum(game['scored'] for game in games),
        'conceded': sum(game['conceded'] for game in games),
        'sequence': games, 'shots_on_target': recent['shots_on_target'],
        'yellow_cards': recent['yellow_cards'],
        'scoring_games': sum(game['scored'] > 0 for game in games),
        'clean_sheets': sum(game['conceded'] == 0 for game in games),
        'high_goal_games': sum(game['scored'] + game['conceded'] >= 3 for game in games),
        'count': len(games),
    }


def fixture_answer(matches, league, home=None, away=None, title='Kommande matcher', summary=None):
    label = CUP_NAMES.get(league, LEAGUES.get(league, {}).get('name'))
    return {'kind': 'fixtures', 'league': league, 'league_name': label,
            'fixtures': [fixture_public(item, ROOT) for item in matches[:5]], 'title': title, 'summary': summary,
            'context': context_for(league, home, away)}


def ucl_team_matches(message, fixtures):
    """Matcha alias som PSG och Barça mot verkliga lag i publicerat schema."""
    known = set()
    for code in LEAGUES:
        if model_path(code).exists():
            known.update(find_teams(message, get_state(code)['teams'], code))
    normalized = clean_name(message)
    for fixture in fixtures:
        for name in (fixture['home'], fixture['away']):
            key = normalize_team(name, 'UCL')
            aliases = [key] + [alias for code in LEAGUES for alias, value in ALIASES[code].items() if value == key]
            if any(re.search(r'(?<![a-z0-9])' + re.escape(alias) + r'(?![a-z0-9])', normalized) for alias in aliases):
                known.add(key)
    return known


def unverified_cross_league_pair(message, context=None):
    """Två identifierade klubbar kan diskuteras utan att påstå att ett möte är schemalagt."""
    normalized = clean_name(message)
    found = []
    for code in LEAGUES:
        if not model_path(code).exists():
            continue
        for key in find_teams(message, get_state(code)['teams'], code):
            names = [key, *[alias for alias, value in ALIASES[code].items() if value == key]]
            positions = [hit.start() for name in names
                         for hit in re.finditer(r'(?<![a-z0-9])' + re.escape(name) + r'(?![a-z0-9])', normalized)]
            found.append((min(positions) if positions else len(normalized), code, key))
    if len(found) == 2 and found[0][1] != found[1][1]:
        found.sort()
        return tuple(team_display(key, code) for _, code, key in found)
    if isinstance(context, dict) and context.get('league') in CUP_NAMES and context.get('home') and context.get('away'):
        return context['home'], context['away']
    return None


def unverified_ucl_answer(message, context=None):
    pair = unverified_cross_league_pair(message, context)
    if not pair:
        return None
    home, away = pair
    return ucl_evidence([{'league': 'UCL', 'home': home, 'away': away, 'utc_date': None,
                          'venue': None, 'status': None}], message)


def ucl_evidence(matches, question, competition="UCL"):
    """Historiska observationer från ligorna; inga cup-odds eller säkra utfall."""
    fixture = matches[0]
    participants = []
    for name in (fixture['home'], fixture['away']):
        key = normalize_team(name, competition)
        for code in LEAGUES:
            if not model_path(code).exists():
                continue
            state = get_state(code)
            if key in state.get('teams', []):
                participants.append((name, code, state, key))
                break
    normalized = clean_name(question)
    time_query = (any(term in normalized for term in ('datum', 'arena', 'var spelas', 'spelschema', 'vilken tid', 'avspark'))
                  or bool(re.search(r'\bnar\b.*\b(match|spelar|spelas|borjar)\b', normalized)))
    player_query = any(term in normalized for term in ('raphinha', 'mbappe', 'lewandowski', 'haaland', 'assist', 'malskytt', 'vem gor mal', 'vem tror du gor mal', 'vilken spelare'))
    if time_query:
        if not fixture.get('utc_date'):
            return text_response('Jag kan prata om ' + fixture['home'] + ' och ' + fixture['away'] +
                                 ', men jag har inget verifierat matchdatum eller arena på servern just nu.',
                                 competition, fixture['home'], fixture['away'])
        return fixture_answer(matches, competition, fixture['home'], fixture['away'],
                              title='Tid och plats för matchen', summary='Matchdatum kommer från spelschemat. Lagets vanliga arena kan visas som trolig när matchens arena inte är bekräftad.')
    if player_query:
        if not fixture.get('utc_date'):
            return text_response('Jag saknar verifierad spelarstatistik och ett bekräftat schema för ' +
                                 fixture['home'] + ' och ' + fixture['away'] + '.',
                                 competition, fixture['home'], fixture['away'])
        return fixture_answer(matches, competition, fixture['home'], fixture['away'],
                              title='Spelarfrågan', summary='Jag har inte verifierade spelarsiffror eller startelvor för cupmatchen. Därför kan jag inte uppskatta spelarens skott, mål, assist eller kort. Matchens publicerade tid visas nedan.')
    if any(term in normalized for term in ('skada', 'skadad', 'avstangd', 'startelva')):
        if not fixture.get('utc_date'):
            return text_response('Jag har inga verifierade skador, startelvor eller matchdatum för ' +
                                 fixture['home'] + ' och ' + fixture['away'] + '.',
                                 competition, fixture['home'], fixture['away'])
        return fixture_answer(matches, competition, fixture['home'], fixture['away'],
                              title='Spelarfrånvaro', summary='Jag har ingen verifierad aktuell skade- eller startelvsinformation för matchen och kan inte räkna in den. Kontrollera lagens bekräftade uppgifter nära avspark.')
    if len(participants) < 2:
        if not fixture.get('utc_date'):
            return text_response('Jag saknar verifierat schema och tillräcklig ligahistorik för båda lagen.',
                                 competition, fixture['home'], fixture['away'])
        return fixture_answer(matches, competition, fixture['home'], fixture['away'],
                              title='Underlag saknas för matchanalys', summary='Jag har schemat, men saknar tränad historik för båda lagen. Kör py fetch_data.py och py train_model.py för lagstatistik. Jag kan inte avgöra vad som är säkrast i den här matchen.')
    score_request = any(term in normalized for term in
                        ('slutar', 'slutresultat', 'resultattips', 'resultatet blir', 'tippa', 'prediktion', 'prognos', 'vem vinner', 'tror du vinner', 'vad tror du'))
    if score_request and not any(term in normalized for term in ('skott', 'kort', 'gula')):
        first, second = participants[:2]
        home_games = list(first[2]['history'].get(first[3], []))[-5:]
        away_games = list(second[2]['history'].get(second[3], []))[-5:]
        if len(home_games) >= 5 and len(away_games) >= 5:
            home_rate = (sum(item[1] for item in home_games) / 5 + sum(item[2] for item in away_games) / 5) / 2
            away_rate = (sum(item[1] for item in away_games) / 5 + sum(item[2] for item in home_games) / 5) / 2
            grid = GoalModel.matrix(home_rate, away_rate)
            h, a = max(((h, a) for h in range(8) for a in range(8)), key=lambda score: grid[score])
            summary = ('En grov resultatuppskattning utifrån lagens fem senaste tidigare inhemska matcher, med mål för och emot. '
                       'Cupmatcher ingick inte i träningen och uppskattningen är inte validerad för cupspel.')
            if not fixture.get('utc_date'):
                summary += ' Jag kan inte bekräfta att mötet är inplanerat.'
            result = insight('Resultattips · explorativt', summary, competition,
                             [{'label': 'Resultattips', 'value': f'{first[0]} {h}–{a} {second[0]}',
                               'detail': 'Målsnitt från ligamatcher · ej validerad cup-prognos'}],
                             home=fixture['home'], away=fixture['away'],
                             as_of=max(first[2]['last_match'], second[2]['last_match']))
            if fixture.get('utc_date'):
                result['fixture'] = fixture_public(fixture, ROOT)
            result['source_note'] = 'Grov uppskattning från ligahistorik; ingen tränad cup-modell.'
            return result
    cards = []
    form_query = any(term in normalized for term in ('form', 'senaste', 'varfor', 'forklara', 'jamfor', 'battre'))
    shots = any(term in normalized for term in ('skott', 'avslut'))
    yellows = any(term in normalized for term in ('kort', 'varning'))
    goals = any(term in normalized for term in ('mal', 'gorar', 'malrik', 'bada lagen'))
    broad = any(term in normalized for term in ('sakrast', 'sakerast', 'sannolik', 'trolig', 'vinner', 'prognos', 'handa', 'hander', 'handelse', 'forvanta', 'vanligast', 'lapp', 'speltips'))
    if (form_query and not (shots or yellows or goals)) or not (shots or yellows or goals or broad):
        for name, code, state, key in participants:
            recent = team_snapshot(state, key, code)
            cards.append({'label': name, 'value': f'{recent["points"]} / 15',
                          'detail': f'Poäng i senaste 5 {LEAGUES[code]["name"]}-matcher · {recent["scored"]}–{recent["conceded"]} i mål'})
        title = 'Lagens form inför mötet'
    else:
        observations = []
        for name, code, state, key in participants:
            events = list((state.get('event_history') or {}).get(key, []))
            if shots or broad:
                recorded = [event['shots'] for event in events if isinstance(event, dict)
                            and isinstance(event.get('shots'), (int, float))]
                observations.extend([(f'{name}: minst {minimum} skott på mål', [value >= minimum for value in recorded])
                                     for minimum in (3, 4)])
            if yellows or broad:
                recorded = [event['cards'] for event in events if isinstance(event, dict)
                            and isinstance(event.get('cards'), (int, float))]
                observations.extend([(f'{name}: minst {minimum} gula kort', [value >= minimum for value in recorded])
                                     for minimum in (2, 3)])
        if goals or broad:
            totals = [event['total_goals'] for _, _, state, key in participants
                      for event in (state.get('event_history') or {}).get(key, [])
                      if isinstance(event, dict) and isinstance(event.get('total_goals'), (int, float))]
            observations.extend([(f'Minst {minimum} mål i matchen', [value >= minimum for value in totals])
                                 for minimum in (3, 4)])
        for label, values in observations:
            if len(values) >= 12:
                count = sum(values)
                frequency = count / len(values)
                z = 1.96
                lower = (frequency + z*z/(2*len(values)) - z*math.sqrt(frequency*(1-frequency)/len(values) + z*z/(4*len(values)**2))) / (1 + z*z/len(values))
                category = 'kort' if 'kort' in label else 'skott' if 'skott' in label else 'mål'
                cards.append((lower, category, {'label': label, 'value': f'{count} / {len(values)}',
                                                'detail': 'Observerat i tidigare ligamatcher; ingen matchprognos'}))
        ordered = sorted(cards, key=lambda item: item[0], reverse=True)
        selected = []
        if broad:
            for category in ('mål', 'kort', 'skott'):
                first = next((item for item in ordered if item[1] == category), None)
                if first:
                    selected.append(first)
        selected.extend(item for item in ordered if item not in selected)
        cards = [card for _, _, card in selected[:5]]
        title = 'Vanligast i lagens ligamatcher'
    if not cards:
        if not fixture.get('utc_date'):
            return text_response('Jag saknar verifierat spelschema och tillräckligt många tidigare händelser för de lagen.',
                                 competition, fixture['home'], fixture['away'])
        return fixture_answer(matches, competition, fixture['home'], fixture['away'],
                              title='Historiska händelser saknas', summary='Matchen är publicerad, men det finns för få registrerade händelser för att besvara frågan. Jag kan inte kalla något säkert.')
    missing = [name for name, _, state, key in participants
               if not form_query and len((state.get('event_history') or {}).get(key, [])) < 12]
    summary = ('Detta är tidigare utfall i lagens respektive ligor, inte sannolikheter för den här cupmatchen. '
               'Motstånd, skador och startelvor ingår inte. Inget utfall är säkert.')
    if not fixture.get('utc_date'):
        summary = ('Jag har inget verifierat spelschema för just de här lagen: jag kan inte bekräfta att de möts. '
                   + summary)
    if missing:
        summary += ' Tillräcklig händelsestatistik saknas för ' + ', '.join(missing) + '.'
    result = insight(title, summary,
                     competition, cards, home=fixture['home'], away=fixture['away'],
                     as_of=max(state.get('last_match', '') for _, _, state, _ in participants))
    if fixture.get('utc_date'):
        result['fixture'] = fixture_public(fixture, ROOT)
    result['source_note'] = 'Historik från respektive inhemsk liga; ingen modell för den här cupen har tränats.'
    return result


def champions_answer(message, context=None):
    normalized = clean_name(message)
    explicit = any(term in normalized for term in ('champions league', 'ucl', 'championsligan'))
    previous = isinstance(context, dict) and context.get('league') == 'UCL'
    listing = any(term in normalized for term in ('kommande', 'spelschema', 'vilka matcher', 'nasta matcher'))
    if previous and not explicit and not football_followup(message):
        return None
    result_query = any(term in normalized for term in ('slutade', 'vad blev resultatet', 'vem vann', 'hur gick'))
    if result_query:
        finished = [item for item in read_fixtures(ROOT) if item.get('league') == 'UCL'
                    and item.get('status') == 'FINISHED' and isinstance(item.get('score'), dict)
                    and isinstance(item['score'].get('home'), int) and isinstance(item['score'].get('away'), int)]
        mentioned = ucl_team_matches(message, finished)
        if len(mentioned) == 2:
            past = [item for item in finished if mentioned ==
                    {normalize_team(item['home'], 'UCL'), normalize_team(item['away'], 'UCL')}]
            if past:
                selected = max(past, key=lambda item: item.get('utc_date') or '')
                score = selected['score']
                return fixture_answer([selected], 'UCL', selected['home'], selected['away'],
                                      title='Matchen är färdigspelad',
                                      summary=f'Resultat: {selected["home"]} {score.get("home")}–{score.get("away")} {selected["away"]}. Källa: football-data.org.')
    fixtures = upcoming_fixtures(ROOT, 'UCL')
    if not fixtures and not (explicit or previous):
        return None
    if not fixtures:
        return unverified_ucl_answer(message, context) or text_response(
            'Jag har inget verifierat Champions League-schema på servern just nu. '
            'Fråga om två lag så kan jag visa deras tidigare ligastatistik, men inget bekräftat matchdatum.')
    mentioned = ucl_team_matches(message, fixtures)
    if not mentioned and previous and isinstance(context, dict):
        mentioned = {normalize_team(context.get('home') or '', 'UCL'), normalize_team(context.get('away') or '', 'UCL')} - {''}
    if previous and not explicit and not mentioned and not listing:
        return text_response('Vilken Champions League-match menar du? Skriv båda lagen så kan jag svara om just den matchen.')
    if len(mentioned) > 1:
        matching = [item for item in fixtures if mentioned ==
                    {normalize_team(item['home'], 'UCL'), normalize_team(item['away'], 'UCL')}]
    elif len(mentioned) == 1:
        matching = [item for item in fixtures if next(iter(mentioned)) in
                    (normalize_team(item['home'], 'UCL'), normalize_team(item['away'], 'UCL'))]
    else:
        matching = fixtures if explicit or previous else []
    if not matching:
        return text_response('Jag hittar ingen kommande publicerad Champions League-match för de lagen. Kontrollera motståndare eller datum.') if explicit or previous else None
    if len(matching) > 1 and len(mentioned) == 1 and not listing:
        return fixture_answer(matching, 'UCL', title='Välj en match',
                              summary='Laget har flera kommande matcher. Ange båda lagen för en analys av en viss match.')
    if not (explicit or previous or len(mentioned) > 1):
        return None  # Enstaka klubb utan tävlingsnamn kan avse ligan.
    if not listing and not mentioned:
        return text_response('Vilken Champions League-match menar du? Skriv båda lagen för en analys av just den matchen.')
    if not listing and (len(mentioned) > 1 or previous and len(matching) == 1 and mentioned):
        return ucl_evidence(matching, message)
    return fixture_answer(matching, 'UCL',
                          title='Kommande Champions League-matcher',
                          summary='Skriv två lag eller välj en match för att få ett svar på mål, skott, kort, form eller speltid.')


def other_cup_answer(message, context=None):
    """Cupscheman och tydligt osäkra analyser av inhemsk ligahistorik."""
    normalized = clean_name(message)
    explicit = [code for code, names in CUP_ALIASES.items() if code != 'UCL'
                and any(re.search(r'\b' + re.escape(name) + r'\b', normalized) for name in names)]
    if len(explicit) > 1:
        return text_response('Vilken cup menar du? Ange en tävling i taget.')
    previous = context.get('league') if isinstance(context, dict) else None
    if not explicit and previous not in CUP_NAMES:
        return None
    if not explicit and (previous == 'UCL' or not football_followup(message)):
        return None
    code = explicit[0] if explicit else previous
    if code == 'UCL':
        return None
    name = CUP_NAMES[code]
    listing = any(term in normalized for term in ('kommande', 'spelschema', 'vilka matcher', 'nasta matcher'))
    known = [(league, found) for league in LEAGUES if model_path(league).exists()
             if (found := find_teams(message, get_state(league)['teams'], league))]
    if not explicit and any(len(found) == 2 for _, found in known):
        return None
    all_fixtures = upcoming_fixtures(ROOT, code)
    mentioned = ucl_team_matches(message, all_fixtures)
    if not mentioned and not explicit and isinstance(context, dict):
        mentioned = {normalize_team(context.get('home') or '', code),
                     normalize_team(context.get('away') or '', code)} - {''}
    result_query = any(term in normalized for term in ('hur slutade', 'vad blev resultatet', 'vem vann', 'hur gick det'))
    if result_query:
        finished = [item for item in read_fixtures(ROOT) if item.get('league') == code
                    and item.get('status') == 'FINISHED' and isinstance(item.get('score'), dict)
                    and isinstance(item['score'].get('home'), int) and isinstance(item['score'].get('away'), int)]
        past_teams = ucl_team_matches(message, finished)
        past = [item for item in finished if len(past_teams) == 2 and past_teams ==
                {normalize_team(item['home'], code), normalize_team(item['away'], code)}]
        if past:
            match = max(past, key=lambda item: item.get('utc_date') or '')
            score = match['score']
            return fixture_answer([match], code, match['home'], match['away'], title='Färdigspelad cupmatch',
                                  summary=f'Resultat: {match["home"]} {score["home"]}–{score["away"]} {match["away"]}. Källa: football-data.org.')
    if len(mentioned) > 1:
        matches = [item for item in all_fixtures if mentioned ==
                   {normalize_team(item['home'], code), normalize_team(item['away'], code)}]
    elif len(mentioned) == 1:
        matches = [item for item in all_fixtures if next(iter(mentioned)) in
                   (normalize_team(item['home'], code), normalize_team(item['away'], code))]
    else:
        matches = all_fixtures if listing or explicit else []
    if not matches:
        pair = unverified_cross_league_pair(message, context)
        if not pair:
            same_league = [(league, found) for league, found in known if len(found) == 2]
            if len(same_league) == 1:
                league, found = same_league[0]
                pair = tuple(team_display(key, league) for key in found)
        if pair and not listing:
            home, away = pair
            return ucl_evidence([{'league': code, 'home': home, 'away': away,
                                  'utc_date': None, 'venue': None}], message, code)
        return text_response(f'Inget verifierat kommande schema för {name} finns på servern. '
                             'Cupen kan saknas i datakällans plan; administratören kan uppdatera spelschemat. '
                             'Jag hittar inte på matcher eller datum.', code)
    if len(matches) > 1 and len(mentioned) == 1 and not listing:
        return fixture_answer(matches, code, title='Välj en cupmatch',
                              summary='Laget har flera kommande matcher. Ange båda lagen för en matchanalys.')
    if not listing and (len(mentioned) > 1 or len(matches) == 1 and mentioned):
        return ucl_evidence(matches, message, code)
    return fixture_answer(matches, code, title=f'Kommande matcher · {name}',
                          summary='Publicerat spelschema. Skriv båda lagen för analys utifrån lagens ligahistorik.')


def safest_history(saved, league, home, away):
    histories = saved.get('event_history') or {}
    if not home or not away or home not in histories or away not in histories:
        return text_response('Jag behöver en ny tränad modell och två lag i samma liga. Kör py train_model.py och skriv till exempel ”Barcelona mot Real Madrid”.', league, home, away)
    games = {home: [item for item in histories[home] if isinstance(item, dict)],
             away: [item for item in histories[away] if isinstance(item, dict)]}
    if min(map(len, games.values())) < 12:
        return text_response('Det finns för få tidigare matcher för att rangordna återkommande händelser utan att ge falsk precision.', league, home, away)
    candidates = []

    def add(category, label, observed):
        count, total = sum(observed), len(observed)
        if total < 12:
            return
        p = count / total
        z = 1.96
        lower = (p + z*z/(2*total) - z*math.sqrt(p*(1-p)/total + z*z/(4*total*total))) / (1 + z*z/total)
        candidates.append((lower, category, {'label': label, 'value': f'{count} / {total}',
                                             'detail': f'{p:.0%} i tidigare ligamatcher · ingen matchmodell för detta'}))

    forecast = predict_match(home, away, league)
    for market, label in (('over_2_5', 'Minst 3 mål totalt'), ('both_score', 'Båda lagen gör mål')):
        if market in forecast['goal_markets']:
            p = forecast['goal_markets'][market]
            candidates.append((p / 100, 'mål', {'label': label, 'value': f'{p:.1f} %',
                                                'detail': 'Målmodell testad på senare matcher'}))
    combined = games[home] + games[away]
    if not any(category == 'mål' for _, category, _ in candidates):
        add('mål', 'Minst 3 mål totalt', [item['total_goals'] >= 3 for item in combined
                                          if isinstance(item.get('total_goals'), (int, float))])
    for key in (home, away):
        label = team_display(key, league)
        for field, text, category, thresholds in (('cards', 'gula kort', 'kort', (2, 3)),
                                                   ('shots', 'skott på mål', 'skott', (3, 4))):
            recorded = [item[field] for item in games[key]
                        if isinstance(item.get(field), (int, float))]
            for threshold in thresholds:
                add(category, f'{label}: minst {threshold} {text}',
                    [value >= threshold for value in recorded])
    ordered = sorted(candidates, key=lambda item: item[0], reverse=True)
    selected = []
    for category in ('mål', 'kort', 'skott'):
        first = next((item for item in ordered if item[1] == category), None)
        if first:
            selected.append(first)
    selected.extend(item for item in ordered if item not in selected)
    if not selected:
        return text_response('Jag saknar tillräckligt underlag för meningsfulla mål-, kort- och skottförslag för lagen.', league, home, away)
    return insight('Möjliga utfall att jämföra',
                   'Målmodellens siffror är prognoser; skott och kort visar tidigare lagmatcher.',
                   league, [card for _, _, card in selected[:4]], home=home, away=away,
                   as_of=saved['last_match'])


def legacy_answer_single(message, context=None, history=None):
    plain = clean_name(message)
    if (('menade' in plain and 'inte' in plain) or 'istallet for' in plain) and isinstance(context, dict) and context.get('league') in LEAGUES:
        code = context['league']
        teams = get_state(code)['teams']
        before, after = re.split(r'\bistallet for\b|\binte\b', plain, maxsplit=1)
        new = find_teams(before, teams, code)
        old = find_teams(after, teams, code)
        pair = [context.get('home'), context.get('away')]
        if len(new) == len(old) == 1 and new[0] == old[0]:
            return text_response(f'{team_display(new[0], code)} och namnet du skrev syftar på samma lag. Skriv motståndaren om du vill ändra matchen.', code, *pair)
        if len(new) == 1 and len(old) == 1 and old[0] in pair and new[0] not in pair:
            pair[pair.index(old[0])] = new[0]
            return answer_single(f'{pair[0]} mot {pair[1]}', None, history)
        return text_response('Vilket av lagen vill du byta ut? Skriv till exempel ”Jag menade Real Madrid, inte Atlético Madrid”.', code, *pair)
    if plain in ('hej', 'tjena', 'tja', 'halloj', 'tack', 'tack sa mycket', 'okej tack'):
        result = text_response('Fråga om en match eller ett lag.')
        result['topic_reset'] = True
        return result
    if any(term in plain for term in ('vad kan du gora', 'vad kan jag fraga', 'hur fungerar chatten')) or plain == 'hjalp mig':
        return text_response('Du kan fråga om matchprognoser i fem ligor, lagens form, tidigare mål, skott och kort samt publicerade matchdatum i ligor och cuper när schemat finns. Jag svarar på följdfrågor om samma match. Frågor om spelares enskilda statistik kräver en särskild spelarfil; inga matchutfall är säkra.',
                             context.get('league') if isinstance(context, dict) else None,
                             context.get('home') if isinstance(context, dict) else None,
                             context.get('away') if isinstance(context, dict) else None)
    mentioned_teams = [find_teams(message, get_state(code)['teams'], code)
                       for code in LEAGUES if model_path(code).exists()]
    new_domestic_pair = any(len(found) == 2 for found in mentioned_teams)
    explicit_ucl = any(word in plain for word in ('champions league', 'ucl', 'championsligan'))
    explicit_cup = any(any(re.search(r'\b' + re.escape(name) + r'\b', plain) for name in names)
                       for names in CUP_ALIASES.values())
    explicit_domestic = any(term in plain for term in ('premier league', 'la liga', 'bundesliga', 'serie a', 'ligue 1'))
    changing_league = explicit_domestic and ('nu' in plain or 'menade' in plain or 'istallet' in plain)
    football_concept = any(term in plain for term in (
        'offside', 'falsk nia', 'pressmonster', 'pressing', 'bollinnehav',
        'xg', 'expected goals', 'frispark', 'straffspark', 'formation', 'uppstallning'))
    switch_from_ucl = new_domestic_pair and explicit_ucl and any(term in plain for term in
                       ('inte champions', 'inte ucl', 'slapp cl', 'glom psg', 'men nu',
                        'nu galler', 'ar klart', 'nasta fraga', 'varfor blandar du in'))
    cup = other_cup_answer(message, context)
    if cup:
        return cup
    champion = None if (new_domestic_pair and not explicit_ucl) or changing_league or switch_from_ucl else champions_answer(message, context)
    if champion:
        return champion
    league, issue = detect_league(message, context)
    if issue:
        if 'olika ligor' in issue and upcoming_fixtures(ROOT, 'UCL'):
            possible = champions_answer('Champions League ' + message)
            if possible and possible.get('kind') == 'fixtures':
                return possible
        if 'olika ligor' in issue:
            possible = unverified_ucl_answer(message)
            if possible:
                return possible
        return text_response(issue)
    if not league:
        normalized = clean_name(message)
        player = requested_player(normalized, [], 'PL') if any(term in normalized for term in ('skott pa mal', 'gula kort', 'gult kort', 'assist', 'gor mal')) else None
        if player:
            likely = {'raphinha': 'LL', 'lewandowski': 'LL', 'mbappe': 'LL',
                      'salah': 'PL', 'haaland': 'PL'}.get(player)
            if likely and model_path(likely).exists():
                league = likely
            else:
                return text_response(f'Jag saknar aktuell spelardata för {player.title()}. Skriv gärna spelarens liga och lägg till verifierade spelarmatcher i data/player_stats.csv för att se historiska utfall.')
    if not league:
        if 'vem gor mal' in clean_name(message) or 'vem tror du gor mal' in clean_name(message):
            return text_response('Vilken match menar du? Skriv båda lagen. Jag kan jämföra lagens tidigare mål och säga om en målmodell finns, men saknar data för att peka ut en enskild målskytt.')
        return text_response('Vilken match eller vilket lag menar du? Skriv till exempel ”Barcelona mot Real Madrid”.')
    saved = get_state(league)
    normalized = clean_name(message)
    teams = saved['teams']
    found = find_teams(message, teams, league)
    home = away = None
    if len(found) == 2:
        home, away = found
        if re.search(r'\b(?:borta|away)\s+(?:mot|against|at|hos)\b|\bat\b', normalized):
            home, away = away, home
    elif isinstance(context, dict) and context.get('league') == league:
        previous_home, previous_away = context.get('home'), context.get('away')
        if isinstance(previous_home, str) and isinstance(previous_away, str):
            try:
                home, away = parse_teams(f'{previous_home} mot {previous_away}', teams, league)
            except ValueError:
                pass
    # Ett nytt lagnamn ska inte låta en gammal match tolka resten av frågan.
    targets = found[:2] if found else ([home, away] if home and away else [])
    snapshots = [team_snapshot(saved, team, league) for team in targets]
    if home and away and re.search(r'\b(lapp|speltips|vad ska jag spela)\b', normalized):
        forecast = predict_match(home, away, league)
        candidates = []
        outcomes = forecast['probabilities']
        for key, label in (('H', f'{forecast["home"]} vinner'), ('D', 'Oavgjort'), ('A', f'{forecast["away"]} vinner')):
            candidates.append((outcomes[key], {'label': label, 'value': f'{outcomes[key]:.1f} %',
                                              'detail': 'Validerad 1X2-modell; ingen garanti'}))
        for key, label in (('over_1_5', 'Minst 2 mål'), ('over_2_5', 'Minst 3 mål'), ('both_score', 'Båda lagen gör mål')):
            if key in forecast.get('goal_markets', {}):
                probability = forecast['goal_markets'][key]
                candidates.append((probability, {'label': label, 'value': f'{probability:.1f} %',
                                                 'detail': 'Separat målmodell; ingen garanti'}))
        choices = [item for _, item in sorted(candidates, key=lambda pair: pair[0], reverse=True)[:3]]
        response = insight('Möjliga val att jämföra',
                           'Hög sannolikhet är inte samma sak som ett lönsamt spel. Jag har inga aktuella Unibet-odds; flera val på samma match är beroende av varandra och deras procentsatser får inte multipliceras. Kontrollera startelva och odds före beslut.',
                           league, choices, home=home, away=away, as_of=saved['last_match'])
        response['fixture'] = forecast.get('fixture')
        response['source_note'] = 'Modell för slutresultat och mål; inga liveodds eller säkra spel.'
        return response
    if any(term in normalized for term in ('sakrast', 'sakerast', 'mest troligt', 'troligast', 'vad ar mest sannolikt', 'vanligast')):
        return safest_history(saved, league, home, away)
    if len(found) == 1 and (any(term in normalized for term in ('hemmaarena', 'hemma arena', 'stadion', 'stadium')) or
                             ('spelar' in normalized and 'hemma' in normalized and not home)):
        estimated = home_venue(ROOT, league, found[0])
        if estimated.get('venue'):
            return text_response(f'{team_display(found[0], league)} har {estimated["venue"]} som ordinarie hemmaarena enligt {estimated.get("source", "lagprofilen")}. Kontrollera arenan för en specifik match i schemat.', league)
        return text_response('Jag har ingen verifierad ordinarie arena för det laget ännu. Uppdatera spelschema och lagprofiler för att hämta den.', league)
    wants_time_or_place = bool(re.search(
        r'\b(?:nar|datum\w*|matchdatum\w*|starttid\w*|avspark\w*|arena\w*|hemmaarena\w*|stadion\w*|stadium\w*|spelplats\w*|'
        r'klockan|tid|imorgon|vilken dag|vilken kvall|var|vart|vilken plan|plats\w*|stapeln|camp nou|sanchez pizjuan|'
        r'nasta match\w*|spelschema)\b', normalized))
    only_match_outcome = any(term in normalized for term in ('vem vinner', 'vinstchans', 'prognos')) and not any(
        term in normalized for term in ('nar', 'datum', 'arena', 'avspark', 'var spelas'))
    if wants_time_or_place and not only_match_outcome:
        fixtures = upcoming_fixtures(ROOT, league, home, away) if home and away and len(found) != 1 else (
            upcoming_fixtures(ROOT, league, team=found[0]) if len(found) == 1 else [])
        if fixtures:
            return fixture_answer(fixtures, league, home, away)
        if home and away:
            reverse = upcoming_fixtures(ROOT, league, away, home)
            if reverse:
                return fixture_answer(reverse, league, away, home,
                                      title='Match med omvänt hemmalag',
                                      summary=(f'Inget kommande datum finns publicerat för {team_display(home, league)} '
                                               f'hemma mot {team_display(away, league)}. Matchen nedan spelas '
                                               f'med {team_display(away, league)} som hemmalag.'))
            return text_response(f'Jag hittar ingen kommande match med {team_display(home, league)} hemma mot '
                                 f'{team_display(away, league)} i det publicerade schemat.', league, home, away)
        return text_response('Jag hittar inget publicerat kommande datum för den frågan.', league, home, away)
    if any(term in normalized for term in ('skadad', 'skadade', 'skada', 'skador', 'avstangd', 'saknas i startelvan', 'vansterback')):
        return text_response('En skadad ytterback kan påverka matchbilden, men jag kan inte verifiera aktuell frånvaro eller översätta den till en procentsats för en spelares mål eller skott. Modellen tar ännu inte in skador, startelvor eller förväntade minuter. Kontrollera bekräftade uppgifter nära avspark.', league, home, away)
    shot_query = any(word in normalized for word in ('skott pa mal', 'shots on target', 'avslut pa mal'))
    card_query = any(word in normalized for word in ('gula kort', 'gult kort', 'yellow card', 'varningar'))
    if any(term in normalized for term in ('vem gor mal', 'vem tror du gor mal', 'vilken spelare gor mal', 'vem blir malskytt')):
        if not home or not away:
            return text_response('Skriv först vilka två lag du menar. Jag kan jämföra lagens målstatistik men saknar data för en säker prognos om en enskild målskytt.', league)
        rows = [team_snapshot(saved, key, league) for key in (home, away)]
        cards = [{'label': item['name'], 'value': f'{item["scoring_games"]} av {item["count"]}',
                  'detail': 'Matcher med minst ett gjort mål · senaste ligamatcherna'} for item in rows]
        if saved.get('goal_market_enabled', {}).get('both_score'):
            forecast = predict_match(home, away, league)
            cards.append({'label': 'Båda lagen gör mål',
                          'value': f'{forecast["goal_markets"]["both_score"]:.1f} %',
                          'detail': 'Separat målmodell · osäker prognos för lagen'})
        return insight('Vilka kan göra mål?', 'Om du menar en enskild spelare kan jag inte utse en trovärdig målskytt: spelarhistorik, startelvor och förväntade minuter saknas. Här är bara lagens tidigare mål och eventuell testad målmodell.',
                       league, cards, home=home, away=away, as_of=saved['last_match'])
    player = requested_player(normalized, teams, league) if (shot_query or card_query or 'malskytt' in normalized or 'assist' in normalized or 'gor mal' in normalized) else None
    if player:
        observed = player_summary(ROOT / 'data' / 'player_stats.csv', league, player, saved['last_match'])
        if observed and (shot_query or card_query):
            count = observed['shots'] if shot_query else observed['cards']
            games = observed['shot_matches'] if shot_query else observed['card_matches']
            label = 'skott på mål' if shot_query else 'gula kort'
            return insight(observed['player'], 'Tidigare utfall, inte en sannolikhet för nästa match.',
                           league, [{'label': label.capitalize(), 'value': str(count),
                                     'detail': f'I {games} av {observed["matches"]} registrerade matcher'}],
                           home=home, away=away, as_of=observed['last_date'])
        return text_response(f'Jag saknar verifierade spelarmatcher för {player.title()}. Lagens CSV-filer innehåller inte enskilda spelares skott eller kort. En fil med verkliga matcher i data/player_stats.csv gör att jag kan visa historiken, men inte lova vad som händer i nästa match.', league, home, away)

    goal_market = ('both_score' if any(term in normalized for term in ('bada lagen gor mal', 'bada lagen gora mal', 'gor bada lagen mal', 'btts')) else
                   'over_2_5' if any(term in normalized for term in ('over 2 5', 'mer an 2 5', 'minst 3 mal', 'tre mal')) else
                   'over_1_5' if any(term in normalized for term in ('over 1 5', 'minst 2 mal')) else None)
    if goal_market and home and away:
        forecast = predict_match(home, away, league)
        validated = goal_market in forecast['goal_markets']
        if validated:
            probability = forecast['goal_markets'][goal_market]
        else:
            rates = forecast['scoreline']
            matrix = GoalModel.matrix(rates['home_expected'], rates['away_expected'])
            if goal_market == 'both_score':
                probability = float(matrix[1:, 1:].sum() * 100)
            else:
                boundary = 3 if goal_market == 'over_2_5' else 2
                probability = float(sum(matrix[h, a] for h in range(12) for a in range(12)
                                        if h + a >= boundary) * 100)
        label = {'both_score': 'Båda lagen gör mål', 'over_2_5': 'Minst 3 mål',
                 'over_1_5': 'Minst 2 mål'}[goal_market]
        odds_match = re.search(r'\bodds\s*(\d+[,.]\d{1,3})\b', message.lower())
        odds_note = ''
        if odds_match and validated:
            odds = float(odds_match.group(1).replace(',', '.'))
            if 1.01 <= odds <= 100:
                threshold = 100 / odds
                odds_note = (f' Du angav odds {odds:.2f}; nollpunkten före insats- och marknadsrisk är {threshold:.1f} %. '
                             f'Modellens uppskattning ligger {probability - threshold:+.1f} procentenheter från den nivån. '
                             'Detta är ingen bekräftad aktuell Unibet-kurs eller garanti för spelvärde.')
        summary = ('Uppskattning från en separat målmodell som slog baslinjen på valideringsperioden.' if validated else
                   'Grov Poissonuppskattning utifrån förväntade mål i modellen. Denna målmarknad klarade inte validering mot baslinjen och procentsatsen är inte en testad matchprognos.')
        response = insight(label, summary,
                           league, [{'label': label, 'value': f'{probability:.1f} %',
                                     'detail': 'Validerad målmarknad · ingen garanti' if validated else 'Explorativ uppskattning · använd inte som säkert spel'}],
                           home=home, away=away, as_of=saved['last_match'])
        response['summary'] += odds_note
        response['source_note'] = 'Målmodellens uppskattning · inte xG från matchhändelser.'
        response['fixture'] = forecast.get('fixture')
        return response

    if shot_query or card_query:
        metric = 'shots_on_target' if shot_query else 'yellow_cards'
        label = 'Skott på mål' if shot_query else 'Gula kort'
        if not snapshots:
            return text_response(f'Vilket lag menar du? Skriv till exempel ”Hur många {label.lower()} har Bayern haft?”.', league, home, away)
        asks_future = bool(re.search(r'\b(?:far|kommer|tror|blir det|nasta match|over|minst)\b', normalized))
        boundary = re.search(r'\b(over|mer an|minst)\s+(\d{1,2})\b', normalized)
        if asks_future:
            threshold = int(boundary.group(2)) + (boundary.group(1) != 'minst') if boundary else (4 if shot_query else 2)
            event_key = 'shots' if shot_query else 'cards'
            cards = []
            for key in targets:
                events = (saved.get('event_history') or {}).get(key, [])
                observed = [item[event_key] for item in events if isinstance(item, dict)
                            and isinstance(item.get(event_key), (int, float))]
                if len(observed) >= 12:
                    count = sum(value >= threshold for value in observed)
                    cards.append({'label': f'{team_display(key, league)}: minst {threshold} {label.lower()}',
                                  'value': f'{count} av {len(observed)}',
                                  'detail': f'{count / len(observed):.0%} i tidigare ligamatcher; ingen testad matchprognos'})
            if cards:
                response = insight(f'{label} · möjlig matchbild',
                                   f'Jag skulle jämföra gränsen minst {threshold} {label.lower()} med lagens tidigare utfall nedan. Motstånd, startelva och matchtempo kan ändra det; siffrorna är historik och kan inte användas som säker sannolikhet för nästa match.',
                                   league, cards, home=home, away=away, as_of=saved['last_match'])
                response['source_note'] = 'Tidigare lagmatcher med registrerade händelser; ingen tränad modell för nästa matchs skott eller kort.'
                return response
            return text_response(f'Jag kan inte ge en underbyggd prognos för {label.lower()}: färre än 12 tidigare matcher med den statistiken finns för lagen. Lagmodellen för slutresultat uppskattar inte enskilda skott eller kort.', league, home, away)
        cards = []
        for team in snapshots:
            observation = team[metric]
            cards.append({'label': team['name'],
                          'value': f'{observation["total"] / observation["matches"]:.1f} per match' if observation else '–',
                          'detail': f'{observation["total"]} totalt i {observation["matches"]} av de senaste {team["count"]} matcherna' if observation else f'{label} saknas i de senaste matchfilerna'})
        return insight(label + ' · lagstatistik', 'Antal registrerade händelser för laget, inte en spelarprognos.',
                       league, cards, home=home, away=away, as_of=saved['last_match'])

    if any(term in normalized for term in ('varfor', 'hur kommer det sig', 'forklara')):
        if not home or not away:
            return text_response('Skriv först två lag, till exempel ”Inter mot Milan”. Sedan kan du fråga ”Varför?”.', league)
        prediction = predict_match(home, away, league)
        rows = [team_snapshot(saved, key, league) for key in (home, away)]
        cards = [
            {'label': team['name'], 'value': f'{team["points"]} / 15',
             'detail': f'Poäng · {team["scored"]} gjorda mål · {team["conceded"]} insläppta'}
            for team in rows]
        summary = ('Modellen väger in poäng och mål från de fem senaste ligamatcherna och vem som spelar hemma. '
                   + ('Även de senaste hemma- respektive bortamatcherna ingår. ' if 'hemmaplan' in prediction['model'] else '')
                   + ('Tidigare resultat över längre tid sammanfattas i Elo-lagstyrka och vilodagar ingår inför avspark. ' if prediction['additional_factors'] else
                      'Långsiktig lagstyrka och vilodagar prövades också, men valideringen valde en enklare modell. ')
                   + 'Siffrorna beskriver indata; en enskild siffra förklarar inte ensam sannolikheten.')
        return insight('Därför ser prognosen ut så här', summary, league, cards,
                       teams=rows, home=home, away=away, as_of=saved['last_match'])

    if any(term in normalized for term in ('testresultat', 'hur bra', 'hur saker', 'traffsaker', 'utvardering', 'log loss', 'brier')):
        path = ROOT / 'artifacts' / f'evaluation_{league}.json'
        if not path.exists():
            return text_response('Kör py train_model.py för att skapa ett utvärderingsresultat.', league, home, away)
        report = json.loads(path.read_text(encoding='utf-8'))
        result = report['test'][report['selected_model']]
        return insight('Så gick det i testet', 'Siffrorna gäller den senare testperioden. Nya matcher kan ge andra resultat.', league,
                       [{'label': 'Rätt utfall', 'value': f'{result["accuracy"] * 100:.1f} %', 'detail': 'Andel rätt vald klass'},
                        {'label': 'Log loss', 'value': f'{result["log_loss"]:.3f}', 'detail': 'Lägre är bättre'},
                        {'label': 'Brier', 'value': f'{result["brier"]:.3f}', 'detail': 'Lägre är bättre'}],
                       home=home, away=away, as_of=report['periods']['test']['last'])

    high_goals = 'over 2 5' in normalized or 'over 2,5' in message.casefold() or 'mer an 2 5' in normalized
    clean_sheet = 'nollan' in normalized or 'clean sheet' in normalized
    both_score = 'bada lagen gor mal' in normalized or 'btts' in normalized
    form_query = any(term in normalized for term in ('form', 'senaste', 'mal', 'poang', 'vinster', 'jamfor', 'battre', 'forluster'))
    predict_query = any(term in normalized for term in
                        ('vem vinner', 'prognos', 'sannolikhet', 'vinstchans', 'hur gar matchen',
                         'tror du', 'tippar du', 'tippa', 'prediktion', 'slutar', 'slutresultat', 'resultattips'))
    defense_query = (any(term in normalized for term in ('forsvar', 'inslappta', 'slapper in', 'slappte in', 'baklangesmal', 'defensiv'))
                     or bool(re.search(r'\bslapp(?:er|te)\b(?:\s+\w+){0,4}\s+in\b', normalized)))
    attack_query = 'anfall' in normalized or 'gjorda mal' in normalized
    if snapshots and (high_goals or clean_sheet or both_score or defense_query or attack_query):
        key = ('high_goal_games' if high_goals else 'clean_sheets' if clean_sheet else
               'scoring_games' if both_score else 'conceded' if defense_query else 'scored')
        label = ('Minst 3 mål totalt' if high_goals else 'Hållna nollor' if clean_sheet else
                 'Matcher med gjorda mål' if both_score else 'Insläppta mål' if defense_query else 'Gjorda mål')
        cards = [{'label': team['name'], 'value': f'{team[key]} av {team["count"]}',
                  'detail': 'Senaste ligamatcherna, inte framtida odds'} if key in ('high_goal_games', 'clean_sheets', 'scoring_games')
                 else {'label': team['name'], 'value': str(team[key]),
                       'detail': f'Mål i de senaste {team["count"]} ligamatcherna'} for team in snapshots]
        return insight(label, 'Här visas historiska resultat. Modellen för slutresultat är inte tränad för att förutsäga just den här händelsen.',
                       league, cards, teams=snapshots, home=home, away=away, as_of=saved['last_match'])
    if snapshots and form_query and not predict_query:
        cards = [{'label': team['name'], 'value': f'{team["points"]} / 15',
                  'detail': f'{team["wins"]}V · {team["draws"]}O · {team["losses"]}F · {team["scored"]}–{team["conceded"]} i mål'}
                 for team in snapshots]
        comparison = ''
        if len(snapshots) == 2 and any(word in normalized for word in ('jamfor', 'battre', 'bast')):
            best = max(snapshots, key=lambda team: team['points'])
            comparison = (f'{best["name"]} tog fler poäng på de fem senaste matcherna. ' if snapshots[0]['points'] != snapshots[1]['points']
                          else 'Lagen tog lika många poäng i de fem senaste matcherna. ')
        return insight('Form senaste fem matcher', comparison + 'Poäng, mål och resultat i respektive liga.',
                       league, cards, teams=snapshots, home=home, away=away, as_of=saved['last_match'])
    if 'xg' in normalized and snapshots:
        return insight('Målutsikter utan xG-data',
                       'Jag saknar uppmätt expected goals (xG) och chansdata. Tabellen visar mål som faktiskt gjorts och släppts in i tidigare ligamatcher, inte xG.',
                       league, [{'label': team['name'], 'value': f'{team["scored"]}–{team["conceded"]}',
                                 'detail': f'Gjorda–insläppta mål senaste {team["count"]} matcherna'} for team in snapshots],
                       home=home, away=away, as_of=saved['last_match'])
    if home and away and (len(found) == 2 or predict_query):
        prediction = predict_match(home, away, league)
        prediction['kind'] = 'prediction'
        prediction['context'] = context_for(league, home, away)
        return prediction
    team_overview = any(term in normalized for term in
                        ('tycker', 'hur spelar', 'hur bra spelar', 'hur ser', 'styrkor', 'svagheter', 'laget just nu', 'lagets lage'))
    if snapshots and team_overview:
        return insight('Lagets aktuella ligahistorik',
                       'Utifrån senaste registrerade matcher: poäng och mål ger en bild av form och defensiv. Detta är historik; motstånd och laguppställning för nästa match kan ändra bilden.',
                       league, [{'label': team['name'], 'value': f'{team["points"]} / {3 * team["count"]}',
                                 'detail': f'{team["scored"]} gjorda och {team["conceded"]} insläppta mål i {team["count"]} matcher'}
                                for team in snapshots],
                       teams=snapshots, home=home, away=away, as_of=saved['last_match'])
    matches = upcoming_fixtures(ROOT, league, home, away) if home and away else []
    verified = {
        'liga': LEAGUES[league]['name'], 'senaste_resultat_i_modellen': saved['last_match'],
        'bekraftad_kommande_match': fixture_public(matches[0], ROOT) if matches else None,
        'laghistorik': [{key: row[key] for key in ('name', 'count', 'points', 'scored', 'conceded')}
                        for row in snapshots],
        'spelarstatistik': 'Inte tillgänglig utan verifierad spelarfil.',
        'xg_skador_startelvor': 'Saknas i underlaget.'}
    if home and away:
        try:
            forecast = predict_match(home, away, league)
            verified['modellprognos'] = {'scoreline': forecast['scoreline'],
                                        'sannolikheter': forecast['probabilities'],
                                        'malmarknader': forecast['goal_markets']}
        except ValueError:
            verified['modellprognos'] = None
    open_answer = general_answer(message, verified, history)
    if open_answer:
        result = text_response(open_answer, league, home, away)
        result['source'] = 'Språkmodell · använder bara tillgängligt underlag'
        return result
    if snapshots:
        return insight('Detta kan jag se om laget',
                       'Jag kan inte verifiera den särskilda uppgiften i frågan. Här finns i stället lagets senaste registrerade ligamatcher.',
                       league, [{'label': team['name'], 'value': f'{team["points"]} / {3 * team["count"]}',
                                 'detail': f'Poäng · {team["scored"]} gjorda och {team["conceded"]} insläppta mål'}
                                for team in snapshots],
                       teams=snapshots, home=home, away=away, as_of=saved['last_match'])
    return text_response('Jag kan visa matchprognoser, lagform, mål, hållna nollor, lagens skott och kort, samt modellens testresultat. Skriv ett lag eller två lag i någon av de fem ligorna. För individuella spelare krävs en separat verifierad spelarfil.', league, home, away)


def answer_single(message, context=None, history=None):
    handled = route_question(message, context, history, sys.modules[__name__])
    if handled is not None:
        return handled
    resolved, _, _ = resolve(message, context, sys.modules[__name__])
    if re.search(r'\b(menade|istallet for)\b', clean_name(message)):
        resolved = context
    return legacy_answer_single(message, resolved, history)


def answer_question(message, context=None, history=None):
    pieces = parts_of_question(message)[:3]
    if len(pieces) == 1:
        return answer_single(message, context, history)
    answers = []
    active = context
    # Om lagnamnen står i sista delfrågan gäller de hela den aktuella frågan.
    identified = [(code, found) for code in LEAGUES if model_path(code).exists()
                  if len(found := find_teams(message, get_state(code)['teams'], code)) == 2]
    if len(identified) == 1 and not any(name in clean_name(message) for names in CUP_ALIASES.values() for name in names):
        code, (home, away) = identified[0]
        active = context_for(code, home, away)
    for part in pieces:
        answer = answer_single(part, active, history)
        if answer.get('kind') == 'error':
            return answer
        answers.append(answer)
        if answer.get('topic_reset'):
            active = None
        elif answer.get('context'):
            active = answer['context']
    return {'kind': 'combined', 'parts': answers, 'context': active,
            'topic_reset': bool(answers[-1].get('topic_reset'))}


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/health')
def health():
    return jsonify(status='ok', ai_health=connection_health(),
                   ai_error_code=connection_error_code(),
                   leagues_ready=sum(model_path(code).exists() for code in LEAGUES))


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith('/api/') or request.path == '/chat':
        return jsonify(error='Adressen finns inte.'), 404
    return render_template('404.html'), 404


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error='Frågan är för stor. Skriv högst 2 000 tecken.'), 413


@app.get('/evaluation')
def evaluation():
    reports = []
    for code in LEAGUES:
        path = ROOT / 'artifacts' / f'evaluation_{code}.json'
        if path.exists():
            try:
                report = json.loads(path.read_text(encoding='utf-8'))
                valid_periods = (isinstance(report, dict) and isinstance(report.get('periods'), dict) and
                                 all(isinstance(report['periods'].get(period), dict) and
                                     all(key in report['periods'][period] for key in ('first', 'last', 'matches'))
                                     for period in ('train', 'validation', 'test')))
                valid_metrics = (isinstance(report, dict) and isinstance(report.get('test'), dict) and
                                 all(isinstance(metric, dict) and all(key in metric for key in
                                     ('accuracy', 'log_loss', 'brier')) for metric in report['test'].values()))
                valid_metrics = valid_metrics and all(
                    isinstance(metric[k], (int,float)) and not isinstance(metric[k], bool) and math.isfinite(metric[k]) and metric[k]>=0
                    for metric in report.get('test', {}).values() for k in ('accuracy','log_loss','brier'))
                if valid_periods and valid_metrics and all(key in report for key in
                    ('league', 'source_matches', 'selected_model')):
                    benchmark = report.get('odds_benchmark')
                    valid_benchmark = isinstance(benchmark, dict) and isinstance(benchmark.get('matches'), int) and all(
                        isinstance(benchmark.get(section),dict) and all(isinstance(benchmark[section].get(k),(int,float)) and math.isfinite(benchmark[section][k]) for k in ('accuracy','log_loss'))
                        for section in ('market','selected_model_same_matches'))
                    if not valid_benchmark:
                        report['odds_benchmark'] = None
                    reports.append(report)
            except (OSError, ValueError, UnicodeError):
                app.logger.warning('Utvärderingsfilen för %s kunde inte läsas.', code)
    return render_template('evaluation.html', reports=reports)


@app.get('/api/leagues')
def leagues():
    return jsonify([{'code': code, 'name': meta['name'], 'ready': model_path(code).exists()}
                    for code, meta in LEAGUES.items()])


@app.get('/api/chat/status')
def chat_status():
    return jsonify(language_model=language_status(), ai_health=connection_health(),
                   ai_error_code=connection_error_code(), public=PUBLIC_SITE)


@app.get('/api/fixtures')
def fixture_list():
    code = request.args.get('league', '')
    if code and code not in (*LEAGUES, *CUP_NAMES):
        return jsonify(error='Okänd tävling.'), 400
    result = []
    for league in ([code] if code else [*LEAGUES, *CUP_NAMES]):
        result.extend(fixture_public(item, ROOT) for item in upcoming_fixtures(ROOT, league))
    return jsonify(sorted(result, key=lambda item: item['utc_date'])[:500])


@app.get('/api/data/status')
def data_status():
    records = {}
    for code, meta in LEAGUES.items():
        folder = ROOT / meta['folder']
        csv_files = list(folder.glob('*.csv'))
        records[code] = {'name': meta['name'], 'files': len(csv_files),
                         'trained': model_path(code).exists()}
    fixtures = read_fixtures(ROOT)
    with job_lock:
        current = {'running': job_status['running'], 'message': job_status['message'],
                   'log': job_status['log'][-12:]}
    return jsonify(leagues=records, fixtures=len(fixtures), job=current)


def run_update(kind, token=None):
    def log(message):
        with job_lock:
            job_status['message'] = message
            job_status['log'].append(message)
            job_status['log'] = job_status['log'][-50:]
    try:
        if kind == 'fixtures':
            from update_fixtures import main as refresh_fixtures
            log('Hämtar spelscheman och lagarenor ...')
            refresh_fixtures(token=token, logger=log)
        else:
            from fetch_data import main as refresh_matches
            from train_model import main as retrain
            log('Hämtar färdigspelade matcher ...')
            refresh_matches()
            log('Tränar och testar modellerna. Det kan ta flera minuter ...')
            retrain()
            states.clear()
        log('Uppdateringen är färdig. Uppdatera sidan för att se nya siffror.')
    except (Exception, SystemExit) as error:
        log(f'Uppdateringen avbröts: {error}')
    finally:
        with job_lock:
            job_status['running'] = False


@app.post('/api/data/update')
def start_update():
    if PUBLIC_SITE:
        return jsonify(error='Data uppdateras av webbplatsens administratör.'), 403
    origin = request.headers.get('Origin')
    if origin and origin != request.host_url.rstrip('/'):
        return jsonify(error='Förfrågan måste komma från den här lokala sidan.'), 403
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error='Välj en giltig uppdatering.'), 400
    kind = body.get('kind')
    if kind not in ('fixtures', 'results'):
        return jsonify(error='Välj spelschema eller resultat.'), 400
    token = body.get('token', '')
    if not isinstance(token, str) or len(token) > 200:
        return jsonify(error='Ogiltig nyckel.'), 400
    if kind == 'fixtures' and not (token.strip() or os.environ.get('FOOTBALL_DATA_TOKEN')):
        return jsonify(error='Skriv in din football-data.org-nyckel för att uppdatera schemat.'), 400
    with job_lock:
        if job_status['running']:
            return jsonify(error='En uppdatering pågår redan.'), 409
        job_status.update(running=True, message='Startar ...', log=[])
    threading.Thread(target=run_update, args=(kind, token.strip() or None), daemon=True).start()
    return jsonify(started=True), 202


@app.get('/api/match/result')
def match_result():
    code = request.args.get('league')
    home, away = request.args.get('home', ''), request.args.get('away', '')
    date = request.args.get('date', '')
    if code not in LEAGUES or not home or not away or not date:
        return jsonify(error='Match, liga och datum krävs.'), 400
    try:
        scheduled = pd.to_datetime(date, utc=True)
        if pd.isna(scheduled) or scheduled > pd.Timestamp.now(tz='UTC'):
            return jsonify(status='not_played')
        matches = load_matches(ROOT / LEAGUES[code]['folder'], code)
    except (ValueError, OSError, TypeError):
        return jsonify(status='unavailable')
    first = normalize_team(home, code)
    second = normalize_team(away, code)
    actual = matches[(matches.HomeTeam == first) & (matches.AwayTeam == second) &
                     (matches.Date.dt.date == scheduled.date())]
    if actual.empty:
        return jsonify(status='unavailable')
    row = actual.iloc[0]
    return jsonify(status='finished', home_goals=int(row.FTHG), away_goals=int(row.FTAG),
                   outcome=row.FTR, source='football-data.co.uk', date=str(row.Date.date()))


def allow_public_chat(visitor):
    """En enda serverprocess delar ut en rimlig del av gratisnivån per besökare."""
    now = time.monotonic()
    with chat_lock:
        minute = chat_requests[visitor]
        while minute and now - minute[0] >= 60:
            minute.popleft()
        while total_requests and now - total_requests[0] >= 60:
            total_requests.popleft()
        while daily_requests and now - daily_requests[0] >= 86400:
            daily_requests.popleft()
        if len(minute) >= 8 or len(total_requests) >= 20 or len(daily_requests) >= 200:
            return False
        minute.append(now)
        total_requests.append(now)
        daily_requests.append(now)
        if len(chat_requests) > 1000:
            for address, seen in list(chat_requests.items()):
                if not seen or now - seen[-1] >= 60:
                    del chat_requests[address]
        return True


@app.post('/chat')
def chat():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error='Skicka en giltig fråga.'), 400
    message = body.get('message', '')
    if not isinstance(message, str) or not message.strip() or len(message) > 2000:
        return jsonify(error='Skriv en fråga på högst 2 000 tecken.'), 400
    if PUBLIC_SITE and not allow_public_chat(request.remote_addr or 'unknown'):
        return jsonify(error='Chatten har nått sin tillfälliga gräns. Prova igen senare.'), 429
    raw_context = body.get('context')
    context = ({field: raw_context[field] for field in ('league', 'home', 'away')
                if isinstance(raw_context.get(field), str) and len(raw_context[field]) <= 100}
               if isinstance(raw_context, dict) else None)
    raw_history = body.get('history')
    history = [{field: item[field][:1800] for field in ('question', 'answer')
                if isinstance(item.get(field), str)}
               for item in raw_history[-8:] if isinstance(item, dict)] if isinstance(raw_history, list) else []
    visitor = request.remote_addr or 'unknown'
    request_id = body.get('request_id')
    if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{12,80}', request_id):
        request_id = uuid.uuid4().hex
    key = (visitor, request_id)
    cancel = threading.Event()
    cancel.response = None
    with chat_lock:
        if key in active_requests:
            return jsonify(error='Samma fråga behandlas redan.'), 409
        if sum(address == visitor for address, _ in active_requests) >= 2:
            return jsonify(error='Vänta tills det pågående svaret är färdigt.'), 429
        active_requests[key] = cancel
    cancel_token = request_cancel.set(cancel)
    request_error.set(None)
    try:
        answer = answer_question(message.strip(), context, history)
        if cancel.is_set():
            return jsonify(error='Svaret stoppades.'), 499
        if answer.get('kind') == 'error':
            reason = request_error.get() or {}
            return jsonify(answer), 429 if reason.get('code') == 429 else 503
        answer['suggestions'] = suggestions(answer, history, message)
        answer['analysis_id'] = uuid.uuid4().hex[:12]
        answer['created_at'] = datetime.now(timezone.utc).isoformat()
        # Flask normally permits NaN. Refuse invalid numerical values at the boundary.
        json.dumps(answer, allow_nan=False)
        return jsonify(answer)
    except Cancelled:
        return jsonify(error='Svaret stoppades.'), 499
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        app.logger.error('Chat request %s failed: %s', request_id, type(exc).__name__)
        return jsonify(error='Matchunderlaget kunde inte läsas. Försök igen.'), 503
    finally:
        request_cancel.reset(cancel_token)
        with chat_lock:
            active_requests.pop(key, None)


@app.post('/api/chat/cancel')
def cancel_chat():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get('request_id'), str):
        return jsonify(error='Ogiltigt anrops-id.'), 400
    with chat_lock:
        event = active_requests.get((request.remote_addr or 'unknown', body['request_id']))
        if event:
            event.set()
            response = getattr(event, 'response', None)
        else:
            response = None
    if response:
        try:
            sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
            if sock:
                sock.shutdown(socket.SHUT_RDWR)
            response.close()
        except OSError:
            pass
    return jsonify(cancelled=event is not None)


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
