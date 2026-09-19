"""Ligadata och matchstatistik som var känd innan varje avspark."""
from collections import defaultdict, deque
from pathlib import Path
import re
import unicodedata

import pandas as pd

WINDOW = 5
VENUE_WINDOW = 3
LEAGUES = {
    'PL': {'name': 'Premier League', 'code': 'E0', 'folder': 'data', 'slug': 'premier-league'},
    'LL': {'name': 'La Liga', 'code': 'SP1', 'folder': 'data/la-liga', 'slug': 'la-liga'},
    'BL': {'name': 'Bundesliga', 'code': 'D1', 'folder': 'data/bundesliga', 'slug': 'bundesliga'},
    'SA': {'name': 'Serie A', 'code': 'I1', 'folder': 'data/serie-a', 'slug': 'serie-a'},
    'L1': {'name': 'Ligue 1', 'code': 'F1', 'folder': 'data/ligue-1', 'slug': 'ligue-1'},
}
FEATURES = [
    'home_points', 'away_points', 'home_scored', 'away_scored',
    'home_conceded', 'away_conceded',
]
VENUE_FEATURES = [
    'home_venue_matches', 'away_venue_matches',
    'home_venue_points', 'away_venue_points',
    'home_venue_scored', 'away_venue_scored',
    'home_venue_conceded', 'away_venue_conceded',
]
EXTENDED_FEATURES = FEATURES + VENUE_FEATURES
CONTEXT_FEATURES = ['home_elo', 'away_elo', 'home_rest_days', 'away_rest_days']
RICH_FEATURES = EXTENDED_FEATURES + CONTEXT_FEATURES
REQUIRED = {'Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'FTR'}
ODDS = ('AvgH', 'AvgD', 'AvgA')
TEAM_STATS = ('HST', 'AST', 'HY', 'AY')


def clean_name(name):
    name = unicodedata.normalize('NFKD', str(name)).casefold()
    name = ''.join(c for c in name if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', name).strip()


ALIASES = {
    'PL': {
        'man utd': 'man united', 'manchester united': 'man united',
        'manchester city': 'man city', 'spurs': 'tottenham',
        'tottenham hotspur': 'tottenham', 'wolverhampton wanderers': 'wolves',
        'newcastle united': 'newcastle', 'brighton hove albion': 'brighton',
        'west ham united': 'west ham', 'nottingham forest': 'nott m forest',
        'nott forest': 'nott m forest', 'nottm forest': 'nott m forest',
        'leicester city': 'leicester', 'ipswich town': 'ipswich',
        'norwich city': 'norwich', 'cardiff city': 'cardiff',
    },
    'LL': {
        'fc barcelona': 'barcelona', 'barca': 'barcelona', 'barca fc': 'barcelona',
        'barceona': 'barcelona', 'madrid': 'real madrid',
        'real madrid cf': 'real madrid', 'atletico': 'atletico madrid',
        'atletico madrid': 'atletico madrid',
        'atletico de madrid': 'atletico madrid', 'ath madrid': 'atletico madrid',
        'ath bilbao': 'athletic bilbao', 'athletic club': 'athletic bilbao',
        'athletic club bilbao': 'athletic bilbao',
        'betis': 'real betis', 'real betis balompie': 'real betis',
        'sociedad': 'real sociedad', 'real sociedad de futbol': 'real sociedad',
        'vallecano': 'rayo vallecano', 'rayo vallecano de madrid': 'rayo vallecano',
        'celta': 'celta vigo', 'rc celta': 'celta vigo',
        'espanol': 'espanyol', 'rcd espanyol': 'espanyol',
        'alaves': 'alaves', 'deportivo alaves': 'alaves',
        'villarreal cf': 'villarreal', 'valencia cf': 'valencia',
        'sevilla fc': 'sevilla', 'sevila': 'sevilla', 'girona fc': 'girona',
        'osasuna': 'osasuna', 'ca osasuna': 'osasuna',
        'mallorca': 'mallorca', 'rcd mallorca': 'mallorca',
    },
    'BL': {
        'bayern': 'bayern munich', 'bayern munchen': 'bayern munich',
        'fc bayern munchen': 'bayern munich', 'fc bayern munich': 'bayern munich',
        'borussia dortmund': 'dortmund', 'bvb': 'dortmund',
        'bayer leverkusen': 'leverkusen', 'rb leipzig': 'leipzig',
        'eintracht frankfurt': 'ein frankfurt', 'frankfurt': 'ein frankfurt',
        'borussia monchengladbach': "m gladbach", 'gladbach': 'm gladbach',
        'vfb stuttgart': 'stuttgart', 'vfl wolfsburg': 'wolfsburg',
    },
    'SA': {
        'inter milan': 'inter', 'internazionale': 'inter',
        'internazionale milano': 'inter', 'fc internazionale milano': 'inter',
        'ac milan': 'milan', 'as roma': 'roma', 'ssc napoli': 'napoli',
        'juve': 'juventus', 'atalanta bc': 'atalanta', 'ss lazio': 'lazio',
    },
    'L1': {
        'psg': 'paris sg', 'paris saint germain': 'paris sg',
        'paris saint germain fc': 'paris sg', 'olympique marseille': 'marseille',
        'olympique lyonnais': 'lyon', 'as monaco': 'monaco',
        'losc lille': 'lille', 'ogc nice': 'nice',
    },
}
DISPLAY = {
    'PL': {'man united': 'Manchester United', 'man city': 'Manchester City',
           'nott m forest': 'Nottingham Forest', 'tottenham': 'Tottenham',
           'brighton': 'Brighton', 'wolves': 'Wolves'},
    'LL': {'barcelona': 'Barcelona', 'real madrid': 'Real Madrid',
           'atletico madrid': 'Atlético Madrid', 'athletic bilbao': 'Athletic Bilbao',
           'real betis': 'Real Betis', 'real sociedad': 'Real Sociedad',
           'celta vigo': 'Celta Vigo', 'rayo vallecano': 'Rayo Vallecano',
           'espanyol': 'Espanyol', 'alaves': 'Alavés'},
    'BL': {'bayern munich': 'Bayern München', 'dortmund': 'Borussia Dortmund',
           'leverkusen': 'Bayer Leverkusen', 'ein frankfurt': 'Eintracht Frankfurt',
           'm gladbach': 'Borussia Mönchengladbach'},
    'SA': {'inter': 'Inter', 'milan': 'AC Milan', 'roma': 'Roma'},
    'L1': {'paris sg': 'Paris Saint-Germain', 'marseille': 'Marseille'},
}


def team_key(name, league='PL'):
    key = clean_name(name)
    if key.endswith(' fc'):
        key = key[:-3]
    return ALIASES[league].get(key, key)


def team_display(key, league='PL'):
    return DISPLAY[league].get(key, key.title())


def load_matches(folder: Path, league='PL'):
    if league not in LEAGUES:
        raise ValueError('Okänd liga.')
    # Valfri spelarfil hör inte till ligans matchresultat.
    paths = sorted(path for path in folder.glob('*.csv') if path.name != 'player_stats.csv')
    if not paths:
        raise ValueError(f'Inga CSV-filer för {LEAGUES[league]["name"]} i {folder}. Kör py fetch_data.py.')
    frames = []
    for path in paths:
        frame = pd.read_csv(path, encoding='latin-1', low_memory=False)
        if not REQUIRED.issubset(frame.columns):
            raise ValueError(f'{path.name} saknar: {sorted(REQUIRED - set(frame.columns))}')
        if 'Div' in frame.columns and not frame['Div'].dropna().eq(LEAGUES[league]['code']).all():
            raise ValueError(f'{path.name} verkar tillhöra fel liga. Kontrollera mappen.')
        columns = sorted(REQUIRED | ((set(ODDS) | set(TEAM_STATS)) & set(frame.columns)))
        frame = frame[columns].copy()
        frame['Date'] = pd.to_datetime(frame['Date'], dayfirst=True, errors='coerce', format='mixed')
        for column in ('FTHG', 'FTAG'):
            frame[column] = pd.to_numeric(frame[column], errors='coerce')
        for column in (*ODDS, *TEAM_STATS):
            if column in frame:
                frame[column] = pd.to_numeric(frame[column], errors='coerce')
        frame = frame.dropna(subset=list(REQUIRED))
        frame = frame[frame.FTR.isin(['H', 'D', 'A'])].copy()
        expected = frame.apply(lambda r: 'H' if r.FTHG > r.FTAG else 'A' if r.FTHG < r.FTAG else 'D', axis=1)
        if not frame.FTR.eq(expected).all():
            raise ValueError(f'{path.name} innehåller resultat som inte stämmer med målen.')
        frame['HomeTeam'] = frame.HomeTeam.map(lambda value: team_key(value, league))
        frame['AwayTeam'] = frame.AwayTeam.map(lambda value: team_key(value, league))
        frames.append(frame)
    matches = pd.concat(frames, ignore_index=True)
    if matches.empty:
        raise ValueError(f'CSV-filerna för {LEAGUES[league]["name"]} innehåller inga avslutade matcher.')
    key = ['Date', 'HomeTeam', 'AwayTeam']
    conflicting = matches.groupby(key)[['FTHG', 'FTAG']].nunique().gt(1).any(axis=1)
    if conflicting.any():
        raise ValueError('Samma match har olika målresultat i två CSV-filer.')
    matches = matches.drop_duplicates(subset=key)
    return matches.sort_values(key).reset_index(drop=True)


def form(history):
    if len(history) < WINDOW:
        return None
    return tuple(sum(item[i] for item in history) for i in range(3))


def feature_row(home, away, history, venue_history=None, ratings=None, last_played=None, date=None):
    h, a = form(history[home]), form(history[away])
    if h is None or a is None:
        return None
    result = dict(zip(FEATURES, (h[0], a[0], h[1], a[1], h[2], a[2])))
    if venue_history is not None:
        home_venue = venue_history['home'][home]
        away_venue = venue_history['away'][away]
        h_stats = tuple(sum(game[i] for game in home_venue) for i in range(3))
        a_stats = tuple(sum(game[i] for game in away_venue) for i in range(3))
        result.update(zip(VENUE_FEATURES, (
            len(home_venue), len(away_venue),
            h_stats[0], a_stats[0], h_stats[1], a_stats[1], h_stats[2], a_stats[2],
        )))
    if ratings is not None:
        def rest(team):
            last = (last_played or {}).get(team)
            if date is None or last is None:
                return 7
            return max(0, min(21, (pd.Timestamp(date) - pd.Timestamp(last)).days))
        result.update(home_elo=ratings.get(home, 1500.0), away_elo=ratings.get(away, 1500.0),
                      home_rest_days=rest(home), away_rest_days=rest(away))
    return result


def recent_form(history):
    games = list(history)
    result = {
        'wins': sum(item[0] == 3 for item in games),
        'draws': sum(item[0] == 1 for item in games),
        'losses': sum(item[0] == 0 for item in games),
        'sequence': [dict(points=item[0], scored=item[1], conceded=item[2]) for item in games],
    }
    for index, key in ((3, 'shots_on_target'), (4, 'yellow_cards')):
        observed = [item[index] for item in games if len(item) > index and item[index] is not None]
        result[key] = {'total': sum(observed), 'matches': len(observed)} if observed else None
    return result


def build_event_history(matches, window=20):
    """Senaste observerade matcher för fler faktasvar; ingår inte i träningsfeatures."""
    events = defaultdict(lambda: deque(maxlen=window))
    for game in matches.itertuples(index=False):
        total_goals = int(game.FTHG + game.FTAG)
        for team, goals, shots, cards in (
            (game.HomeTeam, game.FTHG, getattr(game, 'HST', None), getattr(game, 'HY', None)),
            (game.AwayTeam, game.FTAG, getattr(game, 'AST', None), getattr(game, 'AY', None)),
        ):
            events[team].append({
                'total_goals': total_goals, 'goals_scored': int(goals),
                'both_scored': int(game.FTHG > 0 and game.FTAG > 0),
                'shots': int(shots) if shots is not None and pd.notna(shots) else None,
                'cards': int(cards) if cards is not None and pd.notna(cards) else None,
            })
    return dict(events)


def build_dataset(matches):
    history = defaultdict(lambda: deque(maxlen=WINDOW))
    venue_history = {
        'home': defaultdict(lambda: deque(maxlen=VENUE_WINDOW)),
        'away': defaultdict(lambda: deque(maxlen=VENUE_WINDOW)),
    }
    ratings = defaultdict(lambda: 1500.0)
    last_played = {}
    rows = []
    # Dagens matcher delar samma historik; dagens resultat läggs till efteråt.
    for date, games in matches.groupby('Date', sort=True):
        pending = []
        for game in games.itertuples(index=False):
            home, away = game.HomeTeam, game.AwayTeam
            features = feature_row(home, away, history, venue_history, ratings, last_played, date)
            if features is not None:
                row = {'date': date, 'home': home, 'away': away,
                       'outcome': game.FTR, 'home_goals': int(game.FTHG),
                       'away_goals': int(game.FTAG), **features}
                if all(column in matches for column in ODDS):
                    row.update({column: getattr(game, column) for column in ODDS})
                rows.append(row)
            hg, ag = int(game.FTHG), int(game.FTAG)
            def available(column):
                value = getattr(game, column, None)
                return int(value) if value is not None and pd.notna(value) else None
            pending.append((home, away, hg, ag,
                            available('HST'), available('AST'), available('HY'), available('AY')))
        deltas = defaultdict(float)
        for home, away, hg, ag, hst, ast, hy, ay in pending:
            expected = 1 / (1 + 10 ** ((ratings[away] - ratings[home] - 65) / 400))
            outcome = 1 if hg > ag else .5 if hg == ag else 0
            change = 20 * min(1.6, 1 + .15 * abs(hg - ag)) * (outcome - expected)
            deltas[home] += change
            deltas[away] -= change
            h_record = (3 if hg > ag else 1 if hg == ag else 0, hg, ag, hst, hy)
            a_record = (3 if ag > hg else 1 if hg == ag else 0, ag, hg, ast, ay)
            history[home].append(h_record)
            history[away].append(a_record)
            venue_history['home'][home].append(h_record)
            venue_history['away'][away].append(a_record)
            last_played[home] = date
            last_played[away] = date
        for team, change in deltas.items():
            ratings[team] += change
    return pd.DataFrame(rows), history, venue_history, dict(ratings), last_played


def known_teams(matches):
    seasons = matches.Date.map(lambda d: d.year if d.month >= 7 else d.year - 1)
    current = matches[seasons == seasons.max()]
    return sorted(set(current.HomeTeam) | set(current.AwayTeam))


def find_teams(message, teams, league='PL'):
    normalized = clean_name(message)
    candidates = {clean_name(name): name for name in teams}
    candidates.update({alias: canonical for alias, canonical in ALIASES[league].items() if canonical in teams})
    hits = []
    for name, canonical in candidates.items():
        match = re.search(r'(?<![a-z0-9])' + re.escape(name) + r'(?:s)?(?![a-z0-9])', normalized)
        if match:
            hits.append((match.start(), match.end(), canonical))
    # Långa namn får företräde: "Inter Milan" ska inte bli Inter mot Milan.
    occupied = []
    selected = []
    for start, end, team in sorted(hits, key=lambda hit: (-(hit[1] - hit[0]), hit[0])):
        if not any(start < other_end and end > other_start for other_start, other_end in occupied):
            occupied.append((start, end))
            selected.append((start, team))
    result = []
    for _, team in sorted(selected):
        if team not in result:
            result.append(team)
    return result


def parse_teams(message, teams, league='PL'):
    result = find_teams(message, teams, league)
    if len(result) != 2:
        raise ValueError('Skriv två lag i hemma–borta-ordning som finns i den valda ligan.')
    return result
