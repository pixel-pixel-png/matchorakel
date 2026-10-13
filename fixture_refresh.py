"""Periodisk schemahämtning, endast när en datanyckel är konfigurerad."""
import os
import threading

_worker = None
_lock = threading.Lock()


def start_fixture_refresh():
    global _worker
    token = os.environ.get('FOOTBALL_DATA_TOKEN', '').strip()
    if not token:
        return False
    with _lock:
        if _worker and _worker.is_alive():
            return True
        def run():
            from update_fixtures import main
            while True:
                try:
                    main(token=token, logger=lambda line: print(line, flush=True))
                except (Exception, SystemExit) as error:
                    detail=str(error).replace(token,'[nyckel dold]')[:240]
                    print('Schemat kunde inte uppdateras: '+detail, flush=True)
                threading.Event().wait(1800)
        _worker=threading.Thread(target=run,daemon=True,name='fixture-refresh')
        _worker.start()
    return True
