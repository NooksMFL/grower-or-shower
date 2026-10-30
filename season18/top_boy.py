"""Top Boy: league and cup, 5/3/1 scoring; player must appear for win points."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import backend as b

CAPS = {'Flint': 62, 'Spark': 68, 'Ice': 74, 'Stone': 78, 'Iron': 82}
SCORING_FIELDS = ('goals', 'assists', 'wins')


def count(value):
    number = b.number(value)
    return int(number) if number is not None and number >= 0 and number.is_integer() else None


def competition_kind(record):
    c = record.get('competition')
    if not isinstance(c, dict):
        return None
    season = c.get('season') or record.get('season')
    if isinstance(season, dict):
        season = season.get('name') or season.get('number')
    if season is None:
        return 'unknown'
    if str(season).strip().lower() not in ('18', 'season 18'):
        return None
    name = str(c.get('name') or '').lower()
    kind = str(c.get('type') or c.get('competitionType') or '').lower()
    text = name + ' ' + kind
    if any(word in text for word in ('friendly', 'preseason', 'pre-season', 'exhibition', 'arena')):
        return None
    if 'league' in text:
        return 'league'
    if 'cup' in text:
        return 'cup'
    return 'unknown'


def player_totals(records):
    """Only read player-scoped stats, never club/team totals or generic feed data."""
    totals = dict.fromkeys(('appearances',) + SCORING_FIELDS, 0)
    missing = set()
    relevant = 0
    seen = set()
    for row in records:
        kind = competition_kind(row)
        if kind == 'unknown':
            missing.update(totals)
            continue
        if kind is None:
            continue
        # Only collapse exactly duplicated payloads; two clubs may have separate rows.
        signature = json.dumps(row, sort_keys=True, default=str)
        if signature in seen:
            continue
        seen.add(signature)
        relevant += 1
        stats = row.get('stats')
        if not isinstance(stats, dict):
            missing.update(totals)
            continue
        aliases = {'appearances': ('matches', 'nbMatches', 'appearances', 'matchesPlayed', 'apps'),
                   'goals': ('goals', 'nbGoals', 'goalsScored'),
                   'assists': ('assists', 'nbAssists', 'goalAssists'),
                   # Explicit appearance-scoped wins only. A generic team win total
                   # cannot prove this player appeared, even on a player endpoint.
                   'wins': ('winsWithAppearance', 'appearanceWins', 'winAppearances', 'matchesWonWhenPlayed')}
        values = {}
        for field, names in aliases.items():
            value = next((count(stats[name]) for name in names if name in stats), None)
            values[field] = value
        apps = values['appearances']
        if apps == 0:
            # An explicit zero appearances establishes no scoring contributions.
            if any(values[f] not in (0, None) for f in SCORING_FIELDS):
                missing.update(totals)
                continue
            values = dict.fromkeys(totals, 0)
        if values['wins'] is not None and (apps is None or values['wins'] > apps):
            values['wins'] = None
        for field, value in values.items():
            if value is None:
                missing.add(field)
            else:
                totals[field] += value
    # A valid empty list confirms no records; nonempty unclassified rows do not.
    return {**{key: None if key in missing else value for key, value in totals.items()},
            'competition_rows': relevant, 'missing_fields': sorted(missing)}


def points(goals, assists, wins):
    values = [count(v) for v in (goals, assists, wins)]
    return 5 * values[0] + 3 * values[1] + values[2] if all(v is not None for v in values) else None


def validate_review(review):
    if not isinstance(review, dict):
        raise ValueError('Invalid organiser review.')
    league = review.get('league')
    rating = b.number(review.get('entry_rating'))
    if league is not None and league not in CAPS:
        raise ValueError('Choose a recognised league.')
    if review.get('entry_rating') is not None and (rating is None or not 0 <= rating <= 100):
        raise ValueError('Entry rating must be between 0 and 100.')
    if not isinstance(review.get('note', ''), str):
        raise ValueError('Evidence note must be text.')
    if not isinstance(review.get('oop', False), bool):
        raise ValueError('Invalid OOP rating choice.')
    if review.get('manual_totals') is not None:
        values = review['manual_totals']
        if not isinstance(values, dict) or any(count(values.get(f)) is None for f in SCORING_FIELDS):
            raise ValueError('Enter all three non-negative whole-number scoring totals.')
        if not review.get('note', '').strip():
            raise ValueError('Add an evidence note for manually verified scoring totals.')
    return review


def records(store, table):
    if table not in b.TOPBOY_TABLES:
        raise ValueError('Unsupported Top Boy table.')
    with store.connect() as c:
        return {pid: {**json.loads(payload), 'checked_at': at}
                for pid, payload, at in c.execute(f'SELECT * FROM {table}')}


def save(store, table, pid, payload):
    if table not in b.TOPBOY_TABLES or pid not in {e['player_id'] for e in b.entrants('top_boy')}:
        raise ValueError('Unknown Top Boy record.')
    if table == 'topboy_reviews':
        validate_review(payload)
    with store.connect() as c:
        c.execute(f'INSERT OR REPLACE INTO {table} VALUES(?,?,?)', (pid, json.dumps(payload), b.utcnow()))


def refresh(store, client, progress=None):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT at FROM topboy_refresh WHERE id=1').fetchone()
        if row and (datetime.now(timezone.utc) - b.timestamp(row[0])).total_seconds() < 900:
            return ['Top Boy was checked in the last 15 minutes. Previously saved data is shown.']
        c.execute('INSERT OR REPLACE INTO topboy_refresh VALUES(1,?)', (b.utcnow(),))
    messages = []
    entries = b.entrants('top_boy')
    for index, entry in enumerate(entries, 1):
        pid = entry['player_id']
        stop = False
        for endpoint, table in ((f'/players/{pid}', 'topboy_profiles'),
                                (f'/players/{pid}/competitions', 'topboy_competitions')):
            try:
                payload = client.get(endpoint)
                parsed = b.profile(payload, pid) if table == 'topboy_profiles' else {'records': b.rows(payload)}
                save(store, table, pid, parsed)
            except (b.APIError, ValueError) as exc:
                messages.append(f"{entry['entrant']}: {exc}")
                if isinstance(exc, b.APIError) and exc.stop:
                    stop = True
                    break
        if progress:
            progress(index / len(entries))
        if stop:
            messages.append('Refresh stopped; previously saved player and scoring data is retained.')
            break
    return messages


def leaderboard(store):
    profiles = records(store, 'topboy_profiles')
    competitions = records(store, 'topboy_competitions')
    reviews = records(store, 'topboy_reviews')
    table = []
    for entry in b.entrants('top_boy'):
        pid = entry['player_id']
        p = profiles.get(pid, {})
        c = competitions.get(pid)
        review = reviews.get(pid, {})
        auto = player_totals(c['records']) if c else dict.fromkeys(('appearances',) + SCORING_FIELDS)
        manual = review.get('manual_totals')
        values = manual if manual is not None else auto
        league = review.get('league')
        rating = b.number(review.get('entry_rating'))
        eligibility = 'Pending entry rating / league'
        if league in CAPS and rating is not None:
            eligibility = 'Within cap' if rating <= CAPS[league] else 'Over cap'
        score = points(*(values.get(f) for f in SCORING_FIELDS))
        score_source = 'Organiser-verified totals' if manual is not None else 'MFL player competition stats'
        if manual is None and auto.get('wins') is None:
            score_source = 'Win appearances need verification'
        table.append({**entry, **p, **{f: values.get(f) for f in SCORING_FIELDS},
                      'appearances': auto.get('appearances'), 'points': score,
                      'league': league, 'entry_rating': rating, 'oop': review.get('oop', False),
                      'eligibility': eligibility, 'source': score_source,
                      'score_checked_at': review.get('checked_at') if manual is not None else (c or {}).get('checked_at'),
                      'evidence': review.get('note', ''), 'review': review,
                      'player_url': f'https://app.playmfl.com/players/{pid}'})
    table.sort(key=lambda r: (r['eligibility'] == 'Over cap', r['points'] is None, -(r['points'] or 0), r['entrant'].lower()))
    last = None
    position = None
    ranked = 0
    for row in table:
        if row['points'] is None or row['eligibility'] == 'Over cap':
            row['position'] = None
        else:
            ranked += 1
            if row['points'] != last:
                position = ranked
            row['position'] = position
            last = row['points']
    return table
