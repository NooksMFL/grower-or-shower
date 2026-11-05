import copy
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backend as b
import top_boy as tb
import nightly
import topboy_sync as sync
import live_results


def record(apps=1,goals=1,assists=0,wins=1,draws=0,losses=0,rating=8):
    return {'competition':{'id':1,'name':'Flint League','type':'LEAGUE','season':{'name':'Season 18'}},'club':{'id':1},
            'stats':{'nbMatches':apps,'goals':goals,'assists':assists,'wins':wins,'draws':draws,'losses':losses,'rating':rating}}


def snap(when='2026-11-04T18:00:00+00:00',game=None):
    return {'version':1,'season':18,'attempted_at':when,'players':{str(e['player_id']):{'profile':{'player_id':e['player_id'],'player':e['entrant']},'records':copy.deepcopy([game] if game else []),'records_at':when} for e in b.entrants('top_boy')}}

class LiveTests(unittest.TestCase):
    def test_delay_warning_respects_evening_and_midnight_schedule(self):
        stamp=lambda s:datetime.fromisoformat(s+'+00:00')
        self.assertFalse(live_results.scan_delayed(stamp('2026-11-05T00:03:00'),stamp('2026-11-05T18:59:00')))
        self.assertFalse(live_results.scan_delayed(stamp('2026-11-04T22:03:00'),stamp('2026-11-05T00:10:00')))
        self.assertTrue(live_results.scan_delayed(stamp('2026-11-04T19:43:00'),stamp('2026-11-04T21:23:00')))

    def test_scheduled_retries_only_collect_unfinished_hourly_slot(self):
        now=datetime(2026,11,5,20,40,tzinfo=timezone.utc)
        self.assertTrue(sync.schedule_due({'last_complete_at':'2026-11-05T02:02:00Z'},now))
        self.assertFalse(sync.schedule_due({'last_complete_at':'2026-11-05T20:03:00Z'},now))
        self.assertTrue(sync.schedule_due({'last_complete_at':'2026-11-05T19:43:00Z'},now))
        late=datetime(2026,11,5,23,40,tzinfo=timezone.utc)
        self.assertFalse(sync.schedule_due({'last_complete_at':'2026-11-05T22:03:00Z'},late))
        midnight=datetime(2026,11,6,0,20,tzinfo=timezone.utc)
        self.assertTrue(sync.schedule_due({'last_complete_at':'2026-11-05T22:03:00Z'},midnight))
        self.assertFalse(sync.schedule_due({'last_complete_at':'2026-11-06T00:03:00Z'},midnight))

    def test_live_day_leader_uses_daily_points_and_rating_without_guessing(self):
        a=dict(player_id=1,appearances=1,points=16,average_rating=8.75)
        b=dict(player_id=2,appearances=1,points=14,average_rating=9.0)
        self.assertEqual(live_results.day_leaders({'rows':[a,b]}),[a])
        b.update(points=16,average_rating=9.0)
        self.assertEqual(live_results.day_leaders({'rows':[a,b]}),[b])
        b['average_rating']=8.75
        self.assertEqual(live_results.day_leaders({'rows':[a,b]}),[a,b])
        b['points']=None
        self.assertEqual(live_results.day_leaders({'rows':[a,b]}),[])

    def test_rank_movement_uses_shared_positions_and_rejects_incomplete_scores(self):
        def verified(**kw):
            row=record(**kw);row['stats']['winsWithAppearance']=row['stats']['wins'];return row
        before=snap(game=verified(goals=0,assists=0,wins=0,losses=1))
        ids=list(before['players'])
        before['players'][ids[0]]['records']=[verified(goals=3)]
        before['players'][ids[1]]['records']=[verified(goals=2)]
        old=sync.rank_positions(before)
        after=copy.deepcopy(before)
        after['players'][ids[1]]['records']=[verified(goals=4)]
        current=sync.rank_positions(after)
        self.assertEqual(old[ids[1]]-current[ids[1]],1)
        self.assertEqual(old[ids[0]]-current[ids[0]],-1)
        self.assertEqual(current[ids[2]],3)
        self.assertEqual(current[ids[3]],3)
        del after['players'][ids[3]]['records']
        self.assertEqual(sync.rank_positions(after),{})

    def test_win_credit_excludes_missed_team_matches(self):
        first=record();state=nightly.credit_wins(first)
        self.assertEqual(first['stats']['winsWithAppearance'],1)
        missed=record(apps=1,goals=1,wins=2,rating=8)
        state=nightly.credit_wins(missed,state)
        self.assertEqual(missed['stats']['winsWithAppearance'],1)
        next_game=record(apps=2,goals=2,wins=3,rating=16)
        state=nightly.credit_wins(next_game,state)
        self.assertEqual(next_game['stats']['winsWithAppearance'],2)
        ambiguous=record(apps=1,wins=2)
        nightly.credit_wins(ambiguous)
        self.assertNotIn('winsWithAppearance',ambiguous['stats'])
    def test_nightly_delta_uses_points_and_nightly_rating(self):
        before=record(apps=3,goals=10,assists=4,wins=3,rating=24)
        after=record(apps=4,goals=12,assists=5,wins=4,rating=33)
        result=nightly.delta([after],[before])
        self.assertEqual((result['points'],result['goals'],result['assists'],result['wins'],result['average_rating']),(14,2,1,1,9))
        missed=record(apps=3,goals=10,assists=4,wins=4,rating=24)
        self.assertEqual(nightly.delta([missed],[before])['points'],0)
    def test_ambiguous_wins_and_stat_corrections_remain_pending(self):
        self.assertIsNone(nightly.delta([record(apps=1,wins=2)],[]))
        self.assertIsNone(nightly.delta([record(goals=0)],[record(goals=2)]))
    def test_midnight_selects_only_the_closed_night(self):
        initial=snap();nightly.update(initial,datetime(2026,11,4,18,tzinfo=timezone.utc))
        self.assertEqual(initial['nights'],{})
        current=snap('2026-11-05T00:01:00+00:00',record(goals=0,wins=0,draws=1,rating=7))
        current['night_checkpoints']=copy.deepcopy(initial['night_checkpoints'])
        pid=str(b.entrants('top_boy')[0]['player_id'])
        current['players'][pid]['records']=[record(goals=2,wins=1,rating=9)]
        nightly.update(current,datetime(2026,11,5,0,1,tzinfo=timezone.utc))
        award=current['nights']['2026-11-04']
        self.assertEqual(award['status'],'complete');self.assertEqual(award['winners'],[int(pid)])
        self.assertEqual(award['rows'][0]['points'],11)
        frozen=copy.deepcopy(award)
        current['attempted_at']='2026-11-05T22:00:00+00:00'
        for row in current['players'].values():row['records_at']=current['attempted_at'];row['records']=[record(apps=2,goals=9,wins=2,rating=18)]
        nightly.update(current,datetime(2026,11,5,22,tzinfo=timezone.utc))
        self.assertEqual(current['nights']['2026-11-04'],frozen)
    def test_rating_breaks_a_points_tie_and_exact_ties_are_shared(self):
        initial=snap();nightly.update(initial,datetime(2026,11,4,18,tzinfo=timezone.utc))
        current=snap('2026-11-05T00:01:00+00:00',record())
        current['night_checkpoints']=initial['night_checkpoints']
        ids=list(current['players'])
        current['players'][ids[0]]['records'][0]['stats']['rating']=9
        nightly.update(current,datetime(2026,11,5,0,1,tzinfo=timezone.utc))
        self.assertEqual(current['nights']['2026-11-04']['winners'],[int(ids[0])])
    def test_exact_points_and_rating_ties_share_the_award(self):
        initial=snap();nightly.update(initial,datetime(2026,11,4,18,tzinfo=timezone.utc))
        current=snap('2026-11-05T00:01:00+00:00',record())
        current['night_checkpoints']=initial['night_checkpoints']
        nightly.update(current,datetime(2026,11,5,0,1,tzinfo=timezone.utc))
        self.assertEqual(len(current['nights']['2026-11-04']['winners']),len(b.entrants('top_boy')))
    def test_previous_snapshot_read_failure_never_overwrites_saved_results(self):
        with patch.object(sync,'fetch_previous',side_effect=ValueError('Unavailable')),patch.object(sync,'publish') as publish:
            with self.assertRaises(SystemExit):sync.main()
        publish.assert_not_called()

    def test_preexisting_season18_cup_stats_are_not_tonights_goals(self):
        old=record(apps=3,goals=4,wins=1,losses=2,rating=23)
        initial=snap(game=old)
        opening={'at':'2026-11-04T18:43:00+00:00','records':{pid:copy.deepcopy(row['records']) for pid,row in initial['players'].items()},'source':'Verified pre-match Top Boy scan'}
        nightly.update(initial,datetime(2026,11,4,19,tzinfo=timezone.utc),opening=opening)
        current=snap('2026-11-05T00:01:00+00:00',record(apps=4,goals=6,wins=2,losses=2,rating=32))
        current['night_checkpoints']=initial['night_checkpoints']
        nightly.update(current,datetime(2026,11,5,0,1,tzinfo=timezone.utc),opening=opening)
        row=current['nights']['2026-11-04']['rows'][0]
        self.assertEqual((row['goals'],row['points'],row['average_rating']),(2,11,9))

    def test_gmt_day_bounds_stay_fixed_all_year(self):
        self.assertEqual(nightly.bounds('2026-11-04')[0].hour,0)
        self.assertEqual(nightly.bounds('2027-07-01')[0].hour,0)
        self.assertEqual(nightly.bounds('2027-07-01')[0].day,1)
    def test_live_import_keeps_grower_baselines_and_reviews(self):
        with tempfile.TemporaryDirectory() as temp:
            store=b.Store(Path(temp)/'data.db');pid=b.entrants()[0]['player_id']
            with patch.object(b,'utcnow',return_value='2026-11-03T12:00:00Z'):
                store.save_profile(pid,{'player_id':pid,**dict.fromkeys(b.FIELDS,50)})
            tb.save(store,'topboy_reviews',35005,{'league':'Stone','entry_rating':77})
            before=store.baseline(pid)
            snapshot=snap()
            for row in snapshot['players'].values():row['profile_at']='2026-11-04T18:00:00Z'
            self.assertEqual(live_results.apply(store,snapshot),34)
            self.assertEqual(store.baseline(pid),before)
            self.assertEqual(tb.records(store,'topboy_reviews')[35005]['entry_rating'],77)
    def test_collector_retains_previous_data_when_rate_limited(self):
        previous=snap();previous['players']['35005']['records_at']='2026-11-04T10:00:00Z'
        client=Mock();client.get.side_effect=b.APIError('Wait',stop=True)
        result=sync.collect(client,previous,delay=0)
        self.assertEqual(result['players']['35005']['records_at'],'2026-11-04T10:00:00Z')
        self.assertTrue(result['errors']);self.assertEqual(client.get.call_count,1)

