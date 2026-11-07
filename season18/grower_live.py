"""Load durable Season 18 growth scans while preserving saved starting values."""
import json
import time
import requests
import streamlit as st
import backend as b
from grower_sync import LIVE_URL


@st.cache_data(ttl=60,show_spinner=False)
def fetch():
    try:
        response=requests.get(LIVE_URL+'?tick='+str(int(time.time()//60)),timeout=(4,12))
        response.raise_for_status();value=response.json()
        if value.get('version')!=1 or value.get('season')!=18 or value.get('competition')!='grower' or not isinstance(value.get('players'),dict):return None
        return value
    except (requests.RequestException,ValueError,AttributeError):return None


def apply(store,snapshot):
    if not snapshot or snapshot.get('competition')!='grower':return 0
    allowed={e['player_id'] for e in b.entrants()};count=0
    with store.connect() as c:
        for raw,row in snapshot.get('players',{}).items():
            try:pid=int(raw)
            except (ValueError,TypeError):continue
            if pid not in allowed or not isinstance(row,dict):continue
            profile=row.get('profile');at=b.timestamp(row.get('profile_at'))
            existing=c.execute('SELECT checked_at FROM profiles WHERE player_id=?',(pid,)).fetchone()
            if at and isinstance(profile,dict) and profile.get('player_id')==pid and (not existing or at>(b.timestamp(existing[0]) or at)):
                c.execute('INSERT OR REPLACE INTO profiles VALUES(?,?,?)',(pid,json.dumps(profile),at.isoformat()));count+=1
            history=row.get('history')
            if isinstance(history,list) and all(isinstance(r,dict) for r in history):
                existing=c.execute('SELECT payload FROM histories WHERE player_id=?',(pid,)).fetchone()
                merged={json.dumps(r,sort_keys=True):r for r in ((json.loads(existing[0]) if existing else [])+history)}
                c.execute('INSERT OR REPLACE INTO histories VALUES(?,?)',(pid,json.dumps(list(merged.values()))))
            records=row.get('records');at=b.timestamp(row.get('records_at'))
            if at and isinstance(records,list) and all(isinstance(r,dict) for r in records):
                existing=c.execute('SELECT payload FROM competitions WHERE player_id=?',(pid,)).fetchone()
                previous=b.timestamp(json.loads(existing[0]).get('checked_at')) if existing else None
                if previous is None or at>previous:
                    c.execute('INSERT OR REPLACE INTO competitions VALUES(?,?)',(pid,json.dumps({'records':records,'checked_at':at.isoformat()})))
            baseline=row.get('baseline')
            if isinstance(baseline,dict):
                at=b.timestamp(baseline.get('at'))
                if at and at<b.timestamp(b.TRAINING_START) and all(b.number(baseline.get(f)) is not None and 0<=baseline[f]<=100 for f in b.FIELDS):
                    c.execute('INSERT OR IGNORE INTO baselines VALUES(?,?,?)',(pid,json.dumps({f:baseline[f] for f in b.FIELDS}),at.isoformat()))
    for pid in allowed:store.recover_baseline(pid)
    return count
