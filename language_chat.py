"""Samma chatt använder verifierad matchdata och en ansluten språkmodell."""
import json
import logging
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


INSTRUCTIONS = (
    'Du är Matchorakel, en kortfattad fotbollsanalytiker. Svara på svenska och börja direkt med svaret. '
    'Enkel fråga: 1–2 meningar. Resultattips: skriv först "Prediction: Lag A 2–1 Lag B" med siffror '
    'från tillhandahållen modell, sedan 1X2 om den finns och högst fyra korta meningar om de '
    'viktigaste verifierade faktorerna. Skilj observationer från sannolikheter och möjliga utfall. '
    'Följ senaste relevanta matchkontext; besvara bara den nya frågan. Använd enbart uppgifterna '
    'i faktafältet för statistik, resultat, datum, skador och spelare. Saknas en uppgift, säg det kort '
    'och analysera det som faktiskt finns. Hitta inte på siffror, press, skador eller spelschema. '
    'Skriv vanlig löptext utan hälsningsfras, rubriker, markdown, avslutning eller rutinmässig varning.'
)
logger = logging.getLogger(__name__)
groq_health = 'unverified'
groq_last_error_code = None
gemini_health = 'unverified'
gemini_last_error_code = None
other_health = 'unverified'


def clean_ai_answer(value):
    """Ta bort kända standardfraser, men behåll fakta och användarens efterfrågade innehåll."""
    if not isinstance(value, str):
        return None
    answer = value.strip()
    answer = re.sub(r'^(?:bra fråga[!.]?|självklart[!.]?|här är (?:min |en )?analys(?: av matchen)?[.:]?|absolut[!.]?)\s*',
                    '', answer, flags=re.IGNORECASE)
    answer = re.sub(r'\s*(?:hoppas det hjälper[!.]?|säg till om du vill veta mer[!.]?|kom ihåg att fotboll är oförutsägbart[!.]?)\s*$',
                    '', answer, flags=re.IGNORECASE)
    answer = re.sub(r'\*\*(.*?)\*\*', r'\1', answer)
    answer = re.sub(r'(?m)^#{1,4}\s+', '', answer)
    return answer.strip() or None


def connection_health():
    if os.environ.get('GEMINI_API_KEY', '').strip():
        return gemini_health
    if os.environ.get('GROQ_API_KEY', '').strip():
        return groq_health
    return 'unconfigured' if not os.environ.get('OPENAI_API_KEY', '').strip() and not ollama_model() else other_health


def connection_error_code():
    if os.environ.get('GEMINI_API_KEY', '').strip():
        return gemini_last_error_code if gemini_health == 'failed' else None
    return groq_last_error_code if groq_health == 'failed' and os.environ.get('GROQ_API_KEY', '').strip() else None


