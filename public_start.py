"""Serverstart: hämta frivilligt publicerat schema utan att blockera chatten."""
import os
import threading

from app import app

if os.environ.get('MATCHORAKEL_PUBLIC') == '1' and not os.environ.get('GEMINI_API_KEY', '').strip():
    print('AI-chatt är inte aktiverad: GEMINI_API_KEY saknas i Render Environment.', flush=True)


def update_public_fixtures():
    try:
        from update_fixtures import main
        main(token=os.environ['FOOTBALL_DATA_TOKEN'], logger=lambda line: print(line, flush=True))
    except (Exception, SystemExit) as error:
        print(f'Schemat kunde inte uppdateras: {error}', flush=True)


if os.environ.get('MATCHORAKEL_PUBLIC') == '1' and os.environ.get('FOOTBALL_DATA_TOKEN', '').strip():
    threading.Thread(target=update_public_fixtures, daemon=True).start()
