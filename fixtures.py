"""Importerade spelscheman från football-data.org (egen API-nyckel krävs)."""
import json
from datetime import datetime, timezone
from pathlib import Path

from football import LEAGUES, ALIASES, clean_name, team_key

PROVIDER = 'football-data.org'
COMPETITIONS = {'PL': 'PL', 'LL': 'PD', 'BL': 'BL1', 'SA': 'SA', 'L1': 'FL1', 'UCL': 'CL'}
KNOWN_HOME_VENUES = {
    ('LL', 'sevilla'): {'venue': 'Estadio Ramón Sánchez-Pizjuán',
                        'source': 'Sevilla FC · https://entradas.sevillafc.es/'},
}


def read_fixtures(root: Path):
    path = root / 'data' / 'fixtures.json'
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding='utf-8'))
    return payload.get('fixtures', []) if isinstance(payload, dict) else []


def read_venues(root: Path):
    path = root / 'data' / 'fixtures.json'
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data.get('team_venues', {}) if isinstance(data.get('team_venues'), dict) else {}
    except (ValueError, OSError, AttributeError):
        return {}


def normalize_team(name, league):
    if league == 'UCL':
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
    except (ValueError, KeyError, AttributeError):
        return None


def upcoming_fixtures(root, league, home=None, away=None, team=None):
    """Matcha exakta teamnamn och kommande matcher; hitta aldrig på en arena."""
    now = datetime.now(timezone.utc)
    results = []
    for match in read_fixtures(root):
        if match.get('league') != league or match.get('status') not in ('SCHEDULED', 'TIMED'):
            continue
        date = fixture_time(match)
        if not date or date < now:
            continue
        first = normalize_team(match.get('home') or '', league)
        second = normalize_team(match.get('away') or '', league)
        if home and away and (first != home or second != away):
            continue
        if team and team not in (first, second):
            continue
        results.append(match)
    return sorted(results, key=lambda match: match['utc_date'])


def home_venue(root, league, home):
    key = normalize_team(home, league)
    venues = read_venues(root)
    estimated = venues.get(league, {}).get(key, {})
    if not estimated and league == 'UCL':
        estimated = next((venues.get(code, {}).get(key) for code in LEAGUES
                          if venues.get(code, {}).get(key)), {})
    if not estimated:
        estimated = KNOWN_HOME_VENUES.get((league, key), {})
    if not estimated and league == 'UCL':
        estimated = next((KNOWN_HOME_VENUES.get((code, key)) for code in LEAGUES
                          if KNOWN_HOME_VENUES.get((code, key))), {})
    return estimated if isinstance(estimated, dict) else {}


def fixture_public(match, root=None):
    result = {key: match.get(key) for key in
              ('league', 'home', 'away', 'utc_date', 'venue', 'status', 'synced_at', 'source', 'match_id', 'score')}
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
