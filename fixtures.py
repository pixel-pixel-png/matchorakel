"""Importerade spelscheman från football-data.org (egen API-nyckel krävs)."""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from football import LEAGUES, ALIASES, clean_name, team_key

PROVIDER = 'football-data.org'
CUP_NAMES = {'UCL': 'Champions League', 'FAC': 'FA Cup', 'CDR': 'Copa del Rey',
             'EL': 'Europa League', 'UECL': 'Conference League',
             'DFB': 'DFB-Pokal', 'CIT': 'Coppa Italia'}
CUP_ALIASES = {'UCL': ('champions league', 'championsligan', 'ucl'),
               'FAC': ('fa cup', 'facup'), 'CDR': ('copa del rey', 'copa espana', 'spanska cupen'),
               'EL': ('europa league', 'europaleague', 'europaligan'),
               'UECL': ('conference league', 'europa conference league', 'conference ligan'),
               'DFB': ('dfb pokal', 'tyska cupen'),
               'CIT': ('coppa italia', 'italienska cupen')}
COMPETITIONS = {'PL': 'PL', 'LL': 'PD', 'BL': 'BL1', 'SA': 'SA', 'L1': 'FL1',
                'UCL': 'CL', 'FAC': 'FAC', 'CDR': 'CDR', 'EL': 'EL',
                'UECL': 'UCL', 'DFB': 'DFB', 'CIT': 'CIT'}
KNOWN_HOME_VENUES = {
    ('LL', 'sevilla'): {'venue': 'Estadio Ramón Sánchez-Pizjuán',
                        'source': 'Sevilla FC · https://entradas.sevillafc.es/'},
}


def read_fixtures(root: Path):
    path = root / 'data' / 'fixtures.json'
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError, UnicodeError):
        return []
    fixtures = payload.get('fixtures', []) if isinstance(payload, dict) else []
    if not isinstance(fixtures, list):
        return []
    return [item for item in fixtures if isinstance(item, dict) and
            item.get('league') in (*LEAGUES, *CUP_NAMES) and
            isinstance(item.get('home'), str) and item['home'].strip() and
            isinstance(item.get('away'), str) and item['away'].strip() and
            isinstance(item.get('utc_date'), str) and fixture_time(item) is not None and
            isinstance(item.get('status'), str) and
            normalize_team(item['home'], item['league']) != normalize_team(item['away'], item['league'])]


def read_venues(root: Path):
    path = root / 'data' / 'fixtures.json'
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data.get('team_venues', {}) if isinstance(data, dict) and isinstance(data.get('team_venues'), dict) else {}
    except (ValueError, OSError, AttributeError):
        return {}


def normalize_team(name, league):
    if league in CUP_NAMES:
        raw = clean_name(name)
        for code in LEAGUES:
            if raw in ALIASES[code]:
                return ALIASES[code][raw]
        return raw[:-3] if raw.endswith(' fc') else raw
    return team_key(name, league)


def fixture_time(fixture):
    try:
        parsed = datetime.fromisoformat(fixture['utc_date'].replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else None
    except (ValueError, KeyError, AttributeError, TypeError):
        return None


def upcoming_fixtures(root, league, home=None, away=None, team=None):
    """Matcha exakta teamnamn och kommande matcher; hitta aldrig på en arena."""
    now = datetime.now(timezone.utc)
    home = normalize_team(home, league) if home else None
    away = normalize_team(away, league) if away else None
    team = normalize_team(team, league) if team else None
    results = []
    for match in read_fixtures(root):
        if match.get('league') != league or match.get('status') not in ('SCHEDULED', 'TIMED'):
            continue
        date = fixture_time(match)
        if not date or (date < now and (match.get('status') != 'SCHEDULED' or date.date() < now.date())):
            continue
        first = normalize_team(match.get('home') or '', league)
        second = normalize_team(match.get('away') or '', league)
        if home and away and (first != home or second != away):
            continue
        if team and team not in (first, second):
            continue
        results.append(match)
    return sorted(results, key=fixture_time)


def home_venue(root, league, home):
    key = normalize_team(home, league)
    venues = read_venues(root)
    league_venues = venues.get(league)
    estimated = league_venues.get(key, {}) if isinstance(league_venues, dict) else {}
    if not estimated and league in CUP_NAMES:
        estimated = next((items[key] for code in LEAGUES
                          if isinstance((items := venues.get(code)), dict) and items.get(key)), {})
    if not estimated:
        estimated = KNOWN_HOME_VENUES.get((league, key), {})
    if not estimated and league in CUP_NAMES:
        estimated = next((KNOWN_HOME_VENUES.get((code, key)) for code in LEAGUES
                          if KNOWN_HOME_VENUES.get((code, key))), {})
    return estimated if isinstance(estimated, dict) else {}


def fixture_public(match, root=None):
    result = {key: match.get(key) for key in
              ('league', 'home', 'away', 'utc_date', 'venue', 'status', 'synced_at', 'source', 'match_id', 'score')}
    result['kickoff_confirmed'] = match.get('status') in ('TIMED', 'IN_PLAY', 'PAUSED', 'FINISHED')
    if not isinstance(result['venue'], str) or not result['venue'].strip():
        result['venue'] = None
    result['venue_confidence'] = 'confirmed' if result['venue'] else 'unknown'
    result['venue_source'] = result['source'] if result['venue'] else None
    if not result['venue'] and root:
        estimated = home_venue(root, match.get('league'), match.get('home') or '')
        if isinstance(estimated, dict) and estimated.get('venue'):
            result['venue'] = estimated['venue']
            result['venue_confidence'] = 'likely_home'
            result['venue_source'] = estimated.get('source')
            result['venue_updated_at'] = estimated.get('synced_at')
    return result


def display_fixture_date(match, language='sv'):
    stamp = fixture_time(match)
    if not stamp:
        return 'Date unavailable.' if language == 'en' else 'Datum saknas.'
    # SCHEDULED has a date placeholder, not a confirmed local kickoff time.
    timed = match.get('kickoff_confirmed', match.get('status') in ('TIMED','IN_PLAY','PAUSED','FINISHED'))
    date = stamp.astimezone(ZoneInfo('Europe/Stockholm')) if timed else stamp
    months = ('januari februari mars april maj juni juli augusti september oktober november december'.split() if language == 'sv' else
              'January February March April May June July August September October November December'.split())
    result = f'{date.day} {months[date.month-1]} {date.year}'
    if timed:
        result += date.strftime(' %H:%M') + (' svensk tid' if language=='sv' else ' Stockholm time')
    else:
        result += ' · avspark inte fastställd' if language=='sv' else ' · kickoff time unconfirmed'
    return result
