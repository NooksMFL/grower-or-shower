"""Top Boy nightly awards from dated, completed player-stat checkpoints."""
from __future__ import annotations
import copy
import json
from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
import backend as b
import top_boy as tb
UK=timezone.utc


def bounds(day):
    day=date.fromisoformat(day) if isinstance(day,str) else day
    return datetime.combine(day,time.min,UK).astimezone(timezone.utc),datetime.combine(day+timedelta(days=1),time.min,UK).astimezone(timezone.utc)


def key(row):
    return str((row.get('competition') or {}).get('id'))+':'+str((row.get('club') or {}).get('id'))


def outcomes(stats):
    values=[tb.count(stats.get(k)) for k in ('wins','draws','losses')]
    return values if all(v is not None for v in values) else None


def apps(stats):
    return next((tb.count(stats[k]) for k in ('nbMatches','matches','appearances') if k in stats),None)


def credit_wins(row,previous=None):
    """Only credit wins when the player appeared in every match in the interval.

    MFL's raw win/draw/loss totals can cover more club games than nbMatches.
    Tracking each interval allows a missed team match to award zero win points.
    """
    stats=row['stats'];n=apps(stats);out=outcomes(stats)
    state={'stats':copy.deepcopy(stats),'covered_apps':0,'wins':0,'verified':False}
    if n is None:return state
    if n==0:state.update(verified=True);stats['winsWithAppearance']=0;return state
    if out and sum(out)==n:
        state.update(covered_apps=n,wins=out[0],verified=True)
    elif previous:
        old=previous['stats'];old_n=apps(old);old_out=outcomes(old)
        if old_n is not None and out and old_out:
            delta_n=n-old_n;delta=[v-u for v,u in zip(out,old_out)]
            if delta_n>=0 and all(v>=0 for v in delta):
                covered=previous['covered_apps'];wins=previous['wins']
                if delta_n==0:pass # The player missed any team matches in this interval.
                elif sum(delta)==delta_n:covered+=delta_n;wins+=delta[0]
                state.update(covered_apps=covered,wins=wins,verified=covered==n)
    if state['verified']:stats['winsWithAppearance']=state['wins']
    return state


def rating_sum(stats):
    n=apps(stats)
    if n==0:return 0.0
    if n is None:return None
    for field in ('totalRating','ratingTotal','ratingSum'):
        value=b.number(stats.get(field))
        if value is not None and 0<=value<=10*n:return value
    for field in ('averageRating','avgRating'):
        value=b.number(stats.get(field))
        if value is not None and 0<=value<=10:return value*n
    value=b.number(stats.get('rating'))
    if value is not None and (n==1 or value>10) and 0<=value<=10*n:return value
    return None


def delta(current,baseline):
    old={key(r):r for r in baseline};seen={};totals={'appearances':0,'goals':0,'assists':0,'wins':0};ratings=0.0;rating_known=True
    for row in current:
        if tb.competition_kind(row)=='unknown':return None
        if tb.competition_kind(row) not in ('league','cup'):continue
        if key(row) in seen:
            if seen[key(row)]!=row:return None
            continue
        seen[key(row)]=row
        stats=row.get('stats') or {};prior=old.get(key(row),{}).get('stats') or {'nbMatches':0,'goals':0,'assists':0,'wins':0,'draws':0,'losses':0}
        n=apps(stats);before=apps(prior)
        if n is None or before is None or n<before:return None
        dn=n-before
        if n==0 and before==0:continue
        values={f:tb.count(stats.get(f)) for f in ('goals','assists')};prev={f:tb.count(prior.get(f)) for f in ('goals','assists')}
        if any(values[f] is None or prev[f] is None or values[f]<prev[f] for f in values):return None
        if dn==0:
            if any(values[f]!=prev[f] for f in values):return None
            continue
        out=outcomes(stats);old_out=outcomes(prior)
        if not out or not old_out:return None
        changes=[v-u for v,u in zip(out,old_out)]
        if min(changes)<0 or sum(changes)!=dn:return None
        totals['appearances']+=dn;totals['wins']+=changes[0]
        for field in values:totals[field]+=values[field]-prev[field]
        current_rating=rating_sum(stats);old_rating=rating_sum(prior)
        if current_rating is None or old_rating is None or not 0<=current_rating-old_rating<=10*dn:rating_known=False
        else:ratings+=current_rating-old_rating
    # A disappearing competition row is a correction, not a zero-performance night.
    current_keys={key(r) for r in current}
    if any(tb.competition_kind(r) in ('league','cup') and key(r) not in current_keys and (apps(r.get('stats') or {}) or 0)>0 for r in baseline):return None
    totals['average_rating']=round(ratings/totals['appearances'],3) if rating_known and totals['appearances'] else None
    totals['points']=5*totals['goals']+3*totals['assists']+totals['wins']
    return totals


