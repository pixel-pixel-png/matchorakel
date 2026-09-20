"""Retained statistics, optional data and report regressions."""
import json,tempfile,unittest
from pathlib import Path
from qa.support import Sandbox
from player_data import player_summary
import app as web

class ExistingFeatures(unittest.TestCase):
 def setUp(self):self.env=Sandbox().__enter__();self.client=self.env.client;self.ctx={'league':'LL','home':'barcelona','away':'sevilla'}
 def tearDown(self):self.env.__exit__(None,None,None)
 def ask(self,q):
  r=self.client.post('/chat',json={'message':q,'context':self.ctx});self.assertEqual(r.status_code,200,r.get_json());return r.get_json()
 def test_form_defense_clean_sheets_and_why(self):
  for q,word in [('Hur är lagens form?','Form'),('Hur många mål släpper Barcelona in?','Insläppta'),('Hur ofta håller Barcelona nollan?','Hållna'),('Varför?','Därför')]:
   with self.subTest(q=q):a=self.ask(q);self.assertEqual(a['kind'],'insight');self.assertIn(word,a['title'])
 def test_goal_markets_and_future_cards(self):
  for q in ['Blir det över 2,5 mål?','Gör båda lagen mål?','Får Sevilla över 5 skott på mål mot Barcelona?','Får Sevilla minst 2 gula kort mot Barcelona?','Vad är vanligast?','Vad ska jag lägga för lapp?']:
   with self.subTest(q=q):a=self.ask(q);self.assertEqual(a['kind'],'insight');self.assertTrue(a['cards'])
 def test_correction(self):
  a=self.ask('Jag menade Real Madrid istället för Sevilla');self.assertEqual(a['context']['away'],'real madrid')
 def test_missing_events_are_not_zero(self):
  self.env.states['LL']['history']['barcelona']=[(1,1,1,None,None)]*5
  a=self.ask('Hur många skott på mål har Barcelona haft?');self.assertIn('saknas',a['response']);self.assertNotIn('0 skott',a['response'])
 def test_low_sample_does_not_produce_prediction(self):
  self.env.states['LL']['history']['barcelona']=self.env.states['LL']['history']['barcelona'][:2]
  a=self.ask('Barcelona mot Sevilla, vem vinner?');self.assertNotEqual(a['kind'],'prediction');self.assertIn('historik',a['response'])
 def test_optional_player_csv(self):
  path=self.env.root/'data/player_stats.csv';path.write_text('date,league,player,team,minutes,shots_on_target,yellow_cards\n2026-09-01,LL,Raphinha,Barcelona,80,2,0\n2026-09-02,LL,Raphinha,Barcelona,70,0,1\n')
  a=self.ask('Hur många skott på mål har Raphinha haft?');self.assertEqual(a['kind'],'insight');self.assertEqual(a['cards'][0]['value'],'2')
 def test_malformed_player_values_are_not_counted(self):
  path=self.env.root/'data/player_stats.csv';path.write_text('date,league,player,team,minutes,shots_on_target,yellow_cards\n2026-09-01,LL,Raphinha,Barcelona,80,inf,0\n2026-09-02,LL,Raphinha,Barcelona,70,1.5,0\n')
  self.assertIsNone(player_summary(path,'LL','Raphinha','2026-09-14'))
 def test_report_bad_numeric_fields_do_not_crash_page(self):
  base={'league':'La Liga','source_matches':10,'selected_model':'test','periods':{k:{'first':'2025-01-01','last':'2025-02-01','matches':10} for k in ['train','validation','test']},'test':{'test':{'accuracy':None,'log_loss':{},'brier':'bad'}}}
  (self.env.root/'artifacts/evaluation_LL.json').write_text(json.dumps(base))
  r=self.client.get('/evaluation');self.assertEqual(r.status_code,200)
