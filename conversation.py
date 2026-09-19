"""Småprat och samtalsstyrning. Fri språkförståelse kräver separat språkmodell."""
import re

from football import clean_name


def friendly_reply(message, history=None):
    phrase = clean_name(message)
    if re.search(r'\b(ucl|champions league|cl) (ar )?klart\b', phrase):
        return 'Okej, vi går vidare. Vad vill du prata om nu?'
    if re.search(r'\b(jag mar inte bra|mar inte bra|jag mar daligt|jag ar ledsen|jag kanner mig ensam)\b', phrase):
        return 'Det låter jobbigt. Vill du berätta vad som hänt? Jag lyssnar.'
    if re.search(r'\b(jag mar bra|jag mar fint|jag mar toppen|det ar bra med mig|jag mar okej)\b', phrase):
        return 'Vad skönt att höra! Vad har varit bra med dagen?'
    if re.search(r'\b(jag mar sadar|jag ar trott|det ar sadar med mig)\b', phrase):
        return 'Jag hör dig. Vill du berätta lite mer om hur dagen har varit?'
    if re.search(r'\b(jag ar glad|jag ar lycklig|jag ar peppad)\b', phrase):
        return 'Vad härligt att höra! Vad gjorde dig glad?'
    if re.search(r'\b(jag vill bara prata|kan vi prata om nagot annat|nu vill jag byta amne)\b', phrase):
        return 'Absolut. Vad vill du prata om?'
    if re.search(r'\b(jag ar hungrig)\b', phrase):
        return 'Har du lust att laga något, eller är du sugen på något snabbt?'
    if re.search(r'\b(tack det var hjalpsamt|tack for hjalpen)\b', phrase):
        return 'Vad bra att det hjälpte! Vill du fortsätta med något annat?'
    if re.search(r'\b(jag tycker om fotboll|jag gillar fotboll)\b', phrase):
        return 'Kul att du gillar fotboll! Vill du prata om ett lag eller om fotboll i allmänhet?'
    if re.search(r'\b(kan du saga god natt|god natt)\b', phrase):
        return 'God natt! Hoppas du får sova gott.'
    if re.search(r'\b(hur var din dag|hur har din dag varit)\b', phrase):
        return 'Jag har ingen egen dag på samma sätt som du, men det är trevligt att prata med dig. Hur var din dag?'
    if re.search(r'\b(jag fick|jag klarade|jag lyckades)\b', phrase) and any(
            word in phrase for word in ('tenta', 'prov', 'betyg', 'jobb', 'examen')):
        return 'Åh, grattis! Det låter som något du har jobbat för. Hur känns det nu?'
    if re.search(r'\b(jag pluggar|jag ska plugga|jag studerar|jag jobbar)\b', phrase):
        return 'Berätta mer! Vad håller du på med just nu?'
    if re.fullmatch(r'(hej|hejsan|tja|tjena|halloj|god morgon|god kvall)( du)?', phrase):
        return 'Hej! Kul att du är här. Hur är läget? Du kan också fråga mig om en match när du vill.'
    if re.search(r'\b(hur mar du|hur ar laget|hur har du det|hur ar det med dig|mar du bra|hur har din dag varit)\b', phrase):
        return 'Tack för att du frågar! Jag är här och redo att prata. Hur mår du själv?'
    if re.fullmatch(r'(bra|jattebra|toppen|okej|helt okej|sa dar|sadar|inte sa bra|daligt|jag mar bra|jag mar daligt|det ar bra med mig|bra sjalv)', phrase):
        return ('Tråkigt att höra. Vill du berätta vad som tynger dig? Jag lyssnar.' if
                phrase in ('daligt', 'inte sa bra', 'jag mar daligt') else
                'Skönt att höra! Vad är du sugen på att prata om?')
    if re.fullmatch(r'(tack|tack sa mycket|okej tack|tusen tack|schysst tack|grymt)', phrase):
        return 'Varsågod! Vi kan fortsätta om samma match eller prata om något helt annat.'
    if re.fullmatch(r'(vad heter du|vem ar du|ar du en robot|ar du en ai|beratta om dig sjalv|vem skapade dig)', phrase):
        return 'Jag heter Matchorakel. Jag är en digital chattassistent som hjälper dig med fotboll och vanliga frågor.'
    if re.fullmatch(r'(hur gammal ar du|var bor du|har du kanslor|ar du pa riktigt)', phrase):
        return 'Jag är ett datorprogram, så jag har ingen ålder, hemadress eller mänskliga känslor. Men jag kan gärna hålla dig sällskap i chatten.'
    if re.fullmatch(r'(vilket lag gillar du|vilket ar ditt favoritlag|vilka hejar du pa|vem hejar du pa)', phrase):
        return 'Jag har inget eget favoritlag, men jag hjälper dig gärna följa ditt. Vilket lag hejar du på?'
    if phrase in ('jag gillar fotboll', 'jag alskar fotboll'):
        return 'Det gör chatten roligare! Vilket lag eller vilken liga följer du mest?'
    if re.fullmatch(r'(kan du hjalpa mig|jag behover hjalp|hjalp mig)', phrase):
        return 'Absolut. Berätta vad du vill ha hjälp med, så tar vi det steg för steg.'
    if re.fullmatch(r'(vad gor du|vad gor du nu|vad hander|vad ar du uppe i)', phrase):
        return 'Jag är här och pratar med dig. Vill du snacka fotboll eller något annat?'
    if re.fullmatch(r'(hejda|vi hors|god natt|ha det bra|ses)', phrase):
        return 'Vi hörs! Ta hand om dig.'
    if re.fullmatch(r'(beratta ett skamt|kan du dra ett skamt|dra ett skamt)', phrase):
        return 'Varför tog fotbollsspelaren med sig en stege? För att nå högre divisioner. Jag hittar gärna på ett bättre nästa gång.'
    if re.fullmatch(r'(kan vi prata|vill du prata|ar du dar|lyssnar du)', phrase):
        return 'Ja, jag är här. Berätta vad du tänker på.'
    return None


