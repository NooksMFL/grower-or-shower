import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backend as b
import top_boy as tb
import nightly


def game(cid=999999,start='2026-11-04T18:00:00Z',goals=2):
    return {'competition':{'id':cid,'name':'League','type':'LEAGUE','season':{'name':'Season 18'},'startingDate':start},
            'club':{'id':1},'stats':{'nbMatches':1,'goals':goals,'assists':1,'winsWithAppearance':1,'wins':1,'draws':0,'losses':0,'rating':8}}


class CutoffTests(unittest.TestCase):
    def test_actual_finished_preseason_cups_are_excluded_from_all_stats(self):
        seed=nightly.opening_checkpoint()
        old=[r for records in seed['records'].values() for r in records]
        self.assertTrue(old)
        self.assertTrue(all(tb.competition_kind(r) is None for r in old))
        totals=tb.player_totals(old)
        self.assertEqual((totals['appearances'],totals['goals'],totals['assists'],totals['wins']),(0,0,0,0))
        self.assertIsNone(tb.average_rating(old)['average_rating'])
    def test_only_real_post_cutoff_results_contribute(self):
        old=[r for records in nightly.opening_checkpoint()['records'].values() for r in records]
        valid=game()
        totals=tb.player_totals(old+[valid])
        self.assertEqual((totals['goals'],totals['assists'],totals['wins']),(2,1,1))
        self.assertEqual(tb.points(totals['goals'],totals['assists'],totals['wins']),14)
        self.assertEqual(tb.average_rating(old+[valid])['average_rating'],8)
    def test_finished_before_cutoff_and_straddling_aggregate(self):
        ended=game(start='2026-11-01T00:00:00Z');ended['competition']['endedAt']='2026-11-03T23:59:59Z'
        self.assertIsNone(tb.competition_kind(ended))
        mixed=game(start='2026-11-03T12:00:00Z')
        self.assertEqual(tb.competition_kind(mixed),'unknown')
        self.assertIsNone(tb.player_totals([mixed])['goals'])
    def test_old_seasons_are_not_mistaken_for_mixed_current_stats(self):
        old=game(start='2026-09-22T00:00:00Z');old['competition']['season']={'name':'Season 17'}
        self.assertIsNone(tb.competition_kind(old))
    def test_future_qualifying_cup_is_allowed_and_boundary_is_inclusive(self):
        valid=game(start=tb.SCORING_START);valid['competition'].update(type='CUP',name='New Cup')
        self.assertEqual(tb.competition_kind(valid),'cup')
    def test_excluded_cups_do_not_make_nightly_delta_pending_when_removed(self):
        before=[r for records in nightly.opening_checkpoint()['records'].values() for r in records]
        self.assertEqual(nightly.delta([],before)['points'],0)
        self.assertEqual(nightly.delta([game()],before)['points'],14)

if __name__=='__main__':unittest.main()
