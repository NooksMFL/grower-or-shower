"""Isolated Season 18 competition data; never opens the Season 17 database."""
from __future__ import annotations

import csv
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
TRAINING_START = '2026-11-04T00:00:00+00:00'
FIELDS = ('overall', 'pace', 'shooting', 'passing', 'dribbling', 'defense', 'physical')
LABELS = dict(zip(FIELDS, ('OVR', 'PAC', 'SHO', 'PAS', 'DRI', 'DEF', 'PHY')))
TOPBOY_TABLES = ('topboy_profiles', 'topboy_competitions', 'topboy_reviews')
HEADERS = {
    'Accept': '*/*', 'Origin': 'https://app.playmfl.com',
    'Referer': 'https://app.playmfl.com/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0',
}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, timezone.utc)
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def entrants(competition='grower'):
    filename = 'top_boy_entrants.csv' if competition == 'top_boy' else 'entrants.csv'
    with (ROOT / filename).open(newline='', encoding='utf-8') as f:
        return [{**row, 'player_id': int(row['player_id'])} for row in csv.DictReader(f)]


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and not isinstance(value, bool) else None
    except (ValueError, TypeError):
        return None


def unwrap(payload):
    for _ in range(4):
        if not isinstance(payload, dict):
            break
        child = next((payload[k] for k in ('data', 'player', 'item') if isinstance(payload.get(k), dict)), None)
        if child is None:
            break
        payload = child
    return payload


def rows(payload):
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ('data', 'items', 'results', 'history', 'experiences', 'competitions', 'playerCompetitions'):
            if key in payload:
                return rows(payload[key])
    raise ValueError('MFL returned an unrecognised list format.')


def stats(payload):
    obj = unwrap(payload)
    if not isinstance(obj, dict):
        return dict.fromkeys(FIELDS)
    meta = obj.get('metadata') if isinstance(obj.get('metadata'), dict) else {}
    candidates = [meta, obj]
    for source in (meta, obj):
        for key in ('attributes', 'stats'):
            if isinstance(source.get(key), dict):
                candidates.append(source[key])
    aliases = {'overall': ('overall', 'overallRating', 'ovr', 'OVR'),
               'defense': ('defense', 'defending', 'DEF'),
               'physical': ('physical', 'physicality', 'PHY')}
    result = {}
    for field in FIELDS:
        result[field] = next((n for source in candidates for key in aliases.get(field, (field, LABELS[field]))
                              if (n := number(source.get(key))) is not None and 0 <= n <= 100), None)
    return result


