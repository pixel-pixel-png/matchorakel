"""Småprat och samtalsstyrning. Fri språkförståelse kräver separat språkmodell."""
import re

from football import clean_name


def football_followup(message):
    """Behåll matchkontext bara för en uttrycklig fotbollsfråga."""
    phrase = clean_name(message)
    if phrase in ('varfor', 'varfor ser det ut sa', 'vem vinner', 'nar spelar de', 'nar spelas den',
                  'vilken arena', 'vad ar sakrast', 'hur gar matchen', 'vad tror du matchen slutar',
                  'hur slutar matchen', 'vad tror du', 'vad tippar du', 'kort', 'mal', 'skott', 'form', 'hur ar formen', 'hur manga mal da'):
        return True
    return any(token in phrase for token in (
        'match', 'fotboll', 'champions', 'ucl', 'skott pa mal', 'gula kort',
        'var spelar', 'var spelas', 'nar spelar', 'nar spelas', 'vilken stadion',
        'resultat', 'vinner', 'arena', 'spelschema', 'speltid', 'vinstchans',
        'odds', 'speltips', 'lapp', 'betting', 'sakrast att handa', 'lagens form', 'vem tror du vinner',
        'bada lagen gor mal', 'over 2', 'hur manga mal',
        'vem gor mal', 'vem tror du gor mal', 'vilken spelare gor mal', 'malskytt',
        'slutar', 'slutresultat', 'prediktion', 'tippa'))


def parts_of_question(message):
    """Dela uttryckliga delfrågor utan att dela lagnamn eller vanlig löptext."""
    message = re.sub(r'\bvs\.', 'vs', message, flags=re.I)
    sentences = [item.strip() for item in re.split(r'(?<=[?.!])\s+(?=[A-ZÅÄÖ])', message) if item.strip()]
    if len(sentences) > 1:
        return [part for sentence in sentences for part in parts_of_question(sentence)]
    compact = re.search(r'\b(?:vinnare|seger)\s*,\s*(?:mål|mal)\s+och\s+(?:gula\s+)?kort\b', message, re.I)
    if compact:
        teams = message[:compact.start()].strip(' :,')
        return [f'{teams}, vem vinner?', 'Hur många mål blir det?', 'Hur många gula kort?']
    pieces = re.split(r'\s+(?:och|samt)\s+(?=(?:vad|hur|vem|när|nar|varför|varfor|var|på\s+vilken|pa\s+vilken|vilken|vilket|vilka|blir|får|far|brukar)\b)', message, maxsplit=2, flags=re.I)
    if len(pieces) > 1 and len(clean_name(pieces[0]).split()) == 1:
        return [message]
    return [part.strip(' ,?') for part in pieces if part.strip(' ,?')]


def intent(message):
    phrase = clean_name(message)
    if any(token in phrase for token in ('gula kort', 'gult kort', 'varningar', 'yellow card')):
        return 'cards'
    if any(token in phrase for token in ('skott pa mal', 'avslut pa mal', 'shots on target')):
        return 'shots'
    if any(token in phrase for token in ('form', 'senaste match', 'hur har lagen spelat')):
        return 'form'
    if any(token in phrase for token in ('nar ', 'when ', 'where ', 'nar spelar', 'nar spelas', 'vilket datum', 'vilken arena', 'var spelas')):
        return 'schedule'
    if any(token in phrase for token in ('varfor', 'forklara', 'hur kommer det sig')):
        return 'why'
    if any(token in phrase for token in ('over 2 5', 'minst 3 mal', '3 mal', 'mal totalt',
                                         'bada lagen gor mal', 'btts', 'gor bada lagen mal')):
        return 'goals'
    if any(token in phrase for token in ('sakrast', 'vanligast', 'mest troligt', 'lapp', 'speltips')):
        return 'ticket'
    if any(token in phrase for token in ('vem vinner', 'vinstchans', 'prognos', 'vem tror du', 'slutar', 'tippa', 'prediktion', 'prediction', 'predict', 'who wins')):
        return 'prediction'
    return phrase[:80]


def suggestions(answer, history=None, question=''):
    if answer.get('topic_reset'):
        return []
    context = answer.get('context') or {}
    league = context.get('league')
    home, away = context.get('home'), context.get('away')
    asked = [item.get('question', '') for item in (history or []) if isinstance(item, dict)] + [question]
    used = {intent(part) for phrase in asked for part in parts_of_question(phrase)}
    # A bare match name can already produce a prediction. Do not offer it again.
    def answered_categories(item):
        if not isinstance(item, dict):
            return set()
        result = {'prediction'} if item.get('kind') == 'prediction' else set()
        for child in item.get('parts', []):
            result.update(answered_categories(child))
        return result
    used.update(answered_categories(answer))
    if home and away:
        candidates = [
            ('prediction', 'Vem tror du vinner den här matchen?'),
            ('ticket', 'Vad är vanligast att hända i matchen?'),
            ('goals', 'Hur ofta blir det minst 3 mål?'),
            ('cards', 'Hur många gula kort brukar lagen få?'),
            ('shots', 'Hur många skott på mål har lagen haft?'),
            ('form', 'Hur är lagens form?'),
            ('why', 'Varför ser analysen ut så?'),
            ('schedule', 'När och var spelas matchen?'),
        ]
    elif league:
        candidates = [('form', 'Hur är lagets form?'), ('schedule', 'När spelar laget nästa match?'),
                      ('shots', 'Hur många skott på mål har laget haft?')]
    else:
        candidates = [('prediction', 'Barcelona mot Real Madrid, vem tror du vinner?'),
                      ('form', 'Hur är Barcelonas form?'),
                      ('schedule', 'När spelar Barcelona i Champions League?')]
    result = [label for category, label in candidates if category not in used][:1]
    if answer.get('language') == 'en':
        translations = {'Vem tror du vinner den här matchen?':'Who do you think wins this match?', 'Vad är vanligast att hända i matchen?':'Which outcomes are most likely?', 'Hur ofta blir det minst 3 mål?':'How often are there at least 3 goals?', 'Hur många gula kort brukar lagen få?':'How many yellow cards have the teams received?', 'Hur många skott på mål har lagen haft?':'How many shots on target have the teams had?', 'Hur är lagens form?':'What is the teams’ form?', 'Varför ser analysen ut så?':'Why this prediction?', 'När och var spelas matchen?':'When and where is the match?'}
        return [translations[x] for x in result if x in translations]
    return result
