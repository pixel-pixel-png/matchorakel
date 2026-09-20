import json,unittest
from pathlib import Path
from unittest.mock import patch
from qa.support import Sandbox
from qa.run_cases import check
from language_chat import INSTRUCTIONS,clean_ai_answer
class AnswerQuality(unittest.TestCase):
 def test_prompt_and_cleanup(self):
  self.assertIn('börja direkt med svaret',INSTRUCTIONS);self.assertIn('vanlig löptext',INSTRUCTIONS)
  self.assertEqual(clean_ai_answer('Bra fråga! **Prediction: Barcelona 2–1 Sevilla.** Hoppas det hjälper!'),'Prediction: Barcelona 2–1 Sevilla.')
 def test_all_recorded_adversarial_cases(self):
  cases=json.loads((Path(__file__).resolve().parents[1]/'qa/cases.json').read_text())
  self.assertGreaterEqual(len(cases),200)
  with Sandbox() as env,patch.dict('os.environ',{'GEMINI_API_KEY':''}):
   for case in cases:
    with self.subTest(id=case['id']):check(case,env)
