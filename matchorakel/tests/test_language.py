"""Fri chatt följer konversationen när en lokal språkmodell är installerad."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from language_chat import general_answer, language_status


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


if __name__ == '__main__':
    unittest.main()
