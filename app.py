"""Lokal webbserver med en gemensam chatt för fem ligor."""
import json
import math
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from conversation import friendly_reply, football_followup, parts_of_question, suggestions
from football import ALIASES, FEATURES, LEAGUES, clean_name, feature_row, find_teams, load_matches, parse_teams, recent_form, team_display
from fixtures import fixture_public, home_venue, normalize_team, read_fixtures, upcoming_fixtures
from language_chat import general_answer, language_status
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
    goal_markets = {}
    if saved.get('goal_model') and saved.get('goal_market_enabled'):
        raw = saved['goal_model'].goal_markets(pd.DataFrame([features], columns=saved['goal_features']))[0]
        goal_markets = {market: round(raw[market] * 100, 1)
                        for market, enabled in saved['goal_market_enabled'].items() if enabled}
    return {
        'home': team_display(home, league), 'away': team_display(away, league),
        'league': league, 'league_name': LEAGUES[league]['name'],
        'probabilities': {label: round(float(values[label]) * 100, 1) for label in ('H', 'D', 'A')},
        'goal_markets': goal_markets,
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
            'league': league, 'league_name': 'Champions League' if league == 'UCL' else LEAGUES[league]['name'],
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
    label = 'Champions League' if league == 'UCL' else LEAGUES[league]['name']
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


def ucl_evidence(matches, question):
    """Historiska observationer från ligorna; inga UCL-odds eller säkra utfall."""
    fixture = matches[0]
    participants = []
    for name in (fixture['home'], fixture['away']):
        key = normalize_team(name, 'UCL')
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
    player_query = any(term in normalized for term in ('raphinha', 'mbappe', 'lewandowski', 'haaland', 'assist', 'malskytt'))
    if time_query:
        return fixture_answer(matches, 'UCL', fixture['home'], fixture['away'],
                              title='Tid och plats för matchen', summary='Matchdatum kommer från spelschemat. Lagets vanliga arena kan visas som trolig när matchens arena inte är bekräftad.')
    if player_query:
        return fixture_answer(matches, 'UCL', fixture['home'], fixture['away'],
                              title='Spelarfrågan', summary='Jag har inte verifierade spelarsiffror eller startelvor för den här Champions League-matchen. Därför kan jag inte uppskatta spelarens skott, mål, assist eller kort. Matchens publicerade tid visas nedan.')
    if any(term in normalized for term in ('skada', 'skadad', 'avstangd', 'startelva')):
        return fixture_answer(matches, 'UCL', fixture['home'], fixture['away'],
                              title='Spelarfrånvaro', summary='Jag har ingen verifierad aktuell skade- eller startelvsinformation för matchen och kan inte räkna in den. Kontrollera lagens bekräftade uppgifter nära avspark.')
    if len(participants) < 2:
        return fixture_answer(matches, 'UCL', fixture['home'], fixture['away'],
                              title='Underlag saknas för matchanalys', summary='Jag har schemat, men saknar tränad historik för båda lagen. Kör py fetch_data.py och py train_model.py för lagstatistik. Jag kan inte avgöra vad som är säkrast i den här matchen.')
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
            if goals or broad:
                observations.append((f'{name} gör minst 1 mål', [event['goals_scored'] >= 1 for event in events]))
            if shots or broad:
                recorded = [event['shots'] for event in events if event.get('shots') is not None]
                observations.extend([(f'{name}: minst {minimum} skott på mål', [value >= minimum for value in recorded])
                                     for minimum in (1, 2)])
            if yellows or broad:
                recorded = [event['cards'] for event in events if event.get('cards') is not None]
                observations.extend([(f'{name}: minst {minimum} gula kort', [value >= minimum for value in recorded])
                                     for minimum in (1, 2)])
        if goals or broad:
            totals = [event['total_goals'] for _, _, state, key in participants
                      for event in (state.get('event_history') or {}).get(key, [])]
            observations.extend([(f'Minst {minimum} mål i matchen', [value >= minimum for value in totals])
                                 for minimum in (1, 2, 3)])
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
        return fixture_answer(matches, 'UCL', fixture['home'], fixture['away'],
                              title='Historiska händelser saknas', summary='Matchen är publicerad, men det finns för få registrerade händelser för att besvara frågan. Jag kan inte kalla något säkert.')
    missing = [name for name, _, state, key in participants
               if not form_query and len((state.get('event_history') or {}).get(key, [])) < 12]
    summary = ('Detta är tidigare utfall i lagens respektive ligor, inte sannolikheter för Champions League-matchen. '
               'Motstånd, skador och startelvor ingår inte. Inget utfall är säkert.')
    if missing:
        summary += ' Tillräcklig händelsestatistik saknas för ' + ', '.join(missing) + '.'
    result = insight(title, summary,
                     'UCL', cards, home=fixture['home'], away=fixture['away'],
                     as_of=max(state.get('last_match', '') for _, _, state, _ in participants))
    result['fixture'] = fixture_public(fixture, ROOT)
    result['source_note'] = 'Historik från respektive inhemsk liga; ingen modell för Champions League har tränats.'
    return result


def champions_answer(message, context=None):
    normalized = clean_name(message)
    explicit = any(term in normalized for term in ('champions league', 'ucl', 'championsligan'))
    previous = isinstance(context, dict) and context.get('league') == 'UCL'
    listing = any(term in normalized for term in ('kommande', 'spelschema', 'vilka matcher', 'nasta matcher'))
    if previous and not explicit and not football_followup(message):
        return None
    result_query = any(term in normalized for term in ('resultat', 'slutade', 'vad blev', 'vem vann', 'hur gick'))
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
        return text_response('Jag har inget verifierat Champions League-schema ännu. Kör py update_fixtures.py med en egen football-data.org-nyckel för aktuella datum och arenor.')
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


def safest_history(saved, league, home, away):
    histories = saved.get('event_history') or {}
    if not home or not away or home not in histories or away not in histories:
        return text_response('Jag behöver en ny tränad modell och två lag i samma liga. Kör py train_model.py och skriv till exempel ”Barcelona mot Real Madrid”.', league, home, away)
    games = {home: list(histories[home]), away: list(histories[away])}
    if min(map(len, games.values())) < 12:
        return text_response('Det finns för få tidigare matcher för att rangordna återkommande händelser utan att ge falsk precision.', league, home, away)
    candidates = []

    def add(label, observed):
        count, total = sum(observed), len(observed)
        if total < 12:
            return
        p = count / total
        z = 1.96
        lower = (p + z*z/(2*total) - z*math.sqrt(p*(1-p)/total + z*z/(4*total*total))) / (1 + z*z/total)
        candidates.append((lower, {'label': label, 'value': f'{count} / {total}',
                                   'detail': f'{p:.0%} av de tidigare matcherna'}))

    combined = games[home] + games[away]
    add('Minst 1 mål totalt', [item['total_goals'] >= 1 for item in combined])
    add('Minst 2 mål totalt', [item['total_goals'] >= 2 for item in combined])
    add('Minst 3 mål totalt', [item['total_goals'] >= 3 for item in combined])
    for key in (home, away):
        label = team_display(key, league)
        add(f'{label} gör mål', [item['goals_scored'] >= 1 for item in games[key]])
        for field, text in (('cards', 'gula kort'), ('shots', 'skott på mål')):
            recorded = [item[field] for item in games[key] if item[field] is not None]
            add(f'{label}: minst 1 {text}', [value >= 1 for value in recorded])
            add(f'{label}: minst 2 {text}', [value >= 2 for value in recorded])
    top = [card for _, card in sorted(candidates, key=lambda item: item[0], reverse=True)[:4]]
    return insight('Vanligast i tidigare matcher',
                   'Rangordnat efter hur ofta händelser inträffat i lagens senaste upp till 20 ligamatcher. Detta är inte sannolikheter för den här matchen; motstånd, startelvor och skador ingår inte i beräkningen.',
                   league, top, home=home, away=away, as_of=saved['last_match'])


def answer_single(message, context=None, history=None):
    social = friendly_reply(message, history)
    if social:
        natural = general_answer(message, {'fotboll': 'Ingen ny match efter ämnesbytet.'}, history)
        result = text_response(natural or social)
        result['topic_reset'] = True
        if natural:
            result['source'] = 'Språkmodell · samtal'
        return result
    plain = clean_name(message)
    if 'menade' in plain and 'inte' in plain and isinstance(context, dict) and context.get('league') in LEAGUES:
        code = context['league']
        teams = get_state(code)['teams']
        before, after = re.split(r'\binte\b', plain, maxsplit=1)
        new = find_teams(before, teams, code)
        old = find_teams(after, teams, code)
        pair = [context.get('home'), context.get('away')]
        if len(new) == 1 and len(old) == 1 and old[0] in pair and new[0] not in pair:
            pair[pair.index(old[0])] = new[0]
            return answer_single(f'{pair[0]} mot {pair[1]}', None, history)
        return text_response('Vilket av lagen vill du byta ut? Skriv till exempel ”Jag menade Real Madrid, inte Atlético Madrid”.', code, *pair)
    if plain in ('hej', 'tjena', 'tja', 'halloj'):
        return text_response('Hej! Fråga om en match, lagens form, mål, skott, gula kort eller när matchen spelas. Jag kan också besvara följdfrågor om matchen vi nyss pratade om.',
                             context.get('league') if isinstance(context, dict) else None,
                             context.get('home') if isinstance(context, dict) else None,
                             context.get('away') if isinstance(context, dict) else None)
    if plain in ('tack', 'tack sa mycket', 'okej tack'):
        return text_response('Varsågod! Skriv en följdfråga om matchen när du vill.',
                             context.get('league') if isinstance(context, dict) else None,
                             context.get('home') if isinstance(context, dict) else None,
                             context.get('away') if isinstance(context, dict) else None)
    if any(term in plain for term in ('vad kan du gora', 'vad kan jag fraga', 'hjalp mig', 'hur fungerar chatten')):
        return text_response('Du kan fråga om slutresultat i fem ligor, lagens form, tidigare mål, skott och kort samt publicerade matchdatum i Champions League. Jag svarar på följdfrågor om samma match. Frågor om spelares enskilda statistik kräver en särskild spelarfil; inga matchutfall är säkra.',
                             context.get('league') if isinstance(context, dict) else None,
                             context.get('home') if isinstance(context, dict) else None,
                             context.get('away') if isinstance(context, dict) else None)
    mentioned_teams = [find_teams(message, get_state(code)['teams'], code)
                       for code in LEAGUES if model_path(code).exists()]
    new_domestic_pair = any(len(found) == 2 for found in mentioned_teams)
    explicit_ucl = any(word in plain for word in ('champions league', 'ucl', 'championsligan'))
    explicit_domestic = any(term in plain for term in ('premier league', 'la liga', 'bundesliga', 'serie a', 'ligue 1'))
    changing_league = explicit_domestic and ('nu' in plain or 'menade' in plain or 'istallet' in plain)
    if not any(mentioned_teams) and not explicit_ucl and not football_followup(message):
        natural = general_answer(message, {'fotboll': 'Ingen fotbollsfråga ställdes.'}, history)
        result = text_response(natural or
            'Jag kan inte besvara just den frågan nu. Prova igen om en stund; '
            'om problemet kvarstår behöver den som driver sidan kontrollera AI-anslutningen.')
        result['topic_reset'] = True
        if natural:
            result['source'] = 'Språkmodell · samtal'
        return result
    switch_from_ucl = new_domestic_pair and explicit_ucl and any(term in plain for term in
                       ('inte champions', 'inte ucl', 'slapp cl', 'glom psg', 'men nu',
                        'nu galler', 'ar klart', 'nasta fraga', 'varfor blandar du in'))
    champion = None if (new_domestic_pair and not explicit_ucl) or changing_league or switch_from_ucl else champions_answer(message, context)
    if champion:
        return champion
    league, issue = detect_league(message, context)
    if issue:
        if 'olika ligor' in issue and upcoming_fixtures(ROOT, 'UCL'):
            possible = champions_answer('Champions League ' + message)
            if possible and possible.get('kind') == 'fixtures':
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
        open_answer = general_answer(message, {'matchdata': 'Ingen specifik match har identifierats.'}, history)
        if open_answer:
            result = text_response(open_answer)
            result['source'] = 'Språkmodell · ingen liveinformation'
            return result
        return text_response('Skriv till exempel ”Barcelona mot Real Madrid”, ”Bayern mot Dortmund” eller ”Hur är Arsenals form?”. Jag hittar ligan själv. Fråga sedan ”Varför?” eller ”Hur många gula kort?”.')
    saved = get_state(league)
    normalized = clean_name(message)
    teams = saved['teams']
    found = find_teams(message, teams, league)
    home = away = None
    if len(found) == 2:
        home, away = found
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
    if home and away and any(term in normalized for term in ('lapp', 'speltips', 'vad ska jag spela')):
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
        return text_response('Jag hittar inget verifierat kommande datum för den frågan. Kör py update_fixtures.py med en egen football-data.org-nyckel för att hämta spelschema och arenor. Jag hittar inte på dessa uppgifter.', league, home, away)
    if any(term in normalized for term in ('skadad', 'skadade', 'skada', 'skador', 'avstangd', 'saknas i startelvan', 'vansterback')):
        return text_response('En skadad ytterback kan påverka matchbilden, men jag kan inte verifiera aktuell frånvaro eller översätta den till en procentsats för en spelares mål eller skott. Modellen tar ännu inte in skador, startelvor eller förväntade minuter. Kontrollera bekräftade uppgifter nära avspark.', league, home, away)
    shot_query = any(word in normalized for word in ('skott pa mal', 'shots on target', 'avslut pa mal'))
    card_query = any(word in normalized for word in ('gula kort', 'gult kort', 'yellow card', 'varningar'))
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

    goal_market = ('both_score' if any(term in normalized for term in ('bada lagen gor mal', 'btts')) else
                   'over_2_5' if any(term in normalized for term in ('over 2 5', 'mer an 2 5', 'minst 3 mal', 'tre mal')) else
                   'over_1_5' if any(term in normalized for term in ('over 1 5', 'minst 2 mal')) else None)
    if goal_market and home and away and saved.get('goal_market_enabled', {}).get(goal_market):
        forecast = predict_match(home, away, league)
        probability = forecast['goal_markets'][goal_market]
        label = {'both_score': 'Båda lagen gör mål', 'over_2_5': 'Minst 3 mål',
                 'over_1_5': 'Minst 2 mål'}[goal_market]
        odds_match = re.search(r'\bodds\s*(\d+[,.]\d{1,3})\b', message.lower())
        odds_note = ''
        if odds_match:
            odds = float(odds_match.group(1).replace(',', '.'))
            if 1.01 <= odds <= 100:
                threshold = 100 / odds
                odds_note = (f' Du angav odds {odds:.2f}; nollpunkten före insats- och marknadsrisk är {threshold:.1f} %. '
                             f'Modellens uppskattning ligger {probability - threshold:+.1f} procentenheter från den nivån. '
                             'Detta är ingen bekräftad aktuell Unibet-kurs eller garanti för spelvärde.')
        response = insight(label, 'Uppskattning från en separat målmodell som slog säsongens baslinje på valideringsperioden. Osäkerheten är betydande och detta är ingen garanti.',
                           league, [{'label': label, 'value': f'{probability:.1f} %',
                                     'detail': 'Målmodell · testa mot aktuella odds innan spel'}],
                           home=home, away=away, as_of=saved['last_match'])
        response['summary'] += odds_note
        response['fixture'] = forecast.get('fixture')
        return response

    if shot_query or card_query:
        metric = 'shots_on_target' if shot_query else 'yellow_cards'
        label = 'Skott på mål' if shot_query else 'Gula kort'
        if not snapshots:
            return text_response(f'Vilket lag menar du? Skriv till exempel ”Hur många {label.lower()} har Bayern haft?”.', league, home, away)
        cards = []
        for team in snapshots:
            observation = team[metric]
            cards.append({'label': team['name'],
                          'value': str(observation['total']) if observation else '–',
                          'detail': f'{label} i {observation["matches"]} av de senaste {team["count"]} matcherna' if observation else f'{label} saknas i de senaste matchfilerna'})
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
    predict_query = any(term in normalized for term in ('vem vinner', 'prognos', 'sannolikhet', 'vinstchans', 'hur gar matchen'))
    defense_query = 'forsvar' in normalized or 'inslappta' in normalized
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
    if home and away and (len(found) == 2 or predict_query):
        prediction = predict_match(home, away, league)
        prediction['kind'] = 'prediction'
        prediction['context'] = context_for(league, home, away)
        return prediction
    matches = upcoming_fixtures(ROOT, league, home, away) if home and away else []
    open_answer = general_answer(message, {
        'liga': LEAGUES[league]['name'], 'senaste_resultat_i_modellen': saved['last_match'],
        'lagens_senaste_fem': snapshots,
        'bekraftad_kommande_match': fixture_public(matches[0], ROOT) if matches else None,
        'spelarstatistik': 'Inte tillgänglig utan verifierad spelarfil.'}, history)
    if open_answer:
        result = text_response(open_answer, league, home, away)
        result['source'] = 'Språkmodell · använder bara tillgängligt underlag'
        return result
    return text_response('Jag kan visa matchprognoser, lagform, mål, hållna nollor, lagens skott och kort, samt modellens testresultat. Skriv ett lag eller två lag i någon av de fem ligorna. För individuella spelare krävs en separat verifierad spelarfil.', league, home, away)


def answer_question(message, context=None, history=None):
    pieces = parts_of_question(message)
    if len(pieces) == 1:
        return answer_single(message, context, history)
    answers = []
    active = context
    # Om lagnamnen står i sista delfrågan gäller de hela den aktuella frågan.
    identified = [(code, found) for code in LEAGUES if model_path(code).exists()
                  if len(found := find_teams(message, get_state(code)['teams'], code)) == 2]
    if len(identified) == 1 and not any(word in clean_name(message) for word in ('champions league', 'ucl')):
        code, (home, away) = identified[0]
        active = context_for(code, home, away)
    for part in pieces:
        answer = answer_single(part, active, history)
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


@app.get('/evaluation')
def evaluation():
    reports = []
    for code in LEAGUES:
        path = ROOT / 'artifacts' / f'evaluation_{code}.json'
        if path.exists():
            reports.append(json.loads(path.read_text(encoding='utf-8')))
    return render_template('evaluation.html', reports=reports)


@app.get('/api/leagues')
def leagues():
    return jsonify([{'code': code, 'name': meta['name'], 'ready': model_path(code).exists()}
                    for code, meta in LEAGUES.items()])


@app.get('/api/chat/status')
def chat_status():
    return jsonify(language_model=language_status(), public=PUBLIC_SITE)


@app.get('/api/fixtures')
def fixture_list():
    code = request.args.get('league', '')
    if code and code not in (*LEAGUES, 'UCL'):
        return jsonify(error='Okänd tävling.'), 400
    result = []
    for league in ([code] if code else [*LEAGUES, 'UCL']):
        result.extend(fixture_public(item, ROOT) for item in upcoming_fixtures(ROOT, league))
    return jsonify(sorted(result, key=lambda item: item['utc_date'])[:80])


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
    if not isinstance(message, str) or not message.strip() or len(message) > 500:
        return jsonify(error='Skriv en fråga på högst 500 tecken.'), 400
    if PUBLIC_SITE and not allow_public_chat(request.remote_addr or 'unknown'):
        return jsonify(error='Chatten har nått sin tillfälliga gräns. Prova igen senare.'), 429
    context = body.get('context')
    history = body.get('history')
    if not isinstance(history, list):
        history = []
    try:
        answer = answer_question(message, context, history[-20:])
        answer['suggestions'] = suggestions(answer, history[-20:], message)
        answer['analysis_id'] = uuid.uuid4().hex[:12]
        answer['created_at'] = datetime.now(timezone.utc).isoformat()
        return jsonify(answer)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
