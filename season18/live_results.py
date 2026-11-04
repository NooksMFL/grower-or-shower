"""Read the public Top Boy scheduler feed without modifying Grower data."""
import json
import time
from datetime import datetime,timezone,timedelta
from zoneinfo import ZoneInfo
import requests
import streamlit as st
import backend as b
from topboy_sync import LIVE_URL


@st.cache_data(ttl=45,show_spinner=False)
def fetch():
    try:
        r=requests.get(LIVE_URL+'?tick='+str(int(time.time()//60)),headers={'Cache-Control':'no-cache'},timeout=(4,12))
        if not r.ok:return None
        value=r.json()
        if value.get('version')!=1 or value.get('season')!=18 or not isinstance(value.get('players'),dict):return None
        return value
    except (requests.RequestException,ValueError,AttributeError):return None


def apply(store,snapshot):
    allowed={e['player_id'] for e in b.entrants('top_boy')}
    if not snapshot:return 0
    count=0
    with store.connect() as c:
        for pid,row in snapshot['players'].items():
            try:pid=int(pid)
            except (ValueError,TypeError):continue
            if pid not in allowed or not isinstance(row,dict):continue
            for field,table in [('profile','topboy_profiles'),('records','topboy_competitions')]:
                at=b.timestamp(row.get(field+'_at'))
                if at is None or field not in row:continue
                payload=row[field]
                if field=='profile':
                    if not isinstance(payload,dict) or payload.get('player_id')!=pid:continue
                else:
                    if not isinstance(payload,list) or not all(isinstance(r,dict) for r in payload):continue
                    payload={'records':payload}
                existing=c.execute(f'SELECT checked_at FROM {table} WHERE player_id=?',(pid,)).fetchone()
                if existing and b.timestamp(existing[0]) and b.timestamp(existing[0])>=at:continue
                c.execute(f'INSERT OR REPLACE INTO {table} VALUES(?,?,?)',(pid,json.dumps(payload),at.isoformat()));count+=1
    return count


def scan_delayed(last_complete,now=None):
    now=now or datetime.now(timezone.utc)
    # Allow the host 30 minutes to start and finish a scheduled scan.
    due=[(now-timedelta(days=d)).replace(hour=h,minute=0,second=0,microsecond=0)
         for d in (0,1) for h in (0,19,20,21,22)]
    expected=max(t for t in due if t<=now-timedelta(minutes=30))
    return last_complete<expected


def status(snapshot):
    if not snapshot:
        st.caption('Automatic Top Boy results are waiting for the first scheduled scan. Manual refresh remains available.')
        return
    at=b.timestamp(snapshot.get('last_complete_at'))
    attempt=b.timestamp(snapshot.get('attempted_at'))
    stamp=(at or attempt)
    label=stamp.astimezone(timezone.utc).strftime('%d %b, %H:%M') if stamp else 'not checked'
    if snapshot.get('errors'):
        st.warning('Automatic scan has notices. Previously saved results remain available.')
        with st.expander('Automatic scan details'):
            for error in snapshot['errors']:st.write(error['entrant']+': '+error['message'])
    elif at and scan_delayed(at):
        st.warning('The scheduled results are delayed. Last full check: '+label+' GMT.')
    st.caption('Updates at 19:00, 20:00, 21:00 and 22:00 GMT · Star of the Day at midnight GMT · Last full check: '+label+' GMT. Scheduled runs can be delayed by the host.')


def render_night(snapshot):
    import html
    import pandas as pd
    import rendering
    st.subheader('Star of the Day')
    st.caption('Midnight GMT scan · League + cup · 5 per goal, 3 per assist, 1 per win with an appearance. Nightly checkpoint changes determine the result; ties use the night’s average rating.')
    nights=(snapshot or {}).get('nights',{})
    if nights:
        selected=st.selectbox('Match night',sorted(nights,reverse=True),key='topboy_night')
        night=nights[selected]
        winners=night.get('winners',[])
        if night['status']=='complete':
            for row in night['rows']:
                if row['player_id'] not in winners:continue
                esc=lambda v:html.escape(str(v))
                average=f"{row['average_rating']:.2f}" if row['average_rating'] is not None else '—'
                st.html(f'<div style="background:white;border:3px solid #101014;border-top:8px solid #ff008b;border-radius:12px;padding:24px;display:flex;gap:24px;align-items:center"><img src="https://d13e14gtps4iwl.cloudfront.net/players/v2/{row["player_id"]}/photo.webp" alt="" style="width:160px;height:200px;object-fit:contain"><div><strong style="color:#b00063">{esc(row["entrant"])} · {esc(selected)}</strong><h2>{esc(row["player"])}</h2><p><strong>{row["points"]} POINTS</strong> · {row["goals"]} goals · {row["assists"]} assists · {row["wins"]} wins · {average} AVG</p></div></div>')
            if len(winners)>1:st.caption('Joint winners: points and average rating are tied.')
        elif night['status']=='no_matches':st.info('No qualifying player appearances on this date.')
        else:st.info('Selection pending: the full night’s match evidence is not available yet. No winner has been guessed.')
        rows=night.get('rows',[])
    else:
        st.info('The first Star of the Day is selected after the midnight GMT scan. It compares that night’s league and cup performance between saved checkpoints.')
        rows=(snapshot or {}).get('tonight',{}).get('rows',[])
        if rows:st.subheader('Tonight so far')
    if rows:
        table=pd.DataFrame([{'Entrant':r['entrant'],'Player':r['player'],'Pld':r['appearances'],'Goals':r['goals'],
            'Assists':r['assists'],'Wins':r['wins'],'Points':r['points'],'AVG':r['average_rating']} for r in rows])
        rendering.table(table)
