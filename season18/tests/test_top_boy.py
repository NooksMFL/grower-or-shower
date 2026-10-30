import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backend as b
import top_boy as tb


def fixture(name='Spark League', season='Season 18', goals=2, assists=3, wins=2, apps=4):
    return {'competition': {'id': name, 'name': name, 'season': {'name': season}},
            'stats': {'goals': goals, 'assists': assists, 'appearanceWins': wins, 'matches': apps}}


class TopBoyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = b.Store(Path(self.tmp.name) / 'competitions.sqlite3')

    def tearDown(self):
        self.tmp.cleanup()

    def test_nine_exact_entries(self):
        self.assertEqual({e['entrant']: e['player_id'] for e in b.entrants('top_boy')}, {
            'Ricky': 35005, 'Hawkeye': 384642, 'Minty': 350909, 'iKenny': 152098,
            'Nooks': 412176, 'Krystian': 236834, 'Rhythm': 110469, 'ClarkyIsland': 53882, 'hcy': 316875})

    def test_league_plus_cup_excludes_arena_friendlies_and_past_season(self):
        totals = tb.player_totals([fixture(), fixture('Aspirants Cup'), fixture('Spark League', 'Season 17'),
                                   fixture('Arena League'), fixture('Friendly Cup'), fixture('Pre-season Cup')])
        self.assertEqual((totals['goals'], totals['assists'], totals['wins'], totals['appearances']), (4, 6, 4, 8))
        self.assertEqual(tb.points(totals['goals'], totals['assists'], totals['wins']), 42)

    def test_generic_team_wins_never_become_appearance_points(self):
        row = fixture()
        row['stats'].pop('appearanceWins')
        row['stats'].update({'wins': 20, 'teamWins': 20})
        totals = tb.player_totals([row])
        self.assertEqual(totals['goals'], 2)
        self.assertIsNone(totals['wins'])
        self.assertIsNone(tb.points(totals['goals'], totals['assists'], totals['wins']))

    def test_wins_cannot_exceed_appearances(self):
        self.assertIsNone(tb.player_totals([fixture(wins=5, apps=4)])['wins'])

    def test_partial_competition_cannot_silently_undercount(self):
        cup = fixture('Aspirants Cup')
        cup['stats'].pop('assists')
        totals = tb.player_totals([fixture(), cup])
        self.assertEqual(totals['goals'], 4)
        self.assertIsNone(totals['assists'])

    def test_unknown_season_or_competition_does_not_become_zero(self):
        self.assertIsNone(tb.player_totals([{'competition': {'name': 'Spark League'}, 'stats': {}}])['goals'])
        self.assertIsNone(tb.player_totals([fixture('Unknown Format')])['goals'])
        self.assertEqual(tb.player_totals([])['goals'], 0)

    def test_zero_and_missing_are_different(self):
        self.assertEqual(tb.points(0, 0, 0), 0)
        self.assertEqual(tb.points(2, 3, 4), 23)
        self.assertIsNone(tb.points(2, 3, None))
        self.assertIsNone(tb.points(-1, 3, 0))
        self.assertIsNone(tb.points(True, 3, 0))

    def test_duplicate_payload_not_counted_twice(self):
        row = fixture()
        self.assertEqual(tb.player_totals([row, row])['goals'], 2)

    def review(self, pid, goals, assists=0, wins=0, league='Spark', rating=68, oop=False):
        tb.save(self.store, 'topboy_reviews', pid, {'league': league, 'entry_rating': rating, 'oop': oop,
                'manual_totals': {'goals': goals, 'assists': assists, 'wins': wins}, 'note': 'Checked league and cup appearance records.'})

    def test_tied_points_share_position_no_invented_tiebreak(self):
        self.review(35005, 1)
        self.review(384642, 0, 1, 2)
        self.review(350909, 0)
        rows = {r['player_id']: r for r in tb.leaderboard(self.store)}
        self.assertEqual(rows[35005]['position'], 1)
        self.assertEqual(rows[384642]['position'], 1)
        self.assertEqual(rows[350909]['position'], 3)
        self.assertIsNone(rows[152098]['position'])

    def test_oop_effective_rating_checks_cap_not_current_ovr(self):
        tb.save(self.store, 'topboy_profiles', 35005, {'player_id': 35005, 'player': 'Example', 'overall': 80})
        self.review(35005, 1, league='Flint', rating=62, oop=True)
        row = next(r for r in tb.leaderboard(self.store) if r['player_id'] == 35005)
        self.assertEqual(row['eligibility'], 'Within cap')
        self.review(35005, 1, league='Flint', rating=63, oop=True)
        row = next(r for r in tb.leaderboard(self.store) if r['player_id'] == 35005)
        self.assertEqual(row['eligibility'], 'Over cap')
        self.assertIsNone(row['position'])

    def test_manual_values_need_evidence_and_all_totals(self):
        with self.assertRaises(ValueError):
            tb.validate_review({'manual_totals': {'goals': 1, 'assists': 0, 'wins': None}, 'note': 'checked'})
        with self.assertRaises(ValueError):
            tb.validate_review({'manual_totals': {'goals': 1, 'assists': 0, 'wins': 0}, 'note': ''})

    def test_refresh_does_not_touch_grower_profiles_or_baselines_or_reviews(self):
        self.review(35005, 1)
        with patch.object(b, 'utcnow', return_value='2026-10-30T12:00:00+00:00'):
            self.store.save_profile(337204, {'player_id': 337204, **dict.fromkeys(b.FIELDS, 50)})
        before = self.store.baseline(337204)
        client = Mock()
        client.get.side_effect = lambda path: [fixture()] if path.endswith('competitions') else {'metadata': {'firstName': 'Real', 'overall': 70}}
        messages = tb.refresh(self.store, client)
        self.assertEqual(messages, [])
        self.assertEqual(client.get.call_count, 18)
        self.assertEqual(len(tb.records(self.store, 'topboy_profiles')), 9)
        self.assertEqual(self.store.baseline(337204), before)
        self.assertEqual(len(self.store.latest()), 1)
        row = next(r for r in tb.leaderboard(self.store) if r['player_id'] == 35005)
        self.assertEqual(row['points'], 5)
        self.assertEqual(row['source'], 'Organiser-verified totals')

    def test_rate_limit_retains_old_data_and_stops_calls(self):
        self.review(35005, 1)
        client = Mock()
        client.get.side_effect = b.APIError('Rate limited', stop=True)
        self.assertIn('Refresh stopped', tb.refresh(self.store, client)[-1])
        self.assertEqual(client.get.call_count, 1)
        self.assertEqual(len(tb.records(self.store, 'topboy_reviews')), 1)
        tb.refresh(self.store, client)
        self.assertEqual(client.get.call_count, 1)

    def test_combined_backup_roundtrip_and_old_backup_compatible(self):
        self.review(35005, 2)
        tb.save(self.store, 'topboy_profiles', 35005, {'player_id': 35005, 'player': 'Test'})
        tb.save(self.store, 'topboy_competitions', 35005, {'records': [fixture()]})
        backup = self.store.backup()
        restored = b.Store(Path(self.tmp.name) / 'restored.sqlite3')
        restored.restore(backup)
        row = next(r for r in tb.leaderboard(restored) if r['player_id'] == 35005)
        self.assertEqual(row['points'], 10)
        self.assertEqual(row['player'], 'Test')
        old = json.loads(backup)
        for table in b.TOPBOY_TABLES:
            old['tables'].pop(table)
        restored.restore(json.dumps(old))
        self.assertEqual(len(tb.records(restored, 'topboy_reviews')), 1)


if __name__ == '__main__':
    unittest.main()
