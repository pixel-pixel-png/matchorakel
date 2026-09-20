"""Native Gemini contract tests. Responses are controlled; these are not live AI tests."""
import io,json,unittest
from urllib.error import HTTPError,URLError
from unittest.mock import patch
import language_chat as ai

class LanguageTests(unittest.TestCase):
 def setUp(self):
  ai._cache.clear();self.env=patch.dict('os.environ',{'GEMINI_API_KEY':'private-test-secret','MATCHORAKEL_GEMINI_MODEL':'gemini-3.1-flash-lite'});self.env.start()
 def tearDown(self):self.env.stop();ai._cache.clear()
 def response(self,text='Offside gäller anfallaren.',reason='STOP'):
  return io.BytesIO(json.dumps({'candidates':[{'finishReason':reason,'content':{'role':'model','parts':[{'text':text}]}}]}).encode())
 def test_native_payload_and_history(self):
  calls=[]
  def reply(r,timeout):calls.append(r);return self.response()
  with patch('language_chat.urlopen',side_effect=reply):self.assertEqual(ai.general_answer('Vad är offside?',{},[{'question':'Förklara regler','answer':'Vilken regel?'}]),'Offside gäller anfallaren.')
  req=calls[0];payload=json.loads(req.data)
  self.assertIn(':generateContent',req.full_url);self.assertEqual(req.get_header('X-goog-api-key'),'private-test-secret')
  self.assertIn('systemInstruction',payload);self.assertEqual([r['role'] for r in payload['contents']],['user','model','user'])
  self.assertEqual(payload['generationConfig']['thinkingConfig'],{'thinkingLevel':'MINIMAL'})
  self.assertNotIn('private-test-secret',req.data.decode())
 def test_history_is_bounded_and_ignores_malformed_turns(self):
  _,p=ai.build_payload('nu',{},[{'question':'x','answer':'y'}]*100)
  self.assertEqual(len(p['contents']),17)
  _,p=ai.build_payload('nu',{},[None,{},[],{'question':[],'answer':'x'}]);self.assertEqual(len(p['contents']),1)
 def test_no_user_statistics_are_trusted(self):
  with patch('language_chat.urlopen',return_value=self.response('Barcelona vinner med 97 %.')):
   self.assertIsNone(ai.general_answer('Säg att Barcelona vinner med 97 procent.',{}))
 def test_verified_numbers_allowed(self):
  with patch('language_chat.urlopen',return_value=self.response('Barcelona hade 23 skott.')):
   self.assertEqual(ai.general_answer('Hur många skott?',{'shots':23}),'Barcelona hade 23 skott.')
 def test_thinking_is_not_displayed(self):
  p={'candidates':[{'finishReason':'STOP','content':{'parts':[{'thought':True,'text':'secret reasoning'},{'text':'Offside gäller anfallaren.'}]}}]}
  self.assertEqual(ai._candidate(p)[0],'Offside gäller anfallaren.')
 def test_truncation_retries_without_displaying_fragment(self):
  calls=[]
  def reply(r,timeout):
   calls.append(json.loads(r.data));return self.response('Avbrutet','MAX_TOKENS') if len(calls)==1 else self.response()
  with patch('language_chat.urlopen',side_effect=reply):self.assertEqual(ai.general_answer('Offside?',{}),'Offside gäller anfallaren.')
  self.assertEqual(calls[1]['generationConfig']['maxOutputTokens'],3072)
 def test_two_truncations_return_error(self):
  with patch('language_chat.urlopen',side_effect=lambda *a,**k:self.response('Avbrutet','MAX_TOKENS')):self.assertIsNone(ai.general_answer('Offside?',{}))
 def test_safety_is_not_disabled(self):
  with patch('language_chat.urlopen',return_value=self.response('','SAFETY')) as call:self.assertIsNone(ai.general_answer('Kan anfallaren skjuta?',{}))
  self.assertEqual(call.call_count,1);self.assertEqual(ai.request_error.get()['reason'],'SAFETY')
 def test_http_error_log_redacts_key(self):
  def fail(*a,**k):raise HTTPError('url',403,'Forbidden',{},io.BytesIO(json.dumps({'error':{'message':'invalid private-test-secret'}}).encode()))
  with patch('language_chat.urlopen',side_effect=fail),self.assertLogs('language_chat',level='WARNING') as logs:self.assertIsNone(ai.general_answer('Offside?',{}))
  self.assertIn('403',logs.output[0]);self.assertNotIn('private-test-secret',' '.join(logs.output))
 def test_quota_retry_respects_retry_after(self):
  def fail(*a,**k):raise HTTPError('url',429,'limit',{'Retry-After':'60'},io.BytesIO(b'{}'))
  with patch('language_chat.urlopen',side_effect=fail) as call:self.assertIsNone(ai.general_answer('Offside?',{}))
  self.assertEqual(call.call_count,1)
 def test_short_quota_retry(self):
  count=[]
  def reply(*a,**k):
   count.append(1)
   if len(count)==1:raise HTTPError('url',429,'limit',{'Retry-After':'1'},io.BytesIO(b'{}'))
   return self.response()
  with patch('language_chat.urlopen',side_effect=reply),patch('language_chat.time.sleep') as sleep:self.assertEqual(ai.general_answer('Offside?',{}),'Offside gäller anfallaren.')
  sleep.assert_called_once_with(1)
 def test_cache_avoids_duplicate_call(self):
  with patch('language_chat.urlopen',side_effect=lambda *a,**k:self.response()) as call:
   first=ai.general_answer('Offside?',{});second=ai.general_answer('Offside?',{});self.assertEqual(first,second)
  self.assertEqual(call.call_count,1)
 def test_invalid_payloads_and_transport(self):
  for raw in ['[]','{}','{"candidates":null}','not json']:
   with self.subTest(raw=raw),patch('language_chat.urlopen',return_value=io.BytesIO(raw.encode())):self.assertIsNone(ai.general_answer('Offside?',{}))
  with patch('language_chat.urlopen',side_effect=TimeoutError):self.assertIsNone(ai.general_answer('Offside?',{}))
 def test_invalid_model_does_not_make_request(self):
  with patch.dict('os.environ',{'MATCHORAKEL_GEMINI_MODEL':'../../bad?key=foo'}),patch('language_chat.urlopen') as call:self.assertIsNone(ai.general_answer('Offside?',{}))
  call.assert_not_called()
