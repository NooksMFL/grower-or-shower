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


def day_leaders(preview):
    rows=preview.get('rows',[])
    if not rows or any(r.get('points') is None or r.get('appearances') is None for r in rows):return []
    active=[r for r in rows if r['appearances']>0]
    if not active:return []
    best=max(r['points'] for r in active)
    tied=[r for r in active if r['points']==best]
    if len(tied)>1:
        if any(r.get('average_rating') is None for r in tied):return []
        rating=max(r['average_rating'] for r in tied)
        tied=[r for r in tied if r['average_rating']==rating]
    return tied


def star_card_html(row,day):
    import html
    esc=lambda value:html.escape(str(value),quote=True)
    average=f"{row['average_rating']:.2f}" if row.get('average_rating') is not None else '—'
    count=row.get('appearances',0)
    appearance=f"{count} appearance"+('' if count==1 else 's')
    stats=''.join(f'<div class="star-stat"><strong>{esc(value)}</strong><span>{label}</span></div>'
                  for value,label in ((row['goals'],'GOALS'),(row['assists'],'ASSISTS'),(row['wins'],'WINS'),(average,'AVG RATING')))
    return f'''<article class="star-card" aria-label="Star of the Day: {esc(row['player'])}">
<div class="star-card-header"><span>★ STAR OF THE DAY</span><time>{esc(day)}</time></div>
<div class="star-card-main"><div class="star-portrait"><img src="https://d13e14gtps4iwl.cloudfront.net/players/v2/{int(row['player_id'])}/photo.webp" alt="{esc(row['player'])}"></div>
<div class="star-details"><div class="star-owner">{esc(row['entrant'])}</div><div class="star-player">{esc(row['player'])}</div><div class="star-apps">{appearance}</div><div class="star-points"><strong>{row['points']} POINTS</strong></div></div></div>
<div class="star-stats">{stats}</div></article>'''


def render_night(snapshot):
    import html
    import pandas as pd
    import rendering
    preview=(snapshot or {}).get('tonight',{})
    today=datetime.now(timezone.utc).date().isoformat()
    if preview.get('day')==today:
        checked=b.timestamp((snapshot or {}).get('last_complete_at'))
        stamp=checked.strftime('%H:%M GMT') if checked else 'not checked'
        st.caption('Today’s results · Final award after midnight GMT · Updated '+stamp)
        covered={r.get('player_id') for r in preview.get('rows',[])}
        expected={e['player_id'] for e in b.entrants('top_boy')}
        leaders=day_leaders(preview) if covered==expected else []
        if leaders:
            for row in leaders:
                st.html(star_card_html(row,today))
        else:st.info('No verified leader yet. Waiting for qualifying appearances or complete results.')
    nights=(snapshot or {}).get('nights',{})
    if nights:
        st.subheader('Previous winners')
        selected=st.selectbox('Date',sorted(nights,reverse=True),key='topboy_night')
        night=nights[selected]
        winners=night.get('winners',[])
        if night['status']=='complete':
            for row in night['rows']:
                if row['player_id'] not in winners:continue
                st.html(star_card_html(row,selected))
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
