"""Hämta årets publicerade matcher från football-data.org med egen API-nyckel."""
import argparse
import getpass
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fixtures import COMPETITIONS, PROVIDER, fixture_time, normalize_team, read_fixtures, read_venues

ROOT = Path(__file__).resolve().parent


def fetch_competition(code, token):
    # Utan season-filter väljer API:et själv tävlingens aktiva säsong.
    url = f'https://api.football-data.org/v4/competitions/{COMPETITIONS[code]}/matches'
    request = Request(url, headers={'X-Auth-Token': token, 'User-Agent': 'Matchorakel/5.0'})
    with urlopen(request, timeout=25) as response:
        payload = json.load(response)
    if not isinstance(payload.get('matches'), list):
        raise ValueError('API:et skickade ingen matchlista.')
    stamp = datetime.now(timezone.utc).isoformat()
    return [{
        'league': code, 'home': (item.get('homeTeam') or {}).get('name'),
        'away': (item.get('awayTeam') or {}).get('name'),
        'utc_date': item.get('utcDate'), 'venue': item.get('venue'),
        'status': item.get('status'), 'synced_at': stamp, 'source': PROVIDER,
        'match_id': item.get('id'), 'stage': item.get('stage'),
        'score': (item.get('score') or {}).get('fullTime'),
    } for item in payload['matches'] if item.get('utcDate') and
        (item.get('homeTeam') or {}).get('name') and (item.get('awayTeam') or {}).get('name')]


def fetch_team_venues(code, token):
    url = f'https://api.football-data.org/v4/competitions/{COMPETITIONS[code]}/teams'
    request = Request(url, headers={'X-Auth-Token': token, 'User-Agent': 'Matchorakel/7.0'})
    with urlopen(request, timeout=25) as response:
        payload = json.load(response)
    if not isinstance(payload.get('teams'), list):
        raise ValueError('API:et skickade ingen laglista.')
    stamp = datetime.now(timezone.utc).isoformat()
    return {normalize_team(team['name'], code): {
        'venue': team['venue'], 'source': PROVIDER + ' · lagprofil', 'synced_at': stamp,
    } for team in payload['teams'] if team.get('name') and team.get('venue')}


def api_error(error, token):
    """Visa API:ets förklaring utan att skriva ut den privata nyckeln."""
    try:
        payload = json.loads(error.read().decode('utf-8', errors='replace'))
        detail = (payload.get('message') or payload.get('error')) if isinstance(payload, dict) else None
    except (ValueError, UnicodeError, OSError):
        detail = None
    if not isinstance(detail, str):
        detail = ''
    detail = ' '.join(detail.replace(token, '[nyckel dold]').split())[:240]
    return f'HTTP {error.code}' + (f': {detail}' if detail else '')


def save_fixtures(matches, venues=None):
    destination = ROOT / 'data' / 'fixtures.json'
    destination.parent.mkdir(exist_ok=True)
    temp = destination.with_suffix('.tmp')
    temp.write_text(json.dumps({'source': PROVIDER, 'fixtures': matches,
                                'team_venues': venues if venues is not None else read_venues(ROOT)}, ensure_ascii=False), encoding='utf-8')
    temp.replace(destination)


def main(league=None, token=None, logger=print):
    token = (token or os.environ.get('FOOTBALL_DATA_TOKEN', '')).strip()
    if not token:
        token = getpass.getpass('Klistra in din football-data.org API-nyckel (visas inte): ').strip()
    if not token:
        raise SystemExit('Ingen nyckel angavs. Tidigare sparade spelscheman ändras inte.')
    matches = read_fixtures(ROOT)
    venues = read_venues(ROOT)
    success = 0
    selected = [league] if league else COMPETITIONS
    for index, code in enumerate(selected):
        if index:
            logger('Väntar 7 sekunder före nästa liga (API:ets anropsgräns)...')
            sleep(7)  # gratisnivån tillåter 10 anrop/minut
        try:
            latest = fetch_competition(code, token)
        except HTTPError as error:
            logger(f'{code}: kunde inte hämta schemat ({api_error(error, token)}). Befintligt schema behålls.')
            continue
        except (URLError, TimeoutError, ValueError) as error:
            logger(f'{code}: kunde inte hämta schemat ({error}). Befintligt schema behålls.')
            continue
        if not latest:
            logger(f'{code}: API:et gav inga matcher med datum och lag. Befintligt schema behålls.')
            continue
        unique = {item.get('match_id') or (item['home'], item['away'], item['utc_date']): item for item in latest}
        matches = [item for item in matches if item.get('league') != code] + list(unique.values())
        save_fixtures(matches, venues)
        success += 1
        sleep(7)
        try:
            venues[code] = fetch_team_venues(code, token)
            save_fixtures(matches, venues)
            logger(f'{code}: {len(venues[code])} möjliga hemmaarenor från lagprofiler (inte bekräftade matcharenor).')
        except HTTPError as error:
            logger(f'{code}: inga lagarenor hämtades ({api_error(error, token)}). Matchschemat har sparats.')
        except (URLError, TimeoutError, ValueError) as error:
            logger(f'{code}: inga lagarenor hämtades ({error}). Matchschemat har sparats.')
        now = datetime.now(timezone.utc)
        upcoming = sum(item['status'] in ('SCHEDULED', 'TIMED') and
                       (fixture_time(item) or now) > now for item in latest)
        logger(f'{code}: {len(latest)} publicerade matcher hämtade, varav {upcoming} kommande.')
    if success:
        logger('Klart. Uppdatera webbsidan för att se det nya spelschemat.')
    else:
        logger('Inget schema uppdaterades. Läs felmeddelandet ovan för orsaken.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hämta aktuella spelscheman från football-data.org')
    parser.add_argument('--league', choices=COMPETITIONS, help='Hämta endast denna liga (UCL för Champions League)')
    main(parser.parse_args().league)
