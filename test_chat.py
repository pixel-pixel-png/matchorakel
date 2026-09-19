"""Regressionskontroller för matchfrågor och svar efter schemauppdatering."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from werkzeug.serving import make_server

import app as webapp


class ExampleModel:
    classes_ = ('H', 'D', 'A')

    def predict_proba(self, rows):
        return [[0.4, 0.3, 0.3]]


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        (root / 'data').mkdir()
        (root / 'artifacts').mkdir()
        (root / 'data' / 'fixtures.json').write_text(json.dumps({'fixtures': [
            {'league': 'UCL', 'home': 'Paris Saint-Germain FC', 'away': 'FC Barcelona',
             'utc_date': '2099-10-20T19:00:00Z', 'status': 'SCHEDULED',
             'venue': None, 'source': 'football-data.org', 'synced_at': '2099-09-18T00:00:00Z'},
            {'league': 'LL', 'home': 'Sevilla FC', 'away': 'FC Barcelona',
             'utc_date': '2099-10-21T19:00:00Z', 'status': 'SCHEDULED',
             'venue': None, 'source': 'football-data.org', 'synced_at': '2099-09-18T00:00:00Z'}
        ]}), encoding='utf-8')
        for code in ('LL', 'L1'):
            (root / 'artifacts' / f'model_{code}.joblib').touch()
        self.root_patch = patch.object(webapp, 'ROOT', root)
        self.root_patch.start()
        event = {'total_goals': 3, 'goals_scored': 1, 'both_scored': 1, 'shots': 4, 'cards': 2}
        recent = [(3, 2, 1, 4, 2)] * 5
        self.states = {
            'LL': {'teams': ['barcelona', 'real madrid', 'sevilla'], 'history': {'barcelona': recent, 'real madrid': recent, 'sevilla': recent},
                   'event_history': {'barcelona': [event] * 20}, 'last_match': '2026-09-14',
                   'model': ExampleModel(), 'model_name': 'Testmodell'},
            'L1': {'teams': ['paris sg'], 'history': {'paris sg': recent},
                   'event_history': {'paris sg': [event] * 20}, 'last_match': '2026-09-14'},
        }
        self.state_patch = patch.object(webapp, 'get_state', side_effect=lambda league: self.states[league])
        self.state_patch.start()
        self.client = webapp.app.test_client()

    def tearDown(self):
        self.state_patch.stop()
        self.root_patch.stop()
        self.directory.cleanup()

    def ask(self, message, context=None):
        response = self.client.post('/chat', json={'message': message, 'context': context})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_question_in_screenshot_returns_analysis_and_fixture(self):
        answer = self.ask('barcelona mot psg, vad är säkrast att hända')
        self.assertEqual(answer['kind'], 'insight')
        self.assertEqual(answer['league'], 'UCL')
        self.assertTrue(answer['cards'])
        labels = ' '.join(card['label'] for card in answer['cards']).lower()
        for category in ('mål', 'kort', 'skott'):
            self.assertIn(category, labels)
        self.assertIn('tidigare', answer['summary'].lower())
        self.assertIn('2099-10-20', answer['fixture']['utc_date'])
        self.assertEqual(len(answer['suggestions']), 3)
        self.assertNotIn('100%', json.dumps(answer))

    def test_followup_cards_form_and_date(self):
        first = self.ask('Barcelona mot PSG: vad är vanligast?')
        context = first['context']
        self.assertIn('kort', json.dumps(self.ask('Hur många gula kort?', context)['cards']).lower())
        self.assertIn('form', self.ask('Hur är lagens form?', context)['title'].lower())
        date = self.ask('När och var spelas matchen?', context)
        self.assertEqual(date['kind'], 'fixtures')
        self.assertEqual(date['fixtures'][0]['utc_date'], '2099-10-20T19:00:00Z')

    def test_score_prediction_is_concrete_and_followup_keeps_match(self):
        first = self.ask('Barcelona mot Sevilla')
        self.assertEqual(first['kind'], 'prediction')
        self.assertEqual(first['scoreline']['source'].startswith('Grov'), True)
        self.assertTrue(0 <= first['scoreline']['home'] <= 7)
        followup = self.ask('Vad tror du matchen slutar?', first['context'])
        self.assertEqual(followup['kind'], 'prediction')
        self.assertEqual(followup['scoreline'], first['scoreline'])
        self.assertEqual(followup['context'], first['context'])
        self.assertEqual(self.ask('Vad tror du?', first['context'])['kind'], 'prediction')

    def test_unverified_cross_league_prediction_is_labelled_hypothetical(self):
        (Path(self.directory.name) / 'data' / 'fixtures.json').unlink()
        first = self.ask('Barcelona mot PSG, hur slutar matchen?')
        self.assertEqual(first['kind'], 'insight')
        self.assertIn('resultattips', first['title'].lower())
        self.assertIn('inte bekräfta', first['summary'])
        self.assertNotIn('fixture', first)

    def test_cup_schedule_prediction_aliases_and_context(self):
        fixture_path = Path(self.directory.name) / 'data' / 'fixtures.json'
        data = json.loads(fixture_path.read_text(encoding='utf-8'))
        data['fixtures'].extend([
            {'league': 'CDR', 'home': 'Sevilla FC', 'away': 'FC Barcelona',
             'utc_date': '2099-10-22T19:00:00Z', 'status': 'SCHEDULED',
             'venue': None, 'source': 'football-data.org'},
            {'league': 'EL', 'home': 'Paris Saint-Germain FC', 'away': 'FC Barcelona',
             'utc_date': '2099-10-23T19:00:00Z', 'status': 'SCHEDULED',
             'venue': None, 'source': 'football-data.org'},
        ])
        fixture_path.write_text(json.dumps(data), encoding='utf-8')
        answer = self.ask('Sevilla mot Barcelona i Copa del Rey, när spelar de?')
        self.assertEqual(answer['kind'], 'fixtures')
        self.assertEqual(answer['league'], 'CDR')
        self.assertEqual(answer['fixtures'][0]['utc_date'], '2099-10-22T19:00:00Z')
        alias = self.ask('Sevilla mot Barcelona i Copa España, hur slutar matchen?')
        self.assertEqual(alias['kind'], 'insight')
        self.assertEqual(alias['league'], 'CDR')
        self.assertIn('resultattips', alias['title'].lower())
        self.assertEqual(alias['fixture']['utc_date'], '2099-10-22T19:00:00Z')
        self.assertIn('resultattips', self.ask('Vad tror du resultatet blir?', alias['context'])['title'].lower())
        euro = self.ask('Europa League: PSG mot Barcelona, vem vinner?')
        self.assertEqual(euro['league'], 'EL')
        self.assertIn('resultattips', euro['title'].lower())
        self.assertEqual(self.client.get('/api/fixtures?league=CDR').status_code, 200)
        self.assertEqual(len(self.client.get('/api/fixtures?league=CDR').get_json()), 1)

    def test_cup_unavailable_does_not_fabricate_match_or_date(self):
        answer = self.ask('Kommande FA Cup-matcher')
        self.assertEqual(answer['kind'], 'text')
        self.assertIn('Inget verifierat', answer['response'])
        hypothetical = self.ask('Barcelona mot Sevilla i Copa del Rey, vem vinner?')
        self.assertEqual(hypothetical['league'], 'CDR')
        self.assertEqual(hypothetical['kind'], 'insight')
        self.assertNotIn('fixture', hypothetical)
        self.assertIn('inte bekräfta', hypothetical['summary'])

    def test_corrupt_fixture_file_does_not_take_down_chat_or_api(self):
        fixture_path = Path(self.directory.name) / 'data' / 'fixtures.json'
        for data in ('{', '{"fixtures": {"not": "a list"}}', '{"fixtures": [null, "bad"]}',
                     '{"fixtures": [{"league":"UCL","home":{},"away":[],"utc_date":17,"status":"SCHEDULED"}]}'):
            with self.subTest(data=data):
                fixture_path.write_text(data, encoding='utf-8')
                self.assertEqual(self.client.get('/api/fixtures').status_code, 200)
                result = self.ask('Barcelona mot Real Madrid')
                self.assertEqual(result['kind'], 'prediction')

    def test_corrupt_venue_shape_does_not_take_down_fixture_panel(self):
        fixture_path = Path(self.directory.name) / 'data' / 'fixtures.json'
        data = json.loads(fixture_path.read_text(encoding='utf-8'))
        data['team_venues'] = {'LL': ['broken'], 'UCL': 42}
        fixture_path.write_text(json.dumps(data), encoding='utf-8')
        self.assertEqual(self.client.get('/api/fixtures?league=UCL').status_code, 200)
        self.assertEqual(self.ask('När spelar Barcelona mot PSG i Champions League?')['kind'], 'fixtures')

    def test_untrusted_context_and_history_never_crash_chat(self):
        for context in (["LL"], {'league': []}, {'league': {'bad': 1}}, {'league': 'LL', 'home': []}):
            with self.subTest(context=context):
                response = self.client.post('/chat', json={'message': 'Hur mår du?', 'context': context,
                    'history': [{'question': ['bad'], 'answer': {'unexpected': 1}}, None, 17]})
                self.assertEqual(response.status_code, 200, response.get_json())
        malformed = self.client.post('/chat', json={'message': 'Barcelona mot Real Madrid',
            'context': {'league': 'LL', 'home': {}, 'away': ['wrong']},
            'history': [{'question': [1, 2], 'answer': None}]})
        self.assertEqual(malformed.status_code, 200, malformed.get_json())

    def test_single_team_unknown_question_uses_existing_facts(self):
        for question in ('Vad tycker du om Barcelona?', 'Hur spelar Barcelona?'):
            with self.subTest(question=question):
                result = self.ask(question)
                self.assertEqual(result['kind'], 'insight')
                self.assertIn('insläppta', result['cards'][0]['detail'])
        defense = self.ask('Hur många mål släpper Barcelona in?')
        self.assertIn('Insläppta', defense['title'])
        xg = self.ask('Barcelona mot Real Madrid, xG?')
        self.assertIn('saknar uppmätt', xg['summary'])

    def test_requested_goal_market_has_labeled_prediction_without_validation(self):
        answer = self.ask('Barcelona mot Sevilla, gör båda lagen mål?')
        self.assertEqual(answer['kind'], 'insight')
        self.assertEqual(answer['title'], 'Båda lagen gör mål')
        self.assertIn('inte en testad', answer['summary'])
        self.assertIn('%', answer['cards'][0]['value'])

    def test_future_shots_and_cards_are_labeled_historical_references(self):
        self.states['LL']['event_history']['sevilla'] = [{'shots': 6, 'cards': 2}] * 20
        for query, label in (('Får Sevilla över 5 skott på mål mot Barcelona?', 'minst 6 skott'),
                             ('Får Sevilla minst 2 gula kort mot Barcelona?', 'minst 2 gula kort')):
            with self.subTest(query=query):
                answer = self.ask(query)
                self.assertEqual(answer['kind'], 'insight')
                self.assertTrue(any(label in card['label'].lower() for card in answer['cards']))
                self.assertIn('ingen testad matchprognos', answer['cards'][0]['detail'])
        self.states['LL']['event_history'] = {'barcelona': [{}] * 20, 'sevilla': [{}] * 20}
        missing = self.ask('Får Sevilla minst 2 gula kort mot Barcelona?')
        self.assertEqual(missing['kind'], 'text')
        self.assertIn('färre än 12', missing['response'])

    def test_missing_event_fields_do_not_produce_server_error(self):
        self.states['LL']['event_history'] = {'barcelona': [{'total_goals': 3}] * 20,
                                              'real madrid': [{'shots': 4}] * 20}
        result = self.ask('Barcelona mot Real Madrid, vad är säkrast?')
        self.assertEqual(result['kind'], 'insight')
        self.assertTrue(result['cards'])

    def test_partial_evaluation_report_renders_empty_state(self):
        report = Path(self.directory.name) / 'artifacts' / 'evaluation_LL.json'
        for content in ('{', '{"league":"La Liga","selected_model":"X","source_matches":3,"periods":{},"test":{}}'):
            with self.subTest(content=content):
                report.write_text(content, encoding='utf-8')
                response = self.client.get('/evaluation')
                self.assertEqual(response.status_code, 200)
                self.assertIn('Inga nya resultat', response.get_data(as_text=True))

    def test_different_questions_return_relevant_answers(self):
        context = self.ask('Barcelona mot PSG: vad är vanligast?')['context']
        for question, fragment in (
            ('Hur många mål gör lagen?', 'mål'),
            ('Får lagen skott på mål?', 'skott'),
            ('Blir det gula kort?', 'kort'),
            ('Varför ser det ut så?', 'form'),
            ('Vem vinner?', 'tidigare'),
        ):
            with self.subTest(question=question):
                answer = self.ask(question, context)
                self.assertEqual(answer['kind'], 'insight')
                self.assertIn(fragment, (answer['title'] + json.dumps(answer['cards'], ensure_ascii=False) + answer['summary']).lower())

    def test_compound_question_and_friend_chat(self):
        answer = self.ask('Vem tror du vinner Barcelona mot Real Madrid och vad brukar hända med gula kort?')
        self.assertEqual(answer['kind'], 'combined')
        self.assertEqual(len(answer['parts']), 2)
        self.assertEqual(answer['parts'][0]['kind'], 'prediction')
        self.assertEqual(answer['parts'][1]['kind'], 'insight')
        self.assertIn('kort', answer['parts'][1]['title'].lower())
        self.assertTrue(all('vinner' not in item.lower() and 'kort' not in item.lower()
                            for item in answer['suggestions']))
        self.assertIn('fotboll', self.ask('Hur mår du?')['response'])

    def test_suggestions_do_not_repeat_asked_market(self):
        previous = self.ask('Barcelona mot Real Madrid, hur många gula kort?')
        reply = self.client.post('/chat', json={'message': 'Vad brukar hända med varningar?',
                                                'context': previous['context'],
                                                'history': [{'question': 'Hur många gula kort får lagen?', 'answer': 'Historiska kort.'}]})
        self.assertEqual(reply.status_code, 200)
        self.assertTrue(all('kort' not in label.lower() and 'varning' not in label.lower()
                            for label in reply.get_json()['suggestions']))

    def test_player_question_explains_missing_individual_data(self):
        answer = self.ask('Får Raphinha skott på mål i Barcelona mot PSG?')
        self.assertEqual(answer['kind'], 'fixtures')
        self.assertIn('inte verifierade spelarsiffror', answer['summary'])

    def test_freeform_greeting_and_missing_data_are_explicit(self):
        context = self.ask('Barcelona mot PSG, vad är säkrast?')['context']
        self.assertIn('match', self.ask('tack', context)['response'])
        self.assertIn('Du kan fråga', self.ask('Vad kan du göra?', context)['response'])
        self.states['LL']['event_history'].clear()
        answer = self.ask('Barcelona mot PSG, vad är säkrast?')
        self.assertEqual(answer['kind'], 'insight')  # PSG:s dokumenterade historik kan fortfarande visas.
        self.assertTrue(answer['cards'])

    def test_domestic_pair_is_not_forced_to_champions_league(self):
        answer = self.ask('Barcelona mot Real Madrid')
        self.assertEqual(answer['league'], 'LL')
        self.assertNotEqual(answer['kind'], 'fixtures')

    def test_chat_changes_topic_after_ucl_and_recognizes_next_domestic_match(self):
        first = self.ask('Vilka är kommande UCL matcher?')
        self.assertEqual(first['league'], 'UCL')
        mood = self.ask('Hur mår du?', first['context'])
        self.assertIn('fotboll', mood['response'].lower())
        self.assertTrue(mood['topic_reset'])
        reply = self.ask('Jag mår bra tack', first['context'])
        self.assertIn('fotboll', reply['response'])
        self.assertTrue(reply['topic_reset'])
        self.assertNotIn('fixtures', reply)
        unrelated = self.ask('Jag funderar på att plugga musik', first['context'])
        self.assertTrue(unrelated['topic_reset'])
        self.assertNotIn('Champions League-match', unrelated['response'])
        game = self.ask('Sevilla mot Barcelona', first['context'])
        self.assertEqual(game['league'], 'LL')
        self.assertEqual(game['kind'], 'prediction')
        self.assertEqual(game['fixture']['venue_confidence'], 'likely_home')
        self.assertIn('Sánchez-Pizjuán', game['fixture']['venue'])

    def test_exact_dialogue_without_ai_or_ucl_schedule_is_still_relevant(self):
        (webapp.ROOT / 'data' / 'fixtures.json').write_text(json.dumps({'fixtures': []}), encoding='utf-8')
        with patch.dict('os.environ', {'GROQ_API_KEY': '', 'OPENAI_API_KEY': ''}), \
                patch('language_chat.ollama_model', return_value=None):
            first = self.ask('hej hur mår du idag')
            followup = self.ask('bra tack', first['context'])
            self.assertIn('fotboll', followup['response'])
            self.assertNotIn('AI-anslutningen', followup['response'])
            pair = self.ask('Barcelona mot PSG, vad är vanligast?')
            self.assertEqual(pair['kind'], 'insight')
            self.assertEqual(pair['league'], 'UCL')
            self.assertNotIn('fixture', pair)
            self.assertIn('inget verifierat spelschema', pair['summary'])
            self.assertTrue(all('minst 1' not in card['label'].lower() for card in pair['cards']))
            second = self.ask('i champions league', pair['context'])
            self.assertEqual(second['league'], 'UCL')
            self.assertNotIn('Kör py update_fixtures.py', json.dumps(second, ensure_ascii=False))

    def test_scorer_followup_after_shots_uses_previous_match_without_inventing_player(self):
        first = self.ask('Sevilla mot Barcelona')
        shot = self.ask('Hur många skott på mål har lagen haft?', first['context'])
        self.assertIn('per match', json.dumps(shot['cards'], ensure_ascii=False))
        scorer = self.ask('vem gör mål tror du', shot['context'])
        self.assertEqual(scorer['kind'], 'insight')
        self.assertIn('enskild spelare', scorer['summary'])
        self.assertNotIn('AI-anslutningen', json.dumps(scorer, ensure_ascii=False))

    def test_atletico_alias_and_correction_in_same_conversation(self):
        self.states['LL']['teams'].append('atletico madrid')
        self.states['LL']['history']['atletico madrid'] = [(3, 2, 1, 4, 2)] * 5
        self.states['LL']['event_history']['atletico madrid'] = self.states['LL']['event_history']['barcelona']
        answer = self.ask('Atletico mot Barcelona')
        self.assertEqual(answer['league'], 'LL')
        self.assertIn('Atlético', answer['home'])
        prior = self.ask('Barcelona mot Real Madrid')
        fixed = self.ask('Jag menade Atletico istället för Real Madrid', prior['context'])
        self.assertEqual(fixed['league'], 'LL')
        self.assertIn('Atlético', fixed['away'])

    def test_popular_events_avoid_trivial_one_goal_claim_and_show_model_when_available(self):
        self.states['LL']['event_history']['real madrid'] = self.states['LL']['event_history']['barcelona']
        class GoalEstimate:
            def goal_markets(self, rows):
                return [{'over_2_5': .58, 'both_score': .46}]
        saved = self.states['LL']
        saved['goal_model'] = GoalEstimate()
        saved['goal_features'] = list(webapp.FEATURES)
        saved['goal_market_enabled'] = {'over_2_5': True, 'both_score': True}
        answer = self.ask('Barcelona mot Real Madrid, vad är vanligast?')
        self.assertEqual(answer['kind'], 'insight')
        labels = [card['label'] for card in answer['cards']]
        self.assertIn('Minst 3 mål totalt', labels)
        self.assertTrue(all('Minst 1' not in label and 'gör mål' not in label for label in labels))
        self.assertIn('58.0 %', json.dumps(answer['cards'], ensure_ascii=False))

    def test_popular_events_without_validated_goal_market_still_show_meaningful_goal_threshold(self):
        self.states['LL']['event_history']['real madrid'] = self.states['LL']['event_history']['barcelona']
        answer = self.ask('Barcelona mot Real Madrid, vad är vanligast?')
        labels = [card['label'] for card in answer['cards']]
        self.assertIn('Minst 3 mål totalt', labels)
        self.assertTrue(all('Minst 1' not in label for label in labels))

    def test_fifty_three_turn_conversations(self):
        openings = ['Vilka är kommande UCL matcher?', 'Barcelona mot Real Madrid',
                    'Hej', 'Sevilla mot Barcelona', 'Hur mår du?']
        turns = [('Jag mår bra tack', 'social'), ('Jag mår dåligt idag', 'social'),
                 ('Tack så mycket', 'social'), ('Vad gör du idag?', 'outside'),
                 ('Sevilla mot Barcelona', 'LL'), ('När spelar Sevilla mot Barcelona?', 'LL'),
                 ('Vilken arena spelar Sevilla mot Barcelona?', 'LL'),
                 ('Barca mot Real Madrid, vem vinner?', 'LL'),
                 ('Vill du prata om musik?', 'outside'),
                 ('Hur många gula kort brukar lagen få?', 'football')]
        with patch('language_chat.ollama_model', return_value=None):
            self.assertEqual(len(openings) * len(turns), 50)
            for opening in openings:
                for followup, category in turns:
                    with self.subTest(opening=opening, followup=followup):
                        first = self.ask(opening)
                        second = self.ask(followup, first.get('context'))
                        if category == 'LL':
                            self.assertEqual(second.get('league'), 'LL')
                        elif category in ('social', 'outside'):
                            self.assertEqual(second['kind'], 'text')
                            self.assertTrue(second['topic_reset'])
                            self.assertNotIn('Champions League-match', second['response'])
                        elif first.get('league') == 'UCL':
                            self.assertIn('Vilken Champions League-match', second['response'])
                        context = None if second.get('topic_reset') else second.get('context')
                        third = self.ask('Jag mår bra tack', context)
                        self.assertEqual(third['kind'], 'text')
                        self.assertIn('fotboll', third['response'].lower())

    def test_multiple_sentences_and_social_topic_reset(self):
        answer = self.ask('Sevilla mot Barcelona. Var spelar de? Vem vinner?')
        self.assertEqual(answer['kind'], 'combined')
        self.assertEqual([part['kind'] for part in answer['parts']], ['prediction', 'fixtures', 'prediction'])
        self.assertEqual(answer['parts'][1]['fixtures'][0]['venue_confidence'], 'likely_home')
        switched = self.ask('Barcelona mot Madrid. Jag mår bra tack.')
        self.assertEqual(switched['kind'], 'combined')
        self.assertTrue(switched['topic_reset'])
        self.assertIsNone(switched['context'])

    def test_page_serves_followups_script_and_validates_input(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertNotIn(b'openChatSetup', self.client.get('/').data)
        javascript = self.client.get('/static/script.js', buffered=True)
        self.assertEqual(javascript.status_code, 200)
        self.assertIn(b'followups', javascript.data)
        self.assertEqual(self.client.post('/chat', json={'message': ''}).status_code, 400)
        self.assertEqual(self.client.post('/chat', json=['hej']).status_code, 400)

    def test_public_chat_is_one_interface_and_private_updates_are_blocked(self):
        with patch.object(webapp, 'PUBLIC_SITE', True), patch('language_chat.urlopen') as model:
            model.return_value.__enter__.return_value.read.return_value = json.dumps({
                'choices': [{'message': {'content': 'Kul att du mår bra!'}}]}).encode()
            with patch.dict('os.environ', {'GROQ_API_KEY': 'fake-key'}):
                self.assertTrue(self.client.get('/api/chat/status').get_json()['public'])
                self.assertEqual(self.client.post('/api/data/update', json={'kind': 'results'}).status_code, 403)
                greeting = self.ask('Jag mår bra tack')
                self.assertIn('fotboll', greeting['response'])
                self.assertEqual(self.ask('Barcelona mot Real Madrid')['kind'], 'prediction')

    def test_public_rate_limit_per_visitor(self):
        with patch.object(webapp, 'PUBLIC_SITE', True):
            webapp.chat_requests.clear()
            webapp.total_requests.clear()
            webapp.daily_requests.clear()
            for _ in range(8):
                self.assertEqual(self.client.post('/chat', json={'message': 'Hej'}).status_code, 200)
            response = self.client.post('/chat', json={'message': 'Hej'})
            self.assertEqual(response.status_code, 429)
            self.assertIn('gräns', response.get_json()['error'])
            webapp.chat_requests.clear()
            webapp.total_requests.clear()
            webapp.daily_requests.clear()

    def test_real_local_http_server_serves_page_and_chat(self):
        server = make_server('127.0.0.1', 0, webapp.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(address + '/') as response:
                self.assertIn(b'<form id="composer"', response.read())
            with urlopen(address + '/static/script.js') as response:
                self.assertIn(b'followups', response.read())
            payload = json.dumps({'message': 'Barcelona mot PSG, vad är säkrast att hända'}).encode()
            req = Request(address + '/chat', data=payload, headers={'Content-Type': 'application/json'})
            with urlopen(req) as response:
                answer = json.load(response)
            self.assertEqual(answer['kind'], 'insight')
            self.assertEqual(len(answer['suggestions']), 3)
        finally:
            server.shutdown()
            thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
