"""Unattended Top Boy collection. Only public game records are published."""
from __future__ import annotations
import base64
import copy
import json
import os
from pathlib import Path
import time
import requests
import backend as b
import top_boy as tb
import nightly

LIVE_BRANCH='topboy-live'
LIVE_PATH='season18/live/topboy.json'
LIVE_URL='https://raw.githubusercontent.com/NooksMFL/grower-or-shower/topboy-live/'+LIVE_PATH


def fetch_previous():
    repo=os.getenv('GITHUB_REPOSITORY');token=os.getenv('GITHUB_TOKEN')
    if repo and token:
        r=requests.get('https://api.github.com/repos/'+repo+'/contents/'+LIVE_PATH,
                       params={'ref':LIVE_BRANCH},headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'},timeout=20)
        if r.status_code==404:return {}
        r.raise_for_status()
        value=json.loads(base64.b64decode(r.json()['content']))
    else:
        r=requests.get(LIVE_URL+'?tick='+str(int(time.time()//60)),timeout=20,headers={'Cache-Control':'no-cache'})
        if r.status_code==404:return {}
        r.raise_for_status();value=r.json()
    if value.get('version')!=1 or value.get('season')!=18:raise ValueError('Unrecognised prior snapshot.')
    return value


def collect(client,previous=None,delay=.4):
    result=copy.deepcopy(previous or {})
    result.update(version=1,season=18,attempted_at=b.utcnow(),errors=[])
    players=result.setdefault('players',{})
    for entry in b.entrants('top_boy'):
        pid=entry['player_id'];row=players.setdefault(str(pid),{'entrant':entry['entrant'],'player_id':pid})
        row['entrant']=entry['entrant']
        tracker=row.setdefault('win_tracker',{})
        for suffix,field in [('', 'profile'),('/competitions','records')]:
            try:
                payload=client.get(f'/players/{pid}'+suffix)
                if field=='profile':row[field]=b.profile(payload,pid)
                else:
                    records=[]
                    for record in b.rows(payload):
                        if tb.competition_kind(record) not in ('league','cup'):continue
                        stats=copy.deepcopy(record.get('stats') or {})
                        competition=record.get('competition') or {};club=record.get('club') or {}
                        clean={'competition':{k:competition[k] for k in ('id','name','type','subType','season','status','withXp') if k in competition},
                               'club':{k:club[k] for k in ('id','name') if k in club},'stats':stats}
                        identity=nightly.key(clean);tracker[identity]=nightly.credit_wins(clean,tracker.get(identity))
                        records.append(clean)
                    row[field]=records
                row[field+'_at']=b.utcnow()
            except b.APIError as exc:
                result['errors'].append({'entrant':entry['entrant'],'player_id':pid,'field':field,'message':str(exc)})
                if exc.stop:
                    result['last_error_at']=b.utcnow()
                    return result
            except ValueError:
                result['errors'].append({'entrant':entry['entrant'],'player_id':pid,'field':field,'message':'MFL returned an unsupported record format.'})
            if delay:time.sleep(delay)
    for obsolete in ('api_routes','diagnostic_feed','diagnostic_match','diagnostic_notice','diagnostic_player_feed','player_match_probe','match_endpoint_unavailable'):
        result.pop(obsolete,None)
    nightly.update(result,opening=nightly.opening_checkpoint())
    if not any(e['field'] in ('profile','records') for e in result['errors']):result['last_complete_at']=b.utcnow()
    return result


def publish(snapshot):
    repo=os.environ['GITHUB_REPOSITORY'];token=os.environ['GITHUB_TOKEN']
    session=requests.Session();session.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
    api='https://api.github.com/repos/'+repo
    ref=session.get(api+'/git/ref/heads/'+LIVE_BRANCH,timeout=20)
    if ref.status_code==404:
        created=session.post(api+'/git/refs',json={'ref':'refs/heads/'+LIVE_BRANCH,'sha':os.environ['GITHUB_SHA']},timeout=20)
        if created.status_code!=422:created.raise_for_status()
    else:ref.raise_for_status()
    existing=session.get(api+'/contents/'+LIVE_PATH,params={'ref':LIVE_BRANCH},timeout=20)
    body={'message':'Update Top Boy results '+snapshot['attempted_at'],'branch':LIVE_BRANCH,
          'content':base64.b64encode(json.dumps(snapshot,ensure_ascii=False,indent=2).encode()).decode()}
    if existing.ok:body['sha']=existing.json()['sha']
    elif existing.status_code!=404:existing.raise_for_status()
    saved=session.put(api+'/contents/'+LIVE_PATH,json=body,timeout=30);saved.raise_for_status()


def main():
    try:previous=fetch_previous()
    except (requests.RequestException,ValueError,KeyError):
        print('Previous saved Top Boy results could not be read. Publication skipped to preserve them.')
        raise SystemExit(1)
    snapshot=collect(b.Client(os.getenv('MFL_REFRESH_TOKEN','')),previous)
    Path('topboy-result.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    publish(snapshot)
    print('Top Boy snapshot published. Profiles:',sum('profile' in p for p in snapshot['players'].values()),'Notices:',len(snapshot['errors']))
    if snapshot['errors']:print('Last notice:',snapshot['errors'][0]['message'])

if __name__=='__main__':main()
