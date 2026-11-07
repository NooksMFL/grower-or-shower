"""Season 18 Grower or Shower scan; dated starting values are never replaced."""
import copy
import json
import os
import time
from pathlib import Path
import requests
import backend as b
import topboy_sync as transport

LIVE_BRANCH='grower-live'
LIVE_PATH='season18/live/grower.json'
LIVE_URL='https://raw.githubusercontent.com/NooksMFL/grower-or-shower/'+LIVE_BRANCH+'/'+LIVE_PATH


def collect(client,previous=None,delay=.5):
    result=copy.deepcopy(previous or {})
    result.update(version=1,season=18,competition='grower',attempted_at=b.utcnow(),errors=[])
    players=result.setdefault('players',{})
    for entry in b.entrants():
        pid=entry['player_id'];row=players.setdefault(str(pid),{'player_id':pid})
        row['entrant']=entry['entrant']
        for suffix,field in [('', 'profile'),('/experiences/history','history'),('/competitions','records')]:
            try:
                payload=client.get(f'/players/{pid}'+suffix)
                value=b.profile(payload,pid) if field=='profile' else b.rows(payload)
                row[field]=value;row[field+'_at']=b.utcnow()
                if field=='history' and not row.get('baseline'):
                    base=b.baseline_from_history(value,b.TRAINING_START)
                    if base:row['baseline']={**base,'source':'Dated player history'}
            except (b.APIError,ValueError) as exc:
                result['errors'].append({'entrant':entry['entrant'],'field':field,'message':str(exc)})
                if getattr(exc,'stop',False):return result
            if delay:time.sleep(delay)
        baseline=row.get('baseline');profile=row.get('profile',{})
        row['gains']={f:profile[f]-baseline[f] if baseline and profile.get(f) is not None else None for f in b.FIELDS}
    if not result['errors']:result['last_complete_at']=b.utcnow()
    return result


def main():
    # Reuse the tested GitHub transport in this separate process and branch.
    transport.LIVE_BRANCH=LIVE_BRANCH;transport.LIVE_PATH=LIVE_PATH;transport.LIVE_URL=LIVE_URL
    try:previous=transport.fetch_previous()
    except (requests.RequestException,ValueError,KeyError):
        raise SystemExit('Previous Grower data could not be read; publication skipped to preserve starting values.')
    if previous and previous.get('competition')!='grower':raise SystemExit('Wrong competition feed; no data changed.')
    snapshot=collect(b.Client(os.getenv('MFL_REFRESH_TOKEN','')),previous)
    Path('grower-result.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    transport.publish(snapshot)
    print('Grower scan saved. Players:',len(snapshot['players']),'Notices:',len(snapshot['errors']))
    for row in snapshot['players'].values():print(row['entrant'],'gains:',row.get('gains'),'baseline:',bool(row.get('baseline')))

if __name__=='__main__':main()
