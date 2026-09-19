"""Säkerställ sann källa och att uppdateringspanelen kan användas lokalt."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as webapp
from fixtures import fixture_public


class FixtureApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / 'data').mkdir()
        self.fixture = {'league': 'LL', 'home': 'FC Barcelona', 'away': 'Real Madrid CF',
                        'utc_date': '2099-10-25T19:00:00Z', 'status': 'SCHEDULED',
                        'venue': None, 'source': 'football-data.org', 'synced_at': '2099-09-18T00:00:00Z'}
        self.payload = {'fixtures': [self.fixture], 'team_venues': {
            'LL': {'barcelona': {'venue': 'Example Arena', 'source': 'lagprofil', 'synced_at': '2099-09-18'}}}}
        (self.root / 'data' / 'fixtures.json').write_text(json.dumps(self.payload))
        self.patch = patch.object(webapp, 'ROOT', self.root)
        self.patch.start()
        self.client = webapp.app.test_client()

    def tearDown(self):
        self.patch.stop()
        self.directory.cleanup()

    def test_estimated_venue_is_never_marked_confirmed(self):
        result = fixture_public(self.fixture, self.root)
        self.assertEqual(result['venue_confidence'], 'likely_home')
        self.assertEqual(result['venue'], 'Example Arena')
        other = {**self.fixture, 'home': 'Real Madrid CF'}
        self.assertEqual(fixture_public(other, self.root)['venue_confidence'], 'unknown')
        confirmed = {**self.fixture, 'venue': 'Confirmed Place'}
        self.assertEqual(fixture_public(confirmed, self.root)['venue_confidence'], 'confirmed')

    def test_match_panel_and_status_endpoints(self):
        fixtures = self.client.get('/api/fixtures').get_json()
        self.assertEqual(fixtures[0]['venue_confidence'], 'likely_home')
        self.assertEqual(self.client.get('/api/data/status').status_code, 200)
        self.assertEqual(self.client.get('/api/fixtures?league=bad').status_code, 400)

    def test_key_is_required_and_cross_origin_update_rejected(self):
        missing = self.client.post('/api/data/update', json={'kind': 'fixtures'})
        self.assertEqual(missing.status_code, 400)
        bad = self.client.post('/api/data/update', json={'kind': 'fixtures', 'token': 'test'},
                               headers={'Origin': 'https://unrelated.example'})
        self.assertEqual(bad.status_code, 403)


if __name__ == '__main__':
    unittest.main()
