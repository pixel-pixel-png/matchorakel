"""Kvalitetskontroll med olika fotbollsfrågor, följdfrågor och frågor utanför ämnet."""
import re
import unittest
from unittest.mock import patch

import test_chat
from language_chat import INSTRUCTIONS, clean_ai_answer


class AnswerQuality(unittest.TestCase):
    def test_health_not_found_and_large_payload(self):
        import app as webapp
        client = webapp.app.test_client()
        self.assertEqual(client.get('/health').get_json()['status'], 'ok')
        self.assertEqual(client.get('/saknas').status_code, 404)
        self.assertIn('Till chatten', client.get('/saknas').get_data(as_text=True))
        self.assertEqual(client.get('/api/saknas').get_json()['error'], 'Adressen finns inte.')
        large = client.post('/chat', data=b'a' * 32769, headers={'Content-Type': 'application/json'})
        self.assertEqual(large.status_code, 413)
        self.assertIn('för stor', large.get_json()['error'])

    def test_prompt_and_cleanup(self):
        self.assertIn('börja direkt med svaret', INSTRUCTIONS)
        self.assertIn('vanlig löptext', INSTRUCTIONS)
        self.assertEqual(clean_ai_answer('Bra fråga! **Prediction: Barcelona 2–1 Sevilla.** Hoppas det hjälper!'),
                         'Prediction: Barcelona 2–1 Sevilla.')

    def test_thirty_plus_questions_keep_scope_and_match_context(self):
        fixture = test_chat.ChatTests('test_score_prediction_is_concrete_and_followup_keeps_match')
        fixture.setUp()
        try:
            initial = fixture.ask('Barcelona mot Sevilla')
            context = initial['context']
            football = ['Vem vinner?', 'Vad tror du matchen slutar?', 'Hur är formen?',
                'Varför?', 'Hur många skott på mål?', 'Hur många gula kort?', 'Blir det över 2,5 mål?',
                'Gör båda lagen mål?', 'Vilken arena?', 'När spelas matchen?', 'Vad är mest sannolikt?',
                'Hur ser försvaret ut?', 'xG?', 'Vad tror du om målbilden?', 'Vem gör mål?',
                'Kan du förklara?', 'Vad om Lewandowski är skadad?',
                'Vad släpper lagen in?', 'Hur bra är modellen?', 'Vad ska jag lägga för lapp?',
                'Hur många poäng har lagen?', 'Vilket lag är bättre?', 'Vilka styrkor?',
                'Blir det minst 2 gula kort?', 'Hur ofta blir det målrikt?',
                'När möts Barcelona och Sevilla?', 'Hur många mål gör Barcelona?',
                'Real Madrid mot Barcelona: vem vinner?', 'Atletico mot Sevilla?',
                'Barcelona mot PSG i Champions League?']
            unrelated = ['Hur mår du?', 'Jag mår bra tack', 'Vem är USAs president?',
                         'Kan du skriva kod åt mig?', 'Vilken film ska jag se?', 'Jag gillar kaffe']
            self.assertGreaterEqual(len(football) + len(unrelated), 30)
            with patch('app.general_answer', return_value=None):
                for message in football + unrelated:
                    with self.subTest(message=message):
                        answer = fixture.ask(message, context)
                        self.assertIn(answer['kind'], ('text', 'insight', 'fixtures', 'prediction', 'combined'))
                        strings = [str(answer.get('response', '')), str(answer.get('summary', ''))]
                        body = ' '.join(strings).lower()
                        self.assertNotRegex(body, r'^\s*(bra fråga|självklart|här är en analys)')
                        self.assertNotRegex(body, r'(hoppas det hjälper|säg till om du vill veta mer)')
                        if message in unrelated:
                            self.assertTrue(answer.get('topic_reset'))
                            self.assertIn('fotboll', body)
        finally:
            fixture.tearDown()


if __name__ == '__main__':
    unittest.main()
