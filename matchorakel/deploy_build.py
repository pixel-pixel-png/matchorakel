"""Bygg matchunderlag för en kostnadsfri tjänst vars filsystem nollställs."""
import subprocess
import sys
from pathlib import Path


if __name__ == '__main__':
    project = Path(__file__).resolve().parent
    for script in ('fetch_data.py', 'train_model.py'):
        subprocess.run([sys.executable, str(project / script)], check=True, cwd=project)
    for league in ('PL', 'LL', 'BL', 'SA', 'L1'):
        if not (project / 'artifacts' / f'model_{league}.joblib').is_file():
            raise SystemExit(f'Modell saknas efter träningen: {league}. Kontrollera byggloggen.')
