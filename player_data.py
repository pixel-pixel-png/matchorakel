"""Valfri spelarstatistik från en CSV med en rad per faktisk medverkan."""
from pathlib import Path
import math

import pandas as pd

from football import clean_name

REQUIRED = {'date', 'league', 'player', 'team', 'minutes', 'shots_on_target', 'yellow_cards'}


def player_summary(path: Path, league: str, name: str, as_of: str):
    """Returnera fem senaste observerade framträdanden, aldrig en matchprognos."""
    if not path.exists():
        return None
    data = pd.read_csv(path, encoding='utf-8-sig')
    missing = REQUIRED - set(data.columns)
    if missing:
        raise ValueError(f'Filen {path.name} saknar kolumnerna: {", ".join(sorted(missing))}.')
    data['date'] = pd.to_datetime(data['date'], errors='coerce', utc=True)
    for field in ('minutes', 'shots_on_target', 'yellow_cards'):
        data[field] = pd.to_numeric(data[field], errors='coerce')
    data = data[(data.league == league) & (data.date <= pd.to_datetime(as_of, utc=True)) &
                (data.minutes > 0) & (data.shots_on_target >= 0) &
                (data.yellow_cards >= 0)].copy()
    data = data.loc[data['minutes'].map(lambda n: math.isfinite(n) and 0 < n <= 180).astype(bool)]
    for field, maximum in (('shots_on_target', 50), ('yellow_cards', 2)):
        data = data.loc[data[field].map(lambda n: math.isfinite(n) and 0 <= n <= maximum and float(n).is_integer()).astype(bool)]
    data = data.dropna(subset=['player','team'])
    data['_key'] = data.player.map(clean_name)
    data = data[data._key == clean_name(name)]
    if data.empty:
        return None
    # Två rader för samma spelare på samma datum kan snedvrida statistiken.
    data = data.sort_values('date').drop_duplicates(['date', '_key'], keep='last').tail(5)
    return {
        'player': str(data.player.iloc[-1]), 'matches': len(data),
        'last_date': str(data.date.max().date()),
        'shots': int(data.shots_on_target.sum()),
        'shot_matches': int((data.shots_on_target > 0).sum()),
        'cards': int(data.yellow_cards.sum()),
        'card_matches': int((data.yellow_cards > 0).sum()),
    }
