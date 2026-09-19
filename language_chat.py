"""Samma chatt använder verifierad matchdata och en ansluten språkmodell."""
import json
import logging
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


INSTRUCTIONS = (
    'Du är Matchorakel och samtalar naturligt på svenska om fotboll och andra ämnen. '
    'Följ samtalet och svara på just den senaste frågan, utan att byta tillbaka till fotboll '
    'om personen byter ämne. Ställ gärna en relevant följdfråga i vanligt samtal. '
    'För specifika matcher, arenor, skador, spelarstatistik och sannolikheter får du bara '
    'använda verifierade fakta i underlaget. Hitta inte på aktuella resultat, scheman '
    'eller odds. Var tydlig när aktuella fakta saknas.'
)
logger = logging.getLogger(__name__)


def ollama_model():
    """Använd bara en redan installerad lokal modell; hämta aldrig modeller utan samtycke."""
    try:
        with urlopen('http://127.0.0.1:11434/api/tags', timeout=0.35) as response:
            data = json.load(response)
        models = [item.get('name') for item in data.get('models', []) if isinstance(item, dict)]
        selected = os.environ.get('MATCHORAKEL_OLLAMA_MODEL', '').strip()
        if selected in models:
            return selected
        return 'gemma3:4b' if 'gemma3:4b' in models else next((item for item in models if isinstance(item, str)), None)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None


def language_status():
    if os.environ.get('GROQ_API_KEY', '').strip():
        return 'AI ansluten'
    if os.environ.get('OPENAI_API_KEY', '').strip():
        return 'AI ansluten'
    return 'AI ansluten' if ollama_model() else None


def general_answer(question, facts, history=None):
    groq_key = os.environ.get('GROQ_API_KEY', '').strip()
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    recent = []
    for turn in (history or [])[-6:]:
        if isinstance(turn, dict):
            recent.append((str(turn.get('question', ''))[:300], str(turn.get('answer', ''))[:400]))
    if groq_key:
        messages = [{'role': 'system', 'content': INSTRUCTIONS + '\nVerifierade fakta: ' + json.dumps(facts, ensure_ascii=False)}]
        for user, assistant in recent:
            if user and assistant:
                messages.extend([{'role': 'user', 'content': user}, {'role': 'assistant', 'content': assistant}])
        messages.append({'role': 'user', 'content': question})
        payload = {'model': os.environ.get('MATCHORAKEL_GROQ_MODEL', 'openai/gpt-oss-20b'),
                   'messages': messages, 'max_completion_tokens': 500}
        request = Request('https://api.groq.com/openai/v1/chat/completions',
                          data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                          headers={'Authorization': 'Bearer ' + groq_key,
                                   'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=30) as response:
                result = json.load(response)
            content = (result.get('choices') or [{}])[0].get('message', {}).get('content', '')
            if not isinstance(content, str) or not content.strip():
                logger.warning('Groq gav ett tomt svar. Kontrollera modellens inställningar och kvoter.')
                return None
            return content.strip()
        except HTTPError as error:
            # Endast maskinläsbara felkoder: logga aldrig svaret, frågan eller nyckeln.
            details = {}
            try:
                details = json.loads(error.read(4096)).get('error', {})
            except (ValueError, UnicodeError, OSError, AttributeError):
                pass
            if not isinstance(details, dict):
                details = {}
            safe = lambda item: re.sub(r'[^a-zA-Z0-9_.-]', '', str(item or ''))[:80]
            logger.warning('Groq svarade med HTTP %s; felkod=%s; typ=%s.',
                           error.code, safe(details.get('code')) or 'saknas',
                           safe(details.get('type')) or 'saknas')
            return None
        except (URLError, TimeoutError, ValueError, OSError, AttributeError, IndexError) as error:
            logger.warning('Groq-anrop misslyckades: %s.', type(error).__name__)
            return None
    if not key:
        model = ollama_model()
        if not model:
            return None
        messages = [{'role': 'system', 'content': INSTRUCTIONS + '\nFakta: ' + json.dumps(facts, ensure_ascii=False)}]
        for user, assistant in recent:
            if user and assistant:
                messages.extend([{'role': 'user', 'content': user}, {'role': 'assistant', 'content': assistant}])
        messages.append({'role': 'user', 'content': question})
        payload = {'model': model, 'messages': messages, 'stream': False}
        request = Request('http://127.0.0.1:11434/api/chat',
                          data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                          headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=90) as response:
                result = json.load(response)
            return (result.get('message') or {}).get('content', '').strip() or None
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            return None
    payload = {
        'model': os.environ.get('MATCHORAKEL_LANGUAGE_MODEL', 'gpt-5-mini'),
        'store': False,
        'max_output_tokens': 550,
        'instructions': (
            INSTRUCTIONS
        ),
        'input': json.dumps({'fråga': question, 'tidigare_chatt': recent,
                             'verifierade_fakta': facts}, ensure_ascii=False),
    }
    request = Request('https://api.openai.com/v1/responses',
                      data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                      headers={'Authorization': 'Bearer ' + key,
                               'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None
    parts = [block.get('text', '') for item in data.get('output', [])
             if item.get('type') == 'message' for block in item.get('content', [])
             if block.get('type') == 'output_text']
    return '\n'.join(parts).strip() or None
