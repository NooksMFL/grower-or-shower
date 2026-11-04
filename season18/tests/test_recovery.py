import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import backend as b
import browser_backup as browser


def history():
    return [{'date':'2026-10-20T12:00:00Z','values':dict.fromkeys(b.FIELDS,50)},
            {'date':'2026-11-03T10:00:00Z','values':{'pace':61}},
            {'date':'2026-11-04T00:00:00Z','values':{'overall':51,'pace':62}}]


def response(path):
    if path.endswith('/experiences/history'):return history()
    if path.endswith('/competitions'):return []
    return {'id':int(path.split('/')[-1]),'metadata':{'name':'Current player',**dict.fromkeys(b.FIELDS,65)}}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'records.sqlite3';self.store=b.Store(self.path)
    def tearDown(self):self.temp.cleanup()
    def test_partial_absolute_history_recovers_all_seven_preseason_fields(self):
        pid=b.entrants()[0]['player_id']
        self.store.save('histories',pid,history())
        self.assertTrue(self.store.recover_baseline(pid))
        baseline=self.store.baseline(pid)
        self.assertEqual(baseline['overall'],50);self.assertEqual(baseline['pace'],61)
        self.assertEqual(baseline['at'],'2026-11-03T10:00:00+00:00')
        self.assertEqual(baseline['source'],'Dated player history')
        self.store.save('histories',pid,[{'date':'2026-11-03T12:00:00Z','values':dict.fromkeys(b.FIELDS,1)}])
        self.assertFalse(self.store.recover_baseline(pid))
        self.assertEqual(self.store.baseline(pid),baseline)
    def test_incomplete_or_post_cutoff_history_never_becomes_baseline(self):
        self.assertIsNone(b.baseline_from_history([{'date':'2026-11-03','values':{'overall':50}}],b.TRAINING_START))
        self.assertIsNone(b.baseline_from_history([{'date':b.TRAINING_START,'values':dict.fromkeys(b.FIELDS,60)}],b.TRAINING_START))
    def test_legacy_two_profiles_resume_without_fifteen_minute_lock_or_refetch(self):
        ids=[e['player_id'] for e in b.entrants()]
        for pid in ids[:2]:self.store.save_profile(pid,{'player_id':pid,'player':'Saved player',**dict.fromkeys(b.FIELDS,60)})
        self.store.claim_refresh() # This is the old 15-minute lock shown in the screenshot.
        client=Mock();client.get.side_effect=response
        self.assertEqual(self.store.refresh(client,delay=0),[])
        paths=[c.args[0] for c in client.get.call_args_list]
        self.assertNotIn(f'/players/{ids[0]}',paths);self.assertNotIn(f'/players/{ids[1]}',paths)
        self.assertEqual(len(paths),34);self.assertEqual(len(self.store.latest()),12)
        self.assertEqual(self.store.refresh_state()['status'],'complete')
        self.assertTrue(all(self.store.baseline(pid)['overall']==50 for pid in ids))
        count=client.get.call_count
        self.store.refresh(client,delay=0)
        self.assertEqual(client.get.call_count,count) # 15 minutes only applies after a full completion.
    def test_interruption_checkpoint_restores_and_resumes_only_missing_requests(self):
        client=Mock();count=0
        def stop(path):
            nonlocal count
            count+=1
            if count==5:raise b.APIError('Rate limited',stop=True,retry_after=60)
            return response(path)
        client.get.side_effect=stop
        self.store.refresh(client,delay=0)
        self.assertEqual(len(self.store.latest()),2)
        state=self.store.refresh_state();self.assertEqual(len(state['done']),4)
        self.store.refresh(client,delay=0);self.assertEqual(client.get.call_count,5)
        envelope=browser.seal(self.store.backup(),'test-backup-key')
        restored=b.Store(Path(self.temp.name)/'restored.sqlite3')
        restored.restore(browser.unseal(envelope,'test-backup-key'))
        self.assertEqual(restored.refresh_state(),state)
        state['retry_until']=0;restored._save_refresh(state)
        resumed=Mock();resumed.get.side_effect=response
        self.assertEqual(restored.refresh(resumed,delay=0),[])
        self.assertEqual(resumed.get.call_count,32)
        self.assertNotIn(f'/players/{b.entrants()[0]["player_id"]}',[c.args[0] for c in resumed.get.call_args_list])
        self.assertEqual(restored.refresh_state()['status'],'complete')
        self.assertEqual(len(restored.latest()),12)
    def test_rate_limit_uses_retry_after(self):
        response=Mock(status_code=429,headers={'Retry-After':'90'},ok=False)
        with patch.object(b.requests,'request',return_value=response):
            with self.assertRaises(b.APIError) as error:b.Client().get('/players/1')
        self.assertEqual(error.exception.retry_after,90)
    def test_signed_backups_reject_tampering_and_do_not_reveal_key(self):
        raw=self.store.backup();sealed=browser.seal(raw,'test-backup-key')
        self.assertNotIn('test-backup-key',sealed)
        self.assertEqual(browser.unseal(sealed,'test-backup-key'),raw)
        obj=json.loads(sealed);obj['signature']='bad'
        with self.assertRaises(ValueError):browser.unseal(json.dumps(obj),'test-backup-key')
        with self.assertRaises(ValueError):browser.unseal(sealed,'wrong-key')
    def test_existing_refresh_checkpoint_wins_over_older_backup(self):
        self.store._save_refresh({'status':'paused','done':[],'retry_until':0})
        old=self.store.backup()
        newer={'status':'paused','done':[[b.entrants()[0]['player_id'],'profiles']],'retry_until':0}
        self.store._save_refresh(newer);self.store.restore(old)
        self.assertEqual(self.store.refresh_state(),newer)
    def test_page_recovers_saved_history_before_showing_starting_value_counts(self):
        import streamlit as st
        pid=b.entrants()[0]['player_id']
        self.store.save_profile(pid,{'player_id':pid,'player':'Player',**dict.fromkeys(b.FIELDS,65)})
        self.store.save('histories',pid,history())
        st.cache_resource.clear()
        with patch.dict(os.environ,{'COMPETITIONS_DB':str(self.path),'MFL_REFRESH_TOKEN':'','BACKUP_SIGNING_KEY':''}):
            at=AppTest.from_file(str(ROOT/'app.py')).run()
            at.button(key='open_grower').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.metric[1].value,'1 / 12');self.assertEqual(at.metric[2].value,'1 / 12')
        self.assertEqual(self.store.baseline(pid)['overall'],50)
        st.cache_resource.clear()

if __name__=='__main__':unittest.main()
