"""Read-only public roster and market snapshot; no listings or messages are created."""
import json,time,os
from datetime import datetime,timezone
from pathlib import Path
import requests
BASE='https://api.playmfl.com'
HEADERS={'Accept':'application/json','Origin':'https://app.playmfl.com','Referer':'https://app.playmfl.com/','User-Agent':'Mozilla/5.0'}
SESSION=requests.Session();SESSION.headers.update(HEADERS)
OUT=Path('agency-market-snapshot.json')

def now():return datetime.now(timezone.utc).isoformat()
def get(path,params=None):
    for attempt in range(5):
        r=SESSION.get(BASE+path,params=params,timeout=(10,35))
        if r.status_code in (429,500,502,503,504):
            delay=max(15,min(120,int(r.headers.get('Retry-After','30'))))
            print('Waiting for MFL',r.status_code,delay,'seconds',flush=True);time.sleep(delay);continue
        r.raise_for_status();return r.json()
    raise RuntimeError('MFL read failed after retries')
def rows(payload):
    if isinstance(payload,list):return payload
    if isinstance(payload,dict):
        for key in ('data','players','listings','items','results'):
            if key in payload and isinstance(payload[key],(dict,list)):return rows(payload[key])
    raise ValueError('Unexpected list response')
def unwrap(p):
    for key in ('data','player','item'):
        if isinstance(p,dict) and isinstance(p.get(key),dict):return unwrap(p[key])
    return p

def player(p):
    p=unwrap(p);m=p.get('metadata') or {}
    name=p.get('name') or m.get('name') or ' '.join(str(m.get(k) or p.get(k) or '') for k in ('firstName','lastName')).strip()
    result={'player_id':p.get('id') or p.get('playerId') or m.get('id'),'player':name,
            'age':m.get('age',p.get('age')),'overall':m.get('overall',p.get('overall')),
            'positions':m.get('positions') or p.get('positions') or [],'checked_at':now()}
    for field in ('pace','shooting','passing','dribbling','defense','physical','goalkeeping','potential','height','foot','nationality'):
        result[field]=m.get(field,p.get(field))
    for key in ('status','retired','retirementDate','retirementSeason','retiredAt','positionRatings','traits'):
        if key in p or key in m:result[key]=p.get(key,m.get(key))
    club=None;known=False
    for key in ('currentClub','activeContract','club','contract'):
        for source in (p,m):
            if key not in source:continue
            value=source[key]
            if key in ('activeContract','contract') and isinstance(value,dict):value=value.get('club')
            if value is None:known=True;continue
            if isinstance(value,dict) and value.get('name'):club=value['name'];known=True
            if isinstance(value,str):club=value;known=True
        if club:break
    result.update(club=club,club_known=known)
    return result

def main():
    wallet=os.environ['AGENCY_WALLET']
    snapshot={'captured_at':now(),'wallet':wallet,'roster_complete':False,'market_complete':False,'owned_players':[],'market':[],'errors':[]}
    seen={};before=None
    try:
        for page in range(100):
            params={'ownerWalletAddress':wallet,'limit':100,'view':'full'}
            if before is not None:params['beforePlayerId']=before
            payload=get('/players',params);batch=rows(payload)
            if page==0:
                snapshot['roster_response_keys']=list(payload) if isinstance(payload,dict) else []
                if batch:snapshot['sample_roster_keys']={'player':list(batch[0]),'metadata':list((batch[0].get('metadata') or {}))}
            if not batch:snapshot['roster_complete']=True;break
            fresh=[]
            for raw in batch:
                row=player(raw);pid=int(row['player_id'])
                if pid not in seen:seen[pid]=row;fresh.append(pid)
            if not fresh:raise ValueError('Roster pagination did not advance')
            before=min(fresh);snapshot['owned_players']=list(seen.values());OUT.write_text(json.dumps(snapshot))
            print('Roster page',page+1,'players',len(seen),flush=True);time.sleep(.5)
        if not snapshot['roster_complete']:raise ValueError('Roster not complete')
        # Verify the roster membership with a second complete pass.
        verify=set();cursor=None
        for page in range(100):
            params={'ownerWalletAddress':wallet,'limit':100}
            if cursor is not None:params['beforePlayerId']=cursor
            batch=rows(get('/players',params))
            if not batch:break
            ids={int(player(r)['player_id']) for r in batch}
            if not (ids-verify):raise ValueError('Roster verification stalled')
            verify.update(ids);cursor=min(ids);time.sleep(.4)
        snapshot['roster_verified']=verify==set(seen)
        if not snapshot['roster_verified']:raise ValueError('Agency membership changed during snapshot')
        # Bulk roster normally contains complete profiles; fill only incomplete rows.
        for pid,row in list(seen.items()):
            if row['age'] is None or row['overall'] is None or not row['positions']:
                seen[pid]=player(get('/players/'+str(pid)));time.sleep(.5)
        snapshot['owned_players']=list(seen.values());snapshot['roster_checked_at']=now()
        before=None;listing_seen=set();market=[]
        for page in range(int(os.getenv('MARKET_PAGES','160'))):
            params={'limit':25,'type':'PLAYER','status':'AVAILABLE','view':'full'}
            if before is not None:params['beforeListingId']=before
            payload=get('/listings',params);batch=rows(payload)
            if not batch:snapshot['market_complete']=True;break
            fresh=[]
            for raw in batch:
                lid=raw.get('listingResourceId') or raw.get('id')
                if lid is None or str(lid) in listing_seen:continue
                listing_seen.add(str(lid));fresh.append(lid)
                p=raw.get('player') or {}
                if not isinstance(p,dict):continue
                row=player(p);price=raw.get('price');currency=raw.get('currency') or raw.get('priceCurrency')
                if isinstance(price,dict):currency=price.get('currency') or currency;price=price.get('amount')
                row.update(price=price,currency=currency,listing_id=lid,listing_status=raw.get('status'),listed_at=raw.get('createdAt') or raw.get('date'))
                if page==0 and not market:snapshot['sample_listing_keys']=list(raw)
                market.append(row)
            if not fresh:break
            before=batch[-1].get('listingResourceId') or batch[-1].get('id')
            if before is None:break
            snapshot['market']=market;snapshot['market_pages']=page+1;OUT.write_text(json.dumps(snapshot))
            if page%10==0:print('Market page',page+1,'listings',len(market),flush=True)
            time.sleep(.5)
        snapshot['market']=market;snapshot['market_checked_at']=now();snapshot['completed_at']=now()
    except Exception as exc:
        snapshot['errors'].append(type(exc).__name__+': '+str(exc)[:180])
    OUT.write_text(json.dumps(snapshot,ensure_ascii=False))
    print('SCAN_SUMMARY',json.dumps({k:snapshot.get(k) for k in ('roster_complete','roster_verified','roster_checked_at','market_complete','market_pages','completed_at','errors','sample_roster_keys','sample_listing_keys')}),flush=True)
    print('Players:',len(snapshot['owned_players']),'Market:',len(snapshot['market']),flush=True)
    if snapshot['errors']:raise SystemExit(1)
if __name__=='__main__':main()
