"""Hämta fem ligors säsongsfiler utan API-nyckel."""
import argparse
import csv
from datetime import date
import io
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from football import LEAGUES, REQUIRED

ROOT = Path(__file__).resolve().parent
START_YEAR = 2022


def seasons():
    now = date.today()
    current_start = now.year if now.month >= 7 else now.year - 1
    return [f'{year % 100:02d}{(year + 1) % 100:02d}' for year in range(START_YEAR, current_start + 1)]


def download(league, season, refresh=False):
    meta = LEAGUES[league]
    folder = ROOT / meta['folder']
    folder.mkdir(parents=True, exist_ok=True)
    filename = f'{meta["slug"]}-{season}.csv'
    path = folder / filename
    if path.exists() and not refresh:
        return f'Finns redan: {meta["name"]} {season}'
    url = f'https://www.football-data.co.uk/mmz4281/{season}/{meta["code"]}.csv'
    with urlopen(Request(url, headers={'User-Agent': 'Matchorakel-study-project/2.0'}), timeout=25) as response:
        raw = response.read()
    reader = csv.DictReader(io.StringIO(raw.decode('latin-1')))
    if not REQUIRED.issubset(reader.fieldnames or []):
        raise ValueError('Servern skickade ingen giltig matchfil.')
    if 'Div' in reader.fieldnames:
        first = next(reader, None)
        if first and first['Div'] != meta['code']:
            raise ValueError('Servern skickade fel liga.')
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)
    return f'Hämtade: {meta["name"]} {season}'


def main(no_refresh_current=False):
    years = seasons()
    for league in LEAGUES:
        success = 0
        for season in years:
            try:
                print(download(league, season, not no_refresh_current and season == years[-1]))
                success += 1
            except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
                print(f'Kunde inte hämta {LEAGUES[league]["name"]} {season}: {exc}')
        if success < 3:
            print(f'För få säsonger för {LEAGUES[league]["name"]}; se README för manuell nedladdning.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Hämta ligamatcher från football-data.co.uk.')
    parser.add_argument('--no-refresh-current', action='store_true', help='Behåll sparad fil för pågående säsong.')
    main(parser.parse_args().no_refresh_current)
