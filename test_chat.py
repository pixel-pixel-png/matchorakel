"""Regressions at the public API boundary, with explicitly synthetic match data."""
import json
import threading
import unittest
from unittest.mock import patch
from qa.support import Sandbox
import app as web

class ChatTests(unittest.TestCase):
 def test_prediction_is_not_suggested_again_for_bare_match(self):
  answer=self.ask('Barcelona mot Sevilla')
  self.assertFalse(any('vinner' in q for q in answer['suggestions']))
 def setUp(self):self.env=Sandbox().__enter__();self.client=self.env.client
 def tearDown(self):self.env.__exit__(None,None,None)
 def ask(self,q,context=None):
  r=self.client.post('/chat',json={'message':q,'context':context});self.assertEqual(r.status_code,200,r.get_json());return r.get_json()
 def test_context_after_greeting_and_team_change(self):
  first=self.ask('Barcelona mot Sevilla');greeting=self.ask('hej',first['context']);self.assertEqual(first['context'],greeting['context'])
  second=self.ask('Vem vinner?',greeting['context']);self.assertEqual(first['scoreline'],second['scoreline'])
  changed=self.ask('Arsenal mot Chelsea',second['context']);self.assertEqual(changed['league'],'PL')
 def test_new_single_team_does_not_reuse_old_pair(self):
  old=self.ask('Barcelona mot Sevilla');answer=self.ask('Hur många gula kort har Real Madrid haft?',old['context']);self.assertEqual(answer['context']['home'],'real madrid');self.assertIsNone(answer['context']['away']);self.assertNotIn('Barcelona',answer['response'])
 def test_same_team_twice_does_not_produce_self_match(self):
  answer=self.ask('Barcelona mot Barcelona, vem vinner?');self.assertNotEqual(answer['kind'],'prediction')
 def test_compound_preserves_both_answers(self):
  answer=self.ask('Barcelona mot Sevilla, vem vinner och hur många gula kort har lagen fått?');self.assertEqual(answer['kind'],'combined');self.assertEqual(answer['parts'][0]['kind'],'prediction');self.assertIn('gula kort',answer['parts'][1]['response'])
 def test_preliminary_kickoff_does_not_pretend_midnight(self):
  answer=self.ask('När spelar Sevilla mot Barcelona?');self.assertFalse(answer['fixtures'][0]['kickoff_confirmed'])
 def test_finished_match_uses_result_not_prediction(self):
  answer=self.ask('Vem vann Barcelona mot Sevilla?');self.assertEqual(answer['fixtures'][0]['score'],{'home':2,'away':1});self.assertEqual(answer['fixtures'][0]['status'],'FINISHED')
 def test_bad_probability_is_rejected(self):
  self.env.states['LL']['model'].predict_proba=lambda _: [[float('nan'),.2,.3]]
  response=self.client.post('/chat',json={'message':'Barcelona mot Sevilla'});self.assertNotEqual(response.get_json().get('kind'),'prediction')
 def test_no_partial_response_is_returned_on_ai_error(self):
  with patch.dict('os.environ',{'GEMINI_API_KEY':''}):
   r=self.client.post('/chat',json={'message':'Förklara pressmönster'});self.assertEqual(r.status_code,503);self.assertEqual(r.get_json()['kind'],'error')
 def test_private_update_is_blocked_on_public_service(self):
  with patch.object(web,'PUBLIC_SITE',True):self.assertEqual(self.client.post('/api/data/update',json={'kind':'results'}).status_code,403)
 def test_rate_limit(self):
  with patch.object(web,'PUBLIC_SITE',True):
   web.chat_requests.clear();web.total_requests.clear();web.daily_requests.clear()
   for _ in range(8):self.assertEqual(self.client.post('/chat',json={'message':'hej'}).status_code,200)
   self.assertEqual(self.client.post('/chat',json={'message':'hej'}).status_code,429)
   web.chat_requests.clear();web.total_requests.clear();web.daily_requests.clear()
 def test_cancel_is_scoped_to_visitor_and_id(self):
  event=threading.Event();event.response=None
  web.active_requests[('127.0.0.1','abcdefghijkl')]=event
  try:
   self.assertFalse(self.client.post('/api/chat/cancel',json={'request_id':'other'}).get_json()['cancelled']);self.assertFalse(event.is_set())
   self.assertTrue(self.client.post('/api/chat/cancel',json={'request_id':'abcdefghijkl'}).get_json()['cancelled']);self.assertTrue(event.is_set())
  finally:web.active_requests.clear()
 def test_duplicate_active_request_rejected(self):
  web.active_requests[('127.0.0.1','abcdefghijkl')]=threading.Event()
  try:self.assertEqual(self.client.post('/chat',json={'message':'hej','request_id':'abcdefghijkl'}).status_code,409)
  finally:web.active_requests.clear()
 def test_bad_fixture_data_and_unknown_routes(self):
  (self.env.root/'data'/'fixtures.json').write_text('{"fixtures":[null,{},42]}');self.assertEqual(self.client.get('/api/fixtures').get_json(),[])
  self.assertEqual(self.client.get('/absent').status_code,404);self.assertEqual(self.client.get('/api/absent').status_code,404)
 def test_health_and_static_routes(self):
  self.assertEqual(self.client.get('/health').get_json()['leagues_ready'],5)
  for route in ['/','/evaluation','/static/script.js','/static/style.css','/static/favicon.svg','/static/fonts/InterVariable.woff2']:
   with self.subTest(route=route):
    r=self.client.get(route);self.assertEqual(r.status_code,200);r.close()
 def test_input_bounds(self):
  for body in [{'message':'x'*2001},{'message':''},[],{'message':[]},{'message':None}]:self.assertEqual(self.client.post('/chat',json=body).status_code,400)
  self.assertEqual(self.client.post('/chat',data='x'*32769,content_type='application/json').status_code,413)
