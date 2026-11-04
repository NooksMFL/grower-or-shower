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

LIVE_BRANCH='topboy-live'
LIVE_PATH='season18/live/topboy.json'
LIVE_URL='https://raw.githubusercontent.com/NooksMFL/grower-or-shower/topboy-live/'+LIVE_PATH


def fetch_previous():
    r=requests.get(LIVE_URL,timeout=20,headers={'Cache-Control':'no-cache'})
    if r.status_code==404:return {}
    r.raise_for_status()
    value=r.json()
    return value if value.get('version')==1 and value.get('season')==18 else {}


def collect(client,previous=None,delay=.4):
    result=copy.deepcopy(previous or {})
    result.update(version=1,season=18,attempted_at=b.utcnow(),errors=[])
    players=result.setdefault('players',{})
    unsupported=False
    for entry in b.entrants('top_boy'):
        pid=entry['player_id'];row=players.setdefault(str(pid),{'entrant':entry['entrant'],'player_id':pid})
        row['entrant']=entry['entrant']
        for suffix,field in [('', 'profile'),('/competitions','records'),('/matches','matches')]:
            if field=='matches' and unsupported:continue
            try:
                payload=client.get(f'/players/{pid}'+suffix)
                row[field]=b.profile(payload,pid) if field=='profile' else b.rows(payload)
                row[field+'_at']=b.utcnow()
            except b.APIError as exc:
                if field=='matches' and 'HTTP 404' in str(exc):
                    unsupported=True;result['match_endpoint_unavailable']=True
                    continue
                result['errors'].append({'entrant':entry['entrant'],'player_id':pid,'field':field,'message':str(exc)})
                if exc.stop:
                    result['last_error_at']=b.utcnow()
                    return result
            except ValueError:
                result['errors'].append({'entrant':entry['entrant'],'player_id':pid,'field':field,'message':'MFL returned an unsupported record format.'})
            if delay:time.sleep(delay)
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
    except (requests.RequestException,ValueError):previous={}
    snapshot=collect(b.Client(os.getenv('MFL_REFRESH_TOKEN','')),previous)
    Path('topboy-result.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    publish(snapshot)
    print('Top Boy snapshot published. Profiles:',sum('profile' in p for p in snapshot['players'].values()),'Notices:',len(snapshot['errors']))
    if snapshot['errors']:print('Last notice:',snapshot['errors'][0]['message'])

if __name__=='__main__':main()
