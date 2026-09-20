"""Run the recorded adversarial corpus locally without sending live AI requests."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qa.run_cases import run
if __name__=='__main__':sys.exit(bool(run('manual')))
