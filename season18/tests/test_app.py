import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backend as b


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'ui.sqlite3')
        self.env = patch.dict(os.environ, {'COMPETITIONS_DB': self.path, 'ADMIN_PASSWORD': '', 'SCORING_CONFIRMED': 'false'})
        self.env.start()
        import streamlit as st
        st.cache_resource.clear()

    def tearDown(self):
        import streamlit as st
        st.cache_resource.clear()
        self.env.stop()
        self.tmp.cleanup()

    def test_empty_app_renders_all_entries_without_network(self):
        with patch.object(b.requests, 'request') as request:
            at = AppTest.from_file(str(ROOT / 'app.py')).run()
        self.assertEqual(list(at.exception), [])
        self.assertEqual(at.metric[0].value, '11')
        self.assertEqual(at.metric[2].value, '0 / 11')
        self.assertEqual(len(at.dataframe[0].value), 11)
        self.assertFalse(request.called)

    def test_top_boy_is_empty_and_separate(self):
        at = AppTest.from_file(str(ROOT / 'app.py')).run()
        at.get('button_group')[0].set_value(['Top Boy']).run()
        self.assertEqual(list(at.exception), [])
        self.assertEqual(len(at.dataframe), 0)
        self.assertIn('Entrants coming next', at.info[0].value)

    def test_loaded_players_show_baselines_and_gains(self):
        store = b.Store(self.path)
        for entry in b.entrants():
            p = {'player_id': entry['player_id'], 'player': entry['entrant'] + ' Player',
                 'positions': 'CF', 'age': 20, 'club': 'Test Club', 'club_known': True,
                 **dict.fromkeys(b.FIELDS, 50)}
            with patch.object(b, 'utcnow', return_value='2026-10-30T12:00:00+00:00'):
                store.save_profile(entry['player_id'], p)
            with patch.object(b, 'utcnow', return_value='2026-11-05T12:00:00+00:00'):
                store.save_profile(entry['player_id'], {**p, 'overall': 52, 'shooting': 54})
        at = AppTest.from_file(str(ROOT / 'app.py')).run()
        self.assertEqual(list(at.exception), [])
        self.assertEqual(at.metric[2].value, '11 / 11')
        self.assertTrue((at.dataframe[1].value['OVR gain'] == 2).all())
        self.assertTrue((at.dataframe[1].value['Attribute gain'] == 4).all())


if __name__ == '__main__':
    unittest.main()
