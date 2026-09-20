import unittest
from unittest.mock import patch
from qa.support import Sandbox
class StressScenarios(unittest.TestCase):
 def test_long_or_malformed_history_does_not_leak_context(self):
  with Sandbox() as env:
   for history in [None,{},42,[None,[],{'question':{},'answer':None}],[{'question':'PSG mot Barcelona','answer':'PSG'}]*1000]:
    r=env.client.post('/chat',json={'message':'Arsenal mot Chelsea','history':history,'context':{'league':'UCL','home':'barcelona','away':'paris sg'}})
    if isinstance(history,list) and len(history)>100:
     self.assertEqual(r.status_code,413);continue
    self.assertEqual(r.status_code,200);self.assertEqual(r.get_json()['context'],{'league':'PL','home':'arsenal','away':'chelsea'})
