import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backend as b


class CompetitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = b.Store(Path(self.tmp.name) / 'test.sqlite3')
        self.pid = 337204
        self.profile = {'player_id': self.pid, 'player': 'Test Player', **dict.fromkeys(b.FIELDS, 50)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_entry_mapping_uses_final_hawkeye_choice(self):
        entries = b.entrants()
        self.assertEqual(len(entries), 11)
        self.assertEqual(len({e['player_id'] for e in entries}), 11)
        self.assertEqual(next(e['player_id'] for e in entries if e['entrant'] == 'Hawkeye1'), 337204)
        self.assertNotIn(467300, {e['player_id'] for e in entries})

    def test_refresh_preserves_original_baseline(self):
        with patch.object(b, 'utcnow', return_value='2026-10-30T12:00:00+00:00'):
            self.store.save_profile(self.pid, self.profile)
        with patch.object(b, 'utcnow', return_value='2026-11-05T12:00:00+00:00'):
            self.store.save_profile(self.pid, {**self.profile, 'overall': 52, 'pace': 55})
        self.assertEqual(self.store.baseline(self.pid)['overall'], 50)
        self.assertEqual(self.store.latest()[self.pid]['overall'], 52)
        row = next(r for r in b.standings(self.store) if r['player_id'] == self.pid)
        self.assertEqual(row['gains']['overall'], 2)
        self.assertEqual(row['attribute_gain'], 5)
        self.assertNotIn('rank', row)

    def test_after_training_start_cannot_become_baseline(self):
        with patch.object(b, 'utcnow', return_value=b.TRAINING_START):
            self.store.save_profile(self.pid, self.profile)
        self.assertIsNone(self.store.baseline(self.pid))
        row = next(r for r in b.standings(self.store, confirmed=True) if r['player_id'] == self.pid)
        self.assertIsNone(row['gains']['overall'])
        self.assertNotIn('rank', row)

    def test_incomplete_attributes_cannot_become_baseline(self):
        with patch.object(b, 'utcnow', return_value='2026-10-30T12:00:00+00:00'):
            self.store.save_profile(self.pid, {**self.profile, 'pace': None})
        self.assertIsNone(self.store.baseline(self.pid))

    def test_backup_restores_baseline_and_never_overwrites_it(self):
        with patch.object(b, 'utcnow', return_value='2026-10-30T12:00:00+00:00'):
            self.store.save_profile(self.pid, self.profile)
        backup = self.store.backup()
        restored = b.Store(Path(self.tmp.name) / 'restored.sqlite3')
        restored.restore(backup)
        self.assertEqual(restored.baseline(self.pid), self.store.baseline(self.pid))
        changed = json.loads(backup)
        changed['tables']['baselines'][0][1] = json.dumps(dict.fromkeys(b.FIELDS, 1))
        restored.restore(json.dumps(changed))
        self.assertEqual(restored.baseline(self.pid)['overall'], 50)

    def test_bad_backup_is_rejected_before_any_write(self):
        with patch.object(b, 'utcnow', return_value='2026-10-30T12:00:00+00:00'):
            self.store.save_profile(self.pid, self.profile)
        d = json.loads(self.store.backup())
        d['tables']['baselines'][0][2] = '2026-11-05T00:00:00Z'
        other = b.Store(Path(self.tmp.name) / 'invalid.sqlite3')
        with self.assertRaises(ValueError):
            other.restore(json.dumps(d))
        self.assertEqual(other.latest(), {})

    def test_current_null_club_does_not_reuse_old_contract(self):
        p = b.profile({'metadata': {'firstName': 'Bob', 'lastName': 'Test', 'overall': 58},
                       'currentClub': None, 'contract': {'club': {'name': 'Old FC'}}}, self.pid)
        self.assertTrue(p['club_known'])
        self.assertIsNone(p['club'])

    def test_metadata_attributes_and_club(self):
        p = b.profile({'data': {'metadata': {'firstName': 'Test', 'lastName': 'Player',
                        'overall': 50, 'attributes': {'pace': 60, 'defending': 40}},
                        'activeContract': {'club': {'name': 'Current FC'}}}}, self.pid)
        self.assertEqual((p['player'], p['overall'], p['pace'], p['defense'], p['club']),
                         ('Test Player', 50, 60, 40, 'Current FC'))
        self.assertIsNone(p['shooting'])

    def test_league_rating_excludes_other_seasons_arena_and_friendlies(self):
        def row(name, season, avg, matches):
            return {'competition': {'name': name, 'season': {'name': season}},
                    'stats': {'matches': matches, 'averageRating': avg}}
        result = b.league_performance([row('Ice League', 'Season 18', 8, 2),
                                      row('Spark League', 'Season 18', 6, 1),
                                      row('Arena League', 'Season 18', 10, 100),
                                      row('Friendly League', 'Season 18', 10, 100),
                                      row('Ice League', 'Season 17', 10, 100)])
        self.assertEqual(result['appearances'], 3)
        self.assertAlmostEqual(result['rating'], 7.333)

    def test_unknown_competition_is_not_false_zero_or_guessed_rating(self):
        self.assertIsNone(b.league_performance([])['appearances'])
        result = b.league_performance([{'competition': {'name': 'Ice League', 'season': {'name': 'Season 18'}},
                                      'stats': {'matches': 2, 'rating': 14.5}}])
        self.assertEqual(result['appearances'], 2)
        self.assertIsNone(result['rating'])

    def test_cloudflare_is_not_reported_as_expired_token(self):
        response = Mock(status_code=403, headers={'content-type': 'text/html'}, ok=False)
        with patch.object(b.requests, 'request', return_value=response) as request:
            with self.assertRaisesRegex(b.APIError, 'security service'):
                b.Client('SECRET').get('/players/273344')
        self.assertEqual(request.call_count, 1)

    def test_rate_limit_stops_scan_and_retains_data(self):
        with patch.object(b, 'utcnow', return_value='2026-10-30T12:00:00+00:00'):
            self.store.save_profile(self.pid, self.profile)
        client = Mock()
        client.get.side_effect = b.APIError('Rate limited', stop=True)
        messages = self.store.refresh(client)
        self.assertEqual(client.get.call_count, 1)
        self.assertEqual(self.store.latest()[self.pid]['overall'], 50)
        self.assertIn('Refresh stopped', messages[-1])
        self.store.refresh(client)
        self.assertEqual(client.get.call_count, 1)


if __name__ == '__main__':
    unittest.main()
