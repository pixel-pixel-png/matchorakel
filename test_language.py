"""Fri chatt följer konversationen när en lokal språkmodell är installerad."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from language_chat import general_answer, language_status
from app import app


class LanguageTests(unittest.TestCase):
    def test_local_model_receives_previous_turns_and_answers_current_question(self):
        requests = []

        def reply(request, timeout):
            requests.append(request)
            if isinstance(request, str):
                return io.BytesIO(json.dumps({'models': [{'name': 'gemma3:4b'}]}).encode())
            return io.BytesIO(json.dumps({'message': {'content': 'Vad kul att du mår bra!'}}).encode())

        with patch.dict('os.environ', {'OPENAI_API_KEY': '', 'GROQ_API_KEY': ''}), patch('language_chat.urlopen', side_effect=reply):
            self.assertEqual(language_status(), 'AI ansluten')
            answer = general_answer('Jag mår bra tack', {'fotboll': 'Ingen aktuell match.'},
                                    [{'question': 'Hur mår du?', 'answer': 'Bra, hur mår du?'}])
        self.assertEqual(answer, 'Vad kul att du mår bra!')
        self.assertEqual(requests[-1].full_url, 'http://127.0.0.1:11434/api/chat')
        messages = json.loads(requests[-1].data)['messages']
        self.assertEqual([item['role'] for item in messages], ['system', 'user', 'assistant', 'user'])
        self.assertEqual(messages[-1]['content'], 'Jag mår bra tack')

    def test_hosted_model_uses_history_and_never_exposes_key(self):
        requests = []

        def reply(request, timeout):
            requests.append(request)
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': 'Kul att höra!'}}]}).encode())

        with patch.dict('os.environ', {'GROQ_API_KEY': 'private-test-key', 'OPENAI_API_KEY': ''}), \
                patch('language_chat.urlopen', side_effect=reply):
            self.assertEqual(language_status(), 'AI ansluten')
            answer = general_answer('Jag mår bra', {'aktuell_match': None},
                                    [{'question': 'Hur mår du?', 'answer': 'Bra, tack!'}])
        self.assertEqual(answer, 'Kul att höra!')
        self.assertEqual(requests[0].full_url, 'https://api.groq.com/openai/v1/chat/completions')
        self.assertEqual(requests[0].get_header('Authorization'), 'Bearer private-test-key')
        messages = json.loads(requests[0].data)['messages']
        settings = json.loads(requests[0].data)
        self.assertEqual(settings['reasoning_format'], 'hidden')
        self.assertEqual(settings['reasoning_effort'], 'low')
        self.assertGreaterEqual(settings['max_completion_tokens'], 600)
        self.assertEqual([item['role'] for item in messages], ['system', 'user', 'assistant', 'user'])
        self.assertNotIn('private-test-key', requests[0].data.decode())

    def test_hosted_api_error_logs_status_without_secret(self):
        failure = HTTPError('https://api.groq.com/openai/v1/chat/completions', 401,
                            'Unauthorized', {}, io.BytesIO(b'failed'))
        with patch.dict('os.environ', {'GROQ_API_KEY': 'private-test-key'}), \
                patch('language_chat.urlopen', side_effect=failure), \
                self.assertLogs('language_chat', level='WARNING') as logs:
            self.assertIsNone(general_answer('hej', {}, []))
        self.assertIn('HTTP 401', logs.output[0])
        self.assertNotIn('private-test-key', logs.output[0])

    def test_groq_permission_error_logs_code_without_response_secrets(self):
        body = json.dumps({'error': {'code': 'model_permission_blocked_project',
                                     'type': 'permissions_error',
                                     'message': 'private-test-key'}}).encode()
        failure = HTTPError('https://api.groq.com/openai/v1/chat/completions', 403,
                            'Forbidden', {}, io.BytesIO(body))
        with patch.dict('os.environ', {'GROQ_API_KEY': 'private-test-key'}), \
                patch('language_chat.urlopen', side_effect=failure), \
                self.assertLogs('language_chat', level='WARNING') as logs:
            self.assertIsNone(general_answer('hej', {}, []))
        self.assertIn('HTTP 403; felkod=model_permission_blocked_project; typ=permissions_error', logs.output[0])
        self.assertNotIn('private-test-key', logs.output[0])
        with patch.dict('os.environ', {'GROQ_API_KEY': 'private-test-key'}):
            status = app.test_client().get('/api/chat/status').get_json()
        self.assertEqual(status['ai_health'], 'failed')
        self.assertEqual(status['ai_error_code'], 403)

    def test_success_with_malformed_ai_payload_does_not_raise(self):
        for payload in ([], {'choices': {}}, {'choices': [None]}, {'choices': [{'message': None}]}):
            with self.subTest(payload=payload), patch.dict('os.environ', {'GROQ_API_KEY': 'test-key'}), \
                    patch('language_chat.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())), \
                    self.assertLogs('language_chat', level='WARNING'):
                self.assertIsNone(general_answer('Säg hej', {}, []))
        def reply(request, timeout):
            return io.BytesIO(b'{"models":[{"name":"gemma3:4b"}]}') if isinstance(request, str) else io.BytesIO(b'[]')
        with patch.dict('os.environ', {'GROQ_API_KEY': '', 'OPENAI_API_KEY': ''}), \
                patch('language_chat.urlopen', side_effect=reply):
            self.assertIsNone(general_answer('Säg hej', {}, []))


if __name__ == '__main__':
    unittest.main()