def ollama_model():
    """Använd bara en redan installerad lokal modell; hämta aldrig modeller utan samtycke."""
    try:
        with urlopen('http://127.0.0.1:11434/api/tags', timeout=0.35) as response:
            data = json.load(response)
        rows = data.get('models', []) if isinstance(data, dict) else []
        models = [item.get('name') for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []
        selected = os.environ.get('MATCHORAKEL_OLLAMA_MODEL', '').strip()
        if selected in models:
            return selected
        return 'gemma3:4b' if 'gemma3:4b' in models else next((item for item in models if isinstance(item, str)), None)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return None


def language_status():
    if os.environ.get('GEMINI_API_KEY', '').strip():
        return 'AI ansluten'
    if os.environ.get('GROQ_API_KEY', '').strip():
        return 'AI ansluten'
    if os.environ.get('OPENAI_API_KEY', '').strip():
        return 'AI ansluten'
    return 'AI ansluten' if ollama_model() else None


def general_answer(question, facts, history=None):
    global groq_health, groq_last_error_code, gemini_health, gemini_last_error_code, other_health
    gemini_key = os.environ.get('GEMINI_API_KEY', '').strip()
    groq_key = os.environ.get('GROQ_API_KEY', '').strip()
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    recent = []
    for turn in (history or [])[-6:]:
        if isinstance(turn, dict):
            recent.append((str(turn.get('question', ''))[:300], str(turn.get('answer', ''))[:400]))
    if gemini_key:
        messages = [{'role': 'system', 'content': INSTRUCTIONS + '\nVerifierade fakta: ' + json.dumps(facts, ensure_ascii=False)}]
        for user, assistant in recent:
            if user and assistant:
                messages.extend([{'role': 'user', 'content': user}, {'role': 'assistant', 'content': assistant}])
        messages.append({'role': 'user', 'content': question})
        payload = {'model': os.environ.get('MATCHORAKEL_GEMINI_MODEL', 'gemini-2.5-flash-lite').strip() or 'gemini-2.5-flash-lite',
                   'messages': messages, 'max_tokens': 768, 'temperature': 0.4}
        request = Request('https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
                          data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                          headers={'Authorization': 'Bearer ' + gemini_key,
                                   'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=35) as response:
                result = json.load(response)
            choices = result.get('choices') if isinstance(result, dict) else None
            choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            message = choice.get('message')
            content = message.get('content') if isinstance(message, dict) else None
            if not isinstance(content, str) or not content.strip():
                logger.warning('Gemini gav ett tomt eller ogiltigt svar.')
                gemini_health = 'failed'
                gemini_last_error_code = None
                return None
            gemini_health = 'ok'
            gemini_last_error_code = None
            return clean_ai_answer(content)
        except HTTPError as error:
            logger.warning('Gemini svarade med HTTP %s.', error.code)
            gemini_health = 'failed'
            gemini_last_error_code = error.code
            return None
        except (URLError, TimeoutError, ValueError, OSError, AttributeError, IndexError) as error:
            logger.warning('Gemini-anrop misslyckades: %s.', type(error).__name__)
            gemini_health = 'failed'
            gemini_last_error_code = None
            return None
    if groq_key:
        messages = [{'role': 'system', 'content': INSTRUCTIONS + '\nVerifierade fakta: ' + json.dumps(facts, ensure_ascii=False)}]
        for user, assistant in recent:
            if user and assistant:
                messages.extend([{'role': 'user', 'content': user}, {'role': 'assistant', 'content': assistant}])
        messages.append({'role': 'user', 'content': question})
        selected_model = os.environ.get('MATCHORAKEL_GROQ_MODEL', 'openai/gpt-oss-20b').strip()
        payload = {'model': selected_model,
                   'messages': messages, 'max_completion_tokens': 768, 'temperature': 0.5}
        # GPT-OSS använder egna resonemangstoken; en alltför liten gräns kan ge tomt användarsvar.
        if selected_model.startswith('openai/gpt-oss-'):
            payload.update(reasoning_format='hidden', reasoning_effort='low')
        request = Request('https://api.groq.com/openai/v1/chat/completions',
                          data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                          headers={'Authorization': 'Bearer ' + groq_key,
                                   'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=30) as response:
                result = json.load(response)
            choices = result.get('choices') if isinstance(result, dict) else None
            choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            message = choice.get('message')
            content = message.get('content') if isinstance(message, dict) else None
            if not isinstance(content, str) or not content.strip():
                logger.warning('Groq gav ett tomt svar. Kontrollera modellens inställningar och kvoter.')
                groq_health = 'failed'
                groq_last_error_code = None
                return None
            groq_health = 'ok'
            groq_last_error_code = None
            return clean_ai_answer(content)
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
            content_type = safe(error.headers.get('Content-Type', 'saknas'))
            logger.warning('Groq svarade med HTTP %s; felkod=%s; typ=%s; svarstyp=%s.',
                           error.code, safe(details.get('code')) or 'saknas',
                           safe(details.get('type')) or 'saknas', content_type)
            groq_health = 'failed'
            groq_last_error_code = error.code
            return None
        except (URLError, TimeoutError, ValueError, OSError, AttributeError, IndexError) as error:
            logger.warning('Groq-anrop misslyckades: %s.', type(error).__name__)
            groq_health = 'failed'
            groq_last_error_code = None
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
        payload = {'model': model, 'messages': messages, 'stream': False,
                   'options': {'temperature': 0.25, 'num_predict': 280}}
        request = Request('http://127.0.0.1:11434/api/chat',
                          data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                          headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=90) as response:
                result = json.load(response)
            message = result.get('message') if isinstance(result, dict) else None
            content = message.get('content') if isinstance(message, dict) else None
            other_health = 'ok' if isinstance(content, str) and content.strip() else 'failed'
            return clean_ai_answer(content) if other_health == 'ok' else None
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            other_health = 'failed'
            return None
    payload = {
        'model': os.environ.get('MATCHORAKEL_LANGUAGE_MODEL', 'gpt-5-mini'),
        'store': False,
        'max_output_tokens': 400,
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
        other_health = 'failed'
        return None
    output = data.get('output', []) if isinstance(data, dict) else []
    parts = [block.get('text', '') for item in output if isinstance(item, dict)
             and item.get('type') == 'message' and isinstance(item.get('content'), list)
             for block in item['content'] if isinstance(block, dict)
             and block.get('type') == 'output_text' and isinstance(block.get('text'), str)] if isinstance(output, list) else []
    result = '\n'.join(parts).strip()
    other_health = 'ok' if result else 'failed'
    return clean_ai_answer(result)