def football_followup(message):
    """Behåll matchkontext bara för en uttrycklig fotbollsfråga."""
    phrase = clean_name(message)
    if phrase in ('varfor', 'varfor ser det ut sa', 'vem vinner', 'nar spelar de', 'nar spelas den',
                  'vilken arena', 'vad ar sakrast', 'hur gar matchen', 'kort', 'mal', 'skott', 'form'):
        return True
    return any(token in phrase for token in (
        'match', 'fotboll', 'champions', 'ucl', 'skott pa mal', 'gula kort',
        'var spelar', 'var spelas', 'nar spelar', 'nar spelas', 'vilken stadion',
        'resultat', 'vinner', 'arena', 'spelschema', 'speltid', 'vinstchans',
        'odds', 'speltips', 'lapp', 'betting', 'sakrast att handa', 'lagens form', 'vem tror du vinner',
        'bada lagen gor mal', 'over 2', 'hur manga mal'))


def parts_of_question(message):
    """Dela uttryckliga delfrågor utan att dela lagnamn eller vanlig löptext."""
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
    if any(token in phrase for token in ('nar spelar', 'nar spelas', 'vilket datum', 'vilken arena', 'var spelas')):
        return 'schedule'
    if any(token in phrase for token in ('varfor', 'forklara', 'hur kommer det sig')):
        return 'why'
    if any(token in phrase for token in ('over 2 5', 'minst 3 mal', '3 mal', 'mal totalt')):
        return 'goals'
    if any(token in phrase for token in ('sakrast', 'vanligast', 'mest troligt', 'lapp', 'speltips')):
        return 'ticket'
    if any(token in phrase for token in ('vem vinner', 'vinstchans', 'prognos', 'vem tror du')):
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
        if league == 'UCL':
            candidates = [item for item in candidates if item[0] != 'prediction']
    elif league:
        candidates = [('form', 'Hur är lagets form?'), ('schedule', 'När spelar laget nästa match?'),
                      ('shots', 'Hur många skott på mål har laget haft?')]
    else:
        candidates = [('prediction', 'Barcelona mot Real Madrid, vem tror du vinner?'),
                      ('form', 'Hur är Barcelonas form?'),
                      ('schedule', 'När spelar Barcelona i Champions League?')]
    return [label for category, label in candidates if category not in used][:3]
