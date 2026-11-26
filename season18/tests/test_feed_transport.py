import base64,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import feed_transport as transport
import topboy_sync as sync
import live_results
import grower_live

class LargeSnapshotTests(unittest.TestCase):
    def test_larger_than_one_mib_raw_snapshot_retains_checkpoints_and_awards(self):
        value={'version':1,'season':18,'players':{'1':{'records':[]}},'nights':{'2026-11-20':{'winners':[1]}},'night_checkpoints':{'2026-11-20':{'evidence':'x'*1100000}}}
        self.assertGreater(len(json.dumps(value)),1048576)
        response=Mock();response.status_code=200;response.json.return_value=value
        with patch.dict('os.environ',{'GITHUB_REPOSITORY':'owner/repo','GITHUB_TOKEN':'test'}),patch.object(sync.requests,'get',return_value=response) as get:
            loaded=sync.fetch_previous()
        self.assertEqual(loaded,value)
        self.assertEqual(get.call_args.kwargs['headers']['Accept'],transport.RAW_ACCEPT)
    def test_metadata_without_embedded_content_is_never_treated_as_empty_saved_data(self):
        with self.assertRaises(ValueError):transport.decode_snapshot({'encoding':'none','content':'','size':1100000})
    def test_legacy_embedded_snapshot_still_reads(self):
        value={'version':1,'season':18,'players':{}}
        self.assertEqual(transport.decode_snapshot({'encoding':'base64','content':base64.b64encode(json.dumps(value).encode()).decode()}),value)
    def test_both_ui_readers_accept_raw_snapshots(self):
        for module,extra in [(live_results,{}),(grower_live,{'competition':'grower'})]:
            value={'version':1,'season':18,'players':{},**extra}
            response=Mock();response.json.return_value=value
            module.direct.clear()
            with patch.object(module.requests,'get',return_value=response) as get:
                self.assertEqual(module.direct(),value)
                self.assertEqual(get.call_args.kwargs['headers']['Accept'],transport.RAW_ACCEPT)
            module.direct.clear()
