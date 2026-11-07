import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backend as b
import grower_sync as g

class GrowerScanTests(unittest.TestCase):
    def test_existing_baseline_is_preserved_even_if_history_changes(self):
        entry=b.entrants()[0];pid=entry['player_id']
        baseline={f:50 for f in b.FIELDS};baseline['at']='2026-11-03T20:00:00Z'
        previous={'players':{str(pid):{'baseline':copy.deepcopy(baseline)}}}
        profile={f:52 for f in b.FIELDS};profile['player_id']=pid
        client=Mock();client.get.side_effect=[{},[],[]]
        with patch.object(b,'entrants',return_value=[entry]),patch.object(b,'profile',return_value=profile):
            result=g.collect(client,previous,delay=0)
        self.assertEqual(result['players'][str(pid)]['baseline'],baseline)
        self.assertEqual(result['players'][str(pid)]['gains']['overall'],2)
        self.assertEqual(previous['players'][str(pid)]['baseline'],baseline)
    def test_failed_scan_retains_saved_player_and_completion_time(self):
        previous={'players':{'468523':{'baseline':{'overall':50}}},'last_complete_at':'2026-11-05T00:00:00Z'}
        client=Mock();client.get.side_effect=b.APIError('Wait',stop=True)
        result=g.collect(client,previous,delay=0)
        self.assertEqual(result['players']['468523']['baseline'],{'overall':50})
        self.assertEqual(result['last_complete_at'],previous['last_complete_at'])
        self.assertTrue(result['errors'])
    def test_missing_history_never_uses_current_stats_as_starting_values(self):
        entry=b.entrants()[0];profile={f:52 for f in b.FIELDS};profile['player_id']=entry['player_id']
        client=Mock();client.get.side_effect=[{},[],[]]
        with patch.object(b,'entrants',return_value=[entry]),patch.object(b,'profile',return_value=profile):
            result=g.collect(client,delay=0)
        row=result['players'][str(entry['player_id'])]
        self.assertNotIn('baseline',row)
        self.assertIsNone(row['gains']['overall'])
