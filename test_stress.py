"""Bred, reproducerbar kontroll av oväntade frågor och kontextbyten."""
import itertools
import unittest

import test_chat


class StressScenarios(unittest.TestCase):
    def test_many_phrasings_and_context_changes_never_return_server_error(self):
        fixture = test_chat.ChatTests('test_score_prediction_is_concrete_and_followup_keeps_match')
        fixture.setUp()
        try:
            contexts = [None, {'league': 'LL', 'home': 'barcelona', 'away': 'sevilla'},
                        {'league': 'UCL', 'home': 'FC Barcelona', 'away': 'Paris Saint-Germain FC'},
                        {'league': 'LL', 'home': 'nobody', 'away': 'barcelona'}]
            prefixes = ['', 'Kan du säga ', 'Jag undrar: ', 'Snälla, ', 'Typ ', 'Nu vill jag veta ',
                        'I morgon: ', 'För min vän: ', 'Barcelona mot Sevilla, ', 'PSG mot Barcelona, ']
            questions = ['vem vinner?', 'vad tror du matchen slutar?', 'vem gör mål?',
                         'hur många gula kort?', 'hur många skott på mål?', 'var spelas matchen?',
                         'jag mår bra tack', 'vad tycker du om mat?', 'blir det över 2,5 mål?',
                         'hur går det för Atletíco?', 'okändstad mot felstavatlag?',
                         'Barca mot Sevilla, varför?', '😀 ❄️ ↗ ⚽?', 'samma fråga igen?']
            # 560 olikartade anrop, inklusive giltiga och medvetet ogiltiga sammanhang.
            checked = 0
            for context, prefix, question in itertools.product(contexts, prefixes, questions):
                response = fixture.client.post('/chat', json={'message': prefix + question, 'context': context})
                self.assertLess(response.status_code, 500, (context, prefix, question, response.get_json()))
                self.assertIsInstance(response.get_json(), dict)
                checked += 1
            self.assertEqual(checked, 560)
        finally:
            fixture.tearDown()


if __name__ == '__main__':
    unittest.main()