if __name__=='__main__':unittest.main()

class NightPageTests(unittest.TestCase):
    def test_star_tab_renders_winner_with_live_data_without_touching_grower(self):
        import os
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        first=snap();nightly.update(first,datetime(2026,11,4,18,tzinfo=timezone.utc))
        snapshot=snap('2026-11-05T00:01:00+00:00',record())
        snapshot['night_checkpoints']=first['night_checkpoints']
        snapshot['players']['35005']['records']=[record(goals=2,rating=9)]
        for row in snapshot['players'].values():row['profile_at']='2026-11-05T00:01:00Z'
        nightly.update(snapshot,datetime(2026,11,5,0,1,tzinfo=timezone.utc))
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'COMPETITIONS_DB':str(Path(temp)/'test.db')}),patch.object(live_results,'fetch',return_value=snapshot):
            st.cache_resource.clear()
            at=AppTest.from_file(str(Path(b.__file__).with_name('app.py'))).run()
            at.button(key='open_topboy').click().run()
            self.assertFalse(at.exception)
            self.assertTrue(any(t.label=='Star of the Day' for t in at.tabs))
            self.assertTrue(any('11 POINTS' in e.proto.body for e in at.get('html')))
            self.assertEqual(b.Store(Path(temp)/'test.db').latest(),{})
            st.cache_resource.clear()