def club_name(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ('club', 'team'):
            if isinstance(value.get(key), dict):
                found = club_name(value[key])
                if found:
                    return found
        for key in ('name', 'clubName', 'teamName'):
            if isinstance(value.get(key), str):
                return value[key]
    return None


def profile(payload, pid):
    p = unwrap(payload)
    if not isinstance(p, dict) or not p:
        raise ValueError('MFL returned an empty player profile.')
    m = p.get('metadata') if isinstance(p.get('metadata'), dict) else {}
    name = m.get('name') or p.get('name') or ' '.join(str(m.get(k) or p.get(k) or '') for k in ('firstName', 'lastName')).strip()
    positions = m.get('positions') or p.get('positions') or m.get('position') or p.get('position')
    if isinstance(positions, list):
        positions = ' / '.join(str(x) for x in positions)
    club = None
    club_known = False
    for key in ('activeContract', 'currentClub', 'club', 'contract'):
        source = p if key in p else m if key in m else None
        if source is not None:
            club_known = True
            club = club_name(source[key])
            break  # An explicit null current club must not resurrect an old contract.
    values = stats(p)
    if not name and not any(v is not None for v in values.values()):
        raise ValueError('MFL player profile has no recognised name or attributes.')
    return {'player_id': pid, 'player': name or f'Player #{pid}',
            'age': number(m.get('age', p.get('age'))), 'positions': positions,
            'club': club, 'club_known': club_known, **values}


class APIError(RuntimeError):
    def __init__(self, message, stop=False):
        super().__init__(message)
        self.stop = stop


class Client:
    def __init__(self, refresh_token=''):
        self.refresh_token = refresh_token
        self.access = None
        self.auth_attempted = False

    def request(self, method, path, **kwargs):
        headers = dict(HEADERS)
        if self.access:
            headers['Authorization'] = 'Bearer ' + self.access
        try:
            r = requests.request(method, 'https://api.playmfl.com' + path,
                                 headers=headers, timeout=(6, 20), **kwargs)
        except requests.RequestException:
            raise APIError('MFL could not be reached. Previously saved data is retained.') from None
        # Never include response bodies or credentials in diagnostics.
        if r.status_code == 429:
            raise APIError('MFL rate limit reached. Wait before refreshing again.', stop=True)
        if r.status_code == 403 and 'text/html' in r.headers.get('content-type', ''):
            raise APIError('MFL security service blocked this server (HTTP 403).', stop=True)
        if r.status_code == 401 and method == 'GET' and self.refresh_token and not self.auth_attempted:
            self.auth_attempted = True
            d = self.request('POST', '/auth/refresh', json={'refreshToken': self.refresh_token})
            access = d.get('access') or (d.get('data') or {}).get('access')
            self.access = access.get('token') if isinstance(access, dict) else access
            if not self.access:
                raise APIError('MFL authentication returned no access token.', stop=True)
            return self.request(method, path, **kwargs)
        if not r.ok:
            raise APIError(f'MFL returned HTTP {r.status_code} for {path}.', stop=r.status_code in (401, 403))
        try:
            return r.json()
        except ValueError:
            raise APIError('MFL returned an unexpected response format.') from None

    def get(self, path):
        return self.request('GET', path)


def baseline_from_history(events, cutoff):
    """Only use complete, dated attribute snapshots at/before the baseline."""
    end = timestamp(cutoff)
    if end is None:
        return None
    candidates = []
    for event in events:
        date = timestamp(next((event[k] for k in ('createdAt', 'date', 'timestamp', 'created_at', 'updatedAt') if event.get(k)), None))
        if date is None or date > end:
            continue
        # No delta summing or inference from later snapshots.
        for key in ('after', 'newValues', 'values', 'player', 'metadata', 'data', None):
            obj = event if key is None else event.get(key)
            if not isinstance(obj, dict):
                continue
            values = stats(obj)
            if all(values[f] is not None for f in FIELDS):
                candidates.append((date, values))
                break
    if not candidates:
        return None
    date, values = max(candidates, key=lambda x: x[0])
    return {'at': date.isoformat(), **values}


def league_performance(records):
    apps = 0
    weighted = 0.0
    rated = 0
    recognised = False
    for item in records:
        c = item.get('competition') or {}
        if not isinstance(c, dict):
            continue
        season = c.get('season') or item.get('season')
        if isinstance(season, dict):
            season = season.get('name') or season.get('number')
        if str(season).strip().lower() not in ('18', 'season 18'):
            continue
        text = json.dumps(c).lower()
        if any(word in text for word in ('friendly', 'preseason', 'pre-season', 'cup', 'arena', 'tournament')):
            continue
        kind = str(c.get('type') or c.get('competitionType') or '').lower()
        name = str(c.get('name') or '').lower()
        if 'league' not in kind and 'league' not in name:
            continue
        s = item.get('stats') or {}
        count = next((number(s[k]) for k in ('nbMatches', 'matches', 'appearances', 'apps', 'matchesPlayed') if k in s), None)
        if count is None or count < 0 or count != int(count):
            continue
        recognised = True
        apps += int(count)
        avg = next((number(s[k]) for k in ('averageRating', 'avgRating') if s.get(k) is not None), None)
        # A bare 'rating' can mean total points or average: do not guess.
        if avg is None and number(s.get('rating')) is not None and count == 1:
            avg = number(s['rating'])
        if avg is not None and 0 <= avg <= 10 and count:
            weighted += avg * count
            rated += count
    return {'appearances': apps if recognised else None,
            'rating': round(weighted / rated, 3) if rated else None,
            'rated_appearances': rated}


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS profiles(player_id INTEGER PRIMARY KEY,payload TEXT NOT NULL,checked_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS histories(player_id INTEGER PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS competitions(player_id INTEGER PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS refreshes(id INTEGER PRIMARY KEY CHECK(id=1),at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS baselines(player_id INTEGER PRIMARY KEY,payload TEXT NOT NULL,at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS topboy_profiles(player_id INTEGER PRIMARY KEY,payload TEXT NOT NULL,checked_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS topboy_competitions(player_id INTEGER PRIMARY KEY,payload TEXT NOT NULL,checked_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS topboy_reviews(player_id INTEGER PRIMARY KEY,payload TEXT NOT NULL,checked_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS topboy_refresh(id INTEGER PRIMARY KEY CHECK(id=1),at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS site_assets(name TEXT PRIMARY KEY,mime TEXT NOT NULL,content BLOB NOT NULL);
            ''')

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def latest(self):
        with self.connect() as c:
            return {pid: {**json.loads(p), 'checked_at': at} for pid, p, at in c.execute('SELECT player_id,payload,checked_at FROM profiles')}

    def history(self, pid):
        with self.connect() as c:
            row = c.execute('SELECT payload FROM histories WHERE player_id=?', (pid,)).fetchone()
        return json.loads(row[0]) if row else []

    def performance(self, pid):
        with self.connect() as c:
            row = c.execute('SELECT payload FROM competitions WHERE player_id=?', (pid,)).fetchone()
        return json.loads(row[0]) if row else None

    def claim_refresh(self, seconds=900):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT at FROM refreshes WHERE id=1').fetchone()
            if row and (datetime.now(timezone.utc) - timestamp(row[0])).total_seconds() < seconds:
                return False
            c.execute('INSERT OR REPLACE INTO refreshes VALUES(1,?)', (utcnow(),))
            return True

    def save(self, table, pid, payload):
        if table not in ('histories', 'competitions'):
            raise ValueError('Unsupported storage table')
        with self.connect() as c:
            c.execute(f'INSERT OR REPLACE INTO {table} VALUES(?,?)', (pid, json.dumps(payload)))

    def save_profile(self, pid, payload):
        now = utcnow()
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO profiles VALUES(?,?,?)', (pid, json.dumps(payload), now))
            if timestamp(now) < timestamp(TRAINING_START) and all(payload.get(f) is not None for f in FIELDS):
                c.execute('INSERT OR IGNORE INTO baselines VALUES(?,?,?)', (pid, json.dumps({f: payload[f] for f in FIELDS}), now))

    def baseline(self, pid):
        with self.connect() as c:
            row = c.execute('SELECT payload,at FROM baselines WHERE player_id=?', (pid,)).fetchone()
        return {**json.loads(row[0]), 'at': row[1]} if row else None

    def backup(self):
        with self.connect() as c:
            tables = {table: c.execute(f'SELECT * FROM {table}').fetchall()
                      for table in ('profiles', 'baselines', 'histories', 'competitions') + TOPBOY_TABLES}
        from sponsor import get
        return json.dumps({'version': 1, 'season': 18, 'tables': tables, 'sponsor': get(self)}, indent=2)

    def restore(self, content):
        data = json.loads(content)
        if data.get('version') != 1 or data.get('season') != 18:
            raise ValueError('This is not a Season 18 competition backup.')
        tables = data.get('tables', {})
        artwork = None
        if data.get('sponsor') is not None:
            from sponsor import decode_backup
            artwork = decode_backup(data['sponsor'])
        allowed = {e['player_id'] for e in entrants()}
        validated = {}
        for table in ('profiles', 'baselines', 'histories', 'competitions') + TOPBOY_TABLES:
            records = tables.get(table, [])
            expected = 3 if table in ('profiles', 'baselines') + TOPBOY_TABLES else 2
            if not isinstance(records, list):
                raise ValueError('Invalid backup table.')
            validated[table] = []
            for row in records:
                ids = {e['player_id'] for e in entrants('top_boy')} if table in TOPBOY_TABLES else allowed
                if not isinstance(row, list) or len(row) != expected or row[0] not in ids:
                    raise ValueError('Backup contains an invalid player record.')
                payload = json.loads(row[1])
                if table == 'baselines':
                    if not isinstance(payload, dict) or any(number(payload.get(f)) is None or not 0 <= number(payload[f]) <= 100 for f in FIELDS):
                        raise ValueError('Backup has invalid baseline attributes.')
                    if timestamp(row[2]) is None or timestamp(row[2]) >= timestamp(TRAINING_START):
                        raise ValueError('Baseline must have been captured before training starts.')
                if expected == 3 and timestamp(row[2]) is None:
                    raise ValueError('Backup has an invalid timestamp.')
                if table in ('profiles', 'topboy_profiles') and (not isinstance(payload, dict) or payload.get('player_id') != row[0]):
                    raise ValueError('Invalid saved profile.')
                if table == 'histories' and not isinstance(payload, list):
                    raise ValueError('Invalid history.')
                if table in ('competitions', 'topboy_competitions') and (not isinstance(payload, dict) or not isinstance(payload.get('records'), list)):
                    raise ValueError('Invalid competition records.')
                if table == 'topboy_reviews':
                    from top_boy import validate_review
                    validate_review(payload)
                validated[table].append(tuple(row))
        with self.connect() as c:
            for table, records in validated.items():
                placeholders = '?,?,?' if table in ('profiles', 'baselines') + TOPBOY_TABLES else '?,?'
                # Restore missing records only: never overwrite an existing baseline.
                c.executemany(f'INSERT OR IGNORE INTO {table} VALUES({placeholders})', records)
            if artwork is not None:
                c.execute('INSERT OR IGNORE INTO site_assets VALUES(?,?,?)', ('sponsor', artwork[0], artwork[1]))

    def refresh(self, client, progress=None):
        if not self.claim_refresh():
            return ['A refresh was already attempted in the last 15 minutes. Saved data is shown.']
        messages = []
        entries = entrants()
        for i, entry in enumerate(entries):
            pid = entry['player_id']
            stop = False
            for endpoint, table in ((f'/players/{pid}', 'profiles'),
                                    (f'/players/{pid}/experiences/history', 'histories'),
                                    (f'/players/{pid}/competitions', 'competitions')):
                try:
                    data = client.get(endpoint)
                    if table == 'profiles':
                        self.save_profile(pid, profile(data, pid))
                    elif table == 'histories':
                        self.save(table, pid, rows(data))
                    else:
                        self.save(table, pid, {'records': rows(data), 'checked_at': utcnow()})
                except (APIError, ValueError) as exc:
                    messages.append(f"{entry['entrant']}: {exc}")
                    if isinstance(exc, APIError) and exc.stop:
                        stop = True
                        break
            if progress:
                progress((i + 1) / len(entries))
            if stop:
                messages.append('Refresh stopped; previously saved data is retained for all remaining players.')
                break
        return messages


def standings(store, cutoff='', confirmed=False):
    saved = store.latest()
    result = []
    for entry in entrants():
        pid = entry['player_id']
        p = saved.get(pid, {})
        baseline = store.baseline(pid)
        perf_payload = store.performance(pid)
        perf = league_performance(perf_payload['records']) if perf_payload is not None else {}
        delta = {f: round(p[f] - baseline[f], 3) if baseline and p.get(f) is not None else None for f in FIELDS}
        total = sum(delta[f] for f in FIELDS[1:]) if all(delta[f] is not None for f in FIELDS[1:]) else None
        complete = confirmed and delta['overall'] is not None and total is not None
        result.append({**entry, **p, **perf, 'performance_checked_at': (perf_payload or {}).get('checked_at'),
                       'player_url': f'https://app.playmfl.com/players/{pid}',
                       'baseline_at': baseline['at'] if baseline else None,
                       'gains': delta, 'attribute_gain': total, 'rankable': complete})
    # A rating is a required final tie-break only when OVR and attribute gains tie.
    rankable = [r for r in result if r['rankable']]
    groups = {}
    for r in rankable:
        groups.setdefault((r['gains']['overall'], r['attribute_gain']), []).append(r)
    for group in groups.values():
        if len(group) > 1 and any(r.get('rating') is None for r in group):
            for r in group:
                r['rating_tie_pending'] = True
    result.sort(key=lambda r: (not r['rankable'], -(r['gains']['overall'] or 0) if r['rankable'] else 0,
                              -(r['attribute_gain'] or 0) if r['rankable'] else 0,
                              -(r.get('rating') or 0) if r['rankable'] and not r.get('rating_tie_pending') else 0,
                              r['entrant'].lower()))
    # Do not publish a competition rank while any linked entrant lacks baseline data.
    if len(rankable) == len(result):
        last_key = None
        rank = None
        for i, row in enumerate(result, 1):
            key = (row['gains']['overall'], row['attribute_gain'], None if row.get('rating_tie_pending') else row.get('rating'))
            if key != last_key:
                rank = i
            row['rank'] = rank
            last_key = key
    return result