def opening_checkpoint():
    path=b.ROOT/'opening_night.json'
    return json.loads(path.read_text()) if path.exists() else None


def update(snapshot,now=None,opening=None):
    now=now or datetime.now(timezone.utc);today=now.astimezone(UK).date().isoformat()
    entries=b.entrants('top_boy');players=snapshot['players'];anchors=snapshot.setdefault('night_checkpoints',{})
    current={str(e['player_id']):copy.deepcopy(players.get(str(e['player_id']),{}).get('records',[])) for e in entries}
    checked=all(players.get(str(e['player_id']),{}).get('records_at','')>=snapshot['attempted_at'] for e in entries)
    if not checked:return snapshot
    if opening and '2026-11-04' in anchors and anchors['2026-11-04'].get('source')=='Season 18 opening day' and not (snapshot.get('nights') or {}).get('2026-11-04'):
        anchors['2026-11-04']=copy.deepcopy(opening)
    if not anchors:
        # Season 18's first day has a verified zero starting point. Later first
        # installs cannot reconstruct a missed midnight checkpoint by guessing.
        first='2026-11-04'
        if today==first:anchors[first]=copy.deepcopy(opening) if opening else {'at':now.isoformat(),'records':current,'source':'First observed checkpoint'}
        else:anchors[today]={'at':now.isoformat(),'records':current,'source':'First observed checkpoint'}
    nights=snapshot.setdefault('nights',{})
    yesterday=(date.fromisoformat(today)-timedelta(days=1)).isoformat()
    prior_days=[d for d in anchors if d==yesterday and (nights.get(d) or {}).get('status') not in ('complete','no_matches')]
    end_records=anchors.get(today,{}).get('records',current)
    end_at=anchors.get(today,{}).get('at',now.isoformat())
    for day in sorted(prior_days):
        baseline=anchors[day];rows=[];missing=[]
        for entry in entries:
            pid=str(entry['player_id']);value=delta(end_records[pid],baseline['records'].get(pid,[]))
            if value is None:missing.append(entry['entrant']);continue
            rows.append({**entry,'player':players[pid].get('profile',{}).get('player',f'Player #{pid}'),**value})
        rows.sort(key=lambda r:(-r['points'],-(r['average_rating'] if r['average_rating'] is not None else -1),r['entrant'].casefold()))
        report={'day':day,'checked_at':now.isoformat(),'period_start':baseline['at'],'period_end':end_at,
                'source':'Scheduled player-stat checkpoint comparison','rows':rows,'winners':[],'missing':missing,'status':'pending'}
        if not missing:
            active=[r for r in rows if r['appearances']]
            if not active:report['status']='no_matches'
            else:
                tied=[r for r in active if r['points']==active[0]['points']]
                if len(tied)>1 and any(r['average_rating'] is None for r in tied):report['status']='tie_pending'
                else:
                    if len(tied)>1:
                        best=max(r['average_rating'] for r in tied);tied=[r for r in tied if r['average_rating']==best]
                    report.update(status='complete',winners=[r['player_id'] for r in tied])
        nights[day]=report
    if today not in anchors:anchors[today]={'at':now.isoformat(),'records':current,'source':'Midnight GMT scan'}
    preview=[]
    for entry in entries:
        pid=str(entry['player_id']);value=delta(current[pid],anchors[today]['records'].get(pid,[]))
        if value is None:value=dict.fromkeys(('appearances','goals','assists','wins','points','average_rating'))
        preview.append({**entry,'player':players[pid].get('profile',{}).get('player',f'Player #{pid}'),**value})
    snapshot['tonight']={'day':today,'rows':preview}
    # Keep a small durable history, avoiding unbounded publication sizes.
    snapshot['night_checkpoints']={d:anchors[d] for d in sorted(anchors)[-35:]}
    return snapshot
