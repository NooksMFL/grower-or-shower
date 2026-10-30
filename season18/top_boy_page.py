"""Top Boy Streamlit page, independent from Grower or Shower data and baselines."""
from __future__ import annotations

import hmac
import html
import json

import pandas as pd
import streamlit as st

import backend as b
import top_boy as tb


def display(value):
    return f'{value:g}' if isinstance(value, (int, float)) else '—'


def frame(rows):
    return pd.DataFrame([{
        'Pos': r['position'], 'Photo': f"https://d13e14gtps4iwl.cloudfront.net/players/v2/{r['player_id']}/photo.webp",
        'Entrant': r['entrant'], 'Player': r.get('player') or f"Player #{r['player_id']}",
        'Club': r.get('club') or ('No current club' if r.get('club_known') else 'Awaiting player data'), 'League': r.get('league'), 'Goals': r['goals'],
        'Goal pts': 5 * r['goals'] if r['goals'] is not None else None,
        'Assists': r['assists'], 'Assist pts': 3 * r['assists'] if r['assists'] is not None else None,
        'Win appearances': r['wins'], 'Win pts': r['wins'], 'Points': r['points'],
        'League + cup apps': r.get('appearances'), 'Eligibility': r['eligibility'],
        'Entry rating': r.get('entry_rating'), 'OOP rating': r['oop'],
        'Current OVR': r.get('overall'), 'Age': r.get('age'), 'Position': r.get('positions'),
        **{label: r.get(field) for field, label in b.LABELS.items() if field != 'overall'},
        'Player ID': r['player_id'], 'MFL player': r['player_url'],
        'Profile checked (UTC)': r.get('checked_at'), 'Score checked (UTC)': r.get('score_checked_at'),
        'Source': r['source'], 'Evidence note': r['evidence'],
    } for r in rows])


def league_table_html(rows):
    esc = lambda value: html.escape(str(value), quote=True)
    body = []
    for row in rows:
        pid = int(row['player_id'])
        player = row.get('player') or f'Player #{pid}'
        club = row.get('club') or ('No current club' if row.get('club_known') else 'Player data pending')
        leader = ' class="tb-leader"' if row.get('position') == 1 and row.get('points') is not None else ''
        numbers = ''.join(f'<td class="tb-number">{display(row.get(key))}</td>' for key in ('appearances', 'goals', 'assists', 'wins'))
        body.append(f'''<tr{leader}>
<td class="tb-place"><span>{display(row.get('position'))}</span></td>
<th scope="row" class="tb-entrant">{esc(row['entrant'])}</th>
<td class="tb-player"><a href="https://app.playmfl.com/players/{pid}" target="_blank" rel="noopener noreferrer">
<img src="https://d13e14gtps4iwl.cloudfront.net/players/v2/{pid}/photo.webp" alt="" width="36" height="40" loading="lazy">
<span class="tb-player-text"><strong title="{esc(player)}">{esc(player)}</strong><small>{esc(club)}</small><small class="tb-entrant-mobile">{esc(row['entrant'])}</small></span></a></td>
{numbers}<td class="tb-points">{display(row.get('points'))}</td></tr>''')
    return '''<div class="tb-table-wrap"><div class="tb-table-label"><strong>SEASON 18</strong><span>LEAGUE + CUP</span></div>
<table class="tb-league-table" aria-label="Top Boy Season 18 league table"><thead><tr>
<th scope="col" class="tb-place">#</th><th scope="col" class="tb-entrant">ENTRANT</th><th scope="col" class="tb-player">PLAYER</th>
<th scope="col" class="tb-number"><abbr title="League and cup appearances">Pld</abbr></th>
<th scope="col" class="tb-number"><abbr title="Goals">G</abbr></th><th scope="col" class="tb-number"><abbr title="Assists">A</abbr></th>
<th scope="col" class="tb-number"><abbr title="Team wins with a player appearance">W</abbr></th><th scope="col" class="tb-points">PTS</th>
</tr></thead><tbody>''' + ''.join(body) + '</tbody></table></div>'


def render(store, setting):
    with st.spinner('Loading any new Top Boy entries…'):
        automatic_messages = tb.refresh_missing(store, b.Client(str(setting('MFL_REFRESH_TOKEN'))))
    if automatic_messages:
        st.warning('New-entry lookup could not finish. Player links are still available in Player cards.')
        with st.expander('New-entry lookup details'):
            for message in automatic_messages:
                st.write(message)
    rows = tb.leaderboard(store)
    loaded = sum(bool(r.get('checked_at')) for r in rows)
    complete = sum(r['points'] is not None for r in rows)
    st.markdown(f'<div class="tb-summary"><strong>{len(rows)} ENTRANTS</strong><span>GOAL <b>+5</b></span><span>ASSIST <b>+3</b></span><span>WIN WITH APPEARANCE <b>+1</b></span></div>', unsafe_allow_html=True)
    if st.button('↻ Refresh Top Boy', type='primary', width='stretch'):
        bar = st.progress(0, text='Refreshing Top Boy players and league / cup records…')
        messages = tb.refresh(store, b.Client(str(setting('MFL_REFRESH_TOKEN'))),
                              lambda n: bar.progress(n, text='Refreshing Top Boy players and league / cup records…'))
        bar.empty()
        st.session_state['topboy_messages'] = messages
        st.rerun()
    if 'topboy_messages' in st.session_state:
        if st.session_state['topboy_messages']:
            st.warning('Refresh has notices. Saved records are retained.')
            with st.expander('Top Boy refresh details', expanded=loaded == 0):
                for message in st.session_state['topboy_messages']:
                    st.write(message)
        else:
            st.success('Top Boy player profiles and competition records refreshed.')

    league, players, rules, organiser = st.tabs(['League table', 'Player cards', 'Rules & caps', 'Organiser'])
    df = frame(rows)
    with league:
        provisional = any(r['points'] is None or r['eligibility'] != 'Within cap' for r in rows)
        st.markdown(league_table_html(rows), unsafe_allow_html=True)
        st.caption(f'{loaded}/{len(rows)} profiles loaded · {complete}/{len(rows)} complete scores · ' + ('Provisional: scoring or eligibility checks pending. ' if provisional else '') + 'Equal points share a position. — means unavailable.')
        if any(r['wins'] is None for r in rows):
            st.caption('A club’s win total cannot prove that this player appeared. If MFL does not provide appearance-scoped wins, the organiser can enter verified full-season totals below.')
        with st.expander('Points breakdown and data sources'):
            st.dataframe(df[['Entrant', 'Goals', 'Goal pts', 'Assists', 'Assist pts', 'Win appearances', 'Win pts', 'Points', 'League + cup apps', 'Eligibility', 'Score checked (UTC)', 'Source', 'Evidence note']], hide_index=True, width='stretch')
        st.download_button('Download Top Boy table CSV', df.to_csv(index=False).encode('utf-8-sig'), 'top_boy_season18.csv', 'text/csv')
        st.download_button('Download backup · both competitions', store.backup(), 'competitions_s18_backup.json', 'application/json', key='topboy_backup')

    with players:
        search = st.text_input('Find a Top Boy entrant, player or club', placeholder='Search Top Boy…')
        filtered = [r for r in rows if search.casefold() in ' '.join(str(r.get(k) or '') for k in ('entrant', 'player', 'club', 'player_id')).casefold()]
        if not filtered:
            st.info('No Top Boy entries match that search.')
        grid = st.columns(3)
        esc = lambda value: html.escape(str(value))
        for i, row in enumerate(filtered):
            with grid[i % 3]:
                club = row.get('club') or ('No current club' if row.get('club_known') else 'Club awaiting MFL data')
                name = row.get('player') or f"Player #{row['player_id']}"
                attrs = ''.join(f'<span>{label}<b>{display(row.get(field))}</b></span>' for field, label in b.LABELS.items() if field != 'overall')
                st.markdown(f'''<div class="player"><a href="{row['player_url']}" target="_blank" rel="noopener noreferrer">
                    <img src="https://d13e14gtps4iwl.cloudfront.net/players/v2/{row['player_id']}/photo.webp" alt="">
                    <div class="owner" style="color:#f3c169">{esc(row['entrant'])}</div>
                    <div class="name">{esc(name)}</div><div class="sub">{esc(row.get('positions') or 'Position pending')} · Age {display(row.get('age'))}<br>{esc(club)}</div>
                    <div class="ovr">{display(row.get('overall'))} <small style="font-size:.75rem;color:#acb8ca">OVR</small></div>
                    <div class="stats">{attrs}</div></a></div>''', unsafe_allow_html=True)
                st.markdown(f'<div class="player-check">{display(row["points"])} points · Last checked: {esc(row.get("checked_at") or "Not fetched yet")}</div>', unsafe_allow_html=True)
        st.dataframe(df[['Entrant', 'Player ID', 'Player', 'Club', 'Current OVR', 'Age', 'Position', 'PAC', 'SHO', 'PAS', 'DRI', 'DEF', 'PHY', 'MFL player']],
                     hide_index=True, width='stretch',
                     column_config={'MFL player': st.column_config.LinkColumn('MFL player', display_text='Open player')})

    with rules:
        st.markdown('''
### How to score

| Event | Points |
|---|---:|
| Goal | 5 |
| Assist | 3 |
| Team win, with the nominated player appearing | 1 |

**Season 18 league and cup matches count.** Friendlies, preseason, exhibitions and Arena are excluded.

### Maximum entry ratings
''')
        st.dataframe(pd.DataFrame([{'League': name, 'Maximum OVR': cap} for name, cap in tb.CAPS.items()]), hide_index=True, width='stretch')
        st.write('**OOP ratings are allowed.** The organiser can record the effective entry rating and its position in the evidence note. Current OVR is displayed separately and does not automatically disqualify a developing player.')
        st.write('**Winner’s prize: a limited pack.**')
        st.caption('Source: the supplied Season 18 Top Boy poster, plus the organiser’s league/cup and win-appearance clarification. Final tie-break and prize-sharing rules have not been supplied.')

    with organiser:
        st.write('Record entry eligibility and, where needed, verified full-season scoring totals. Manual totals stay visible until replaced or switched back to MFL data.')
        password = str(setting('ADMIN_PASSWORD'))
        if not password:
            st.info('Set ADMIN_PASSWORD in this app’s Streamlit Secrets to enable organiser controls.')
        else:
            supplied = st.text_input('Organiser password', type='password', key='topboy_admin_password')
            if supplied and hmac.compare_digest(supplied, password):
                labels = {f"{r['entrant']} · #{r['player_id']}": r for r in rows}
                chosen = st.selectbox('Top Boy entrant', list(labels))
                row = labels[chosen]
                review = row['review']
                pid = row['player_id']
                with st.form(f'topboy_review_{pid}'):
                    options = ['Not yet checked'] + list(tb.CAPS)
                    division = st.selectbox('League at entry', options, index=options.index(review.get('league')) if review.get('league') in options else 0)
                    rating = st.number_input('Effective OVR at entry', min_value=0.0, max_value=100.0,
                                             value=float(review['entry_rating']) if review.get('entry_rating') is not None else None, step=1.0)
                    oop = st.checkbox('This is an out-of-position rating', value=review.get('oop', False))
                    manual = st.checkbox('Use organiser-verified full-season totals', value=review.get('manual_totals') is not None)
                    st.caption('Enter season-to-date totals for league and cup combined, not values to add. Win appearances count only matches this nominated player actually played.')
                    values = {}
                    columns = st.columns(3)
                    existing = review.get('manual_totals') or {}
                    for col, key, label in zip(columns, tb.SCORING_FIELDS, ('Goals', 'Assists', 'Win appearances')):
                        values[key] = col.number_input(label, min_value=0, value=existing.get(key), step=1)
                    note = st.text_area('Evidence / position / scoring period', value=review.get('note', ''),
                                        placeholder='Include the source, matches checked, and position if using an OOP rating.')
                    submitted = st.form_submit_button('Save organiser review', type='primary')
                if submitted:
                    payload = {'league': None if division == 'Not yet checked' else division,
                               'entry_rating': rating, 'oop': oop,
                               'manual_totals': values if manual else None, 'note': note}
                    try:
                        tb.save(store, 'topboy_reviews', pid, payload)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state['topboy_messages'] = ['Organiser review saved. Download a fresh competition backup to retain it.']
                        st.rerun()
                st.divider()
                backup = st.file_uploader('Restore a Season 18 competition backup', type=['json'], key='topboy_restore_file')
                if backup and st.button('Restore missing competition records', key='topboy_restore'):
                    try:
                        if backup.size > 10 * 1024 * 1024:
                            raise ValueError('Backup is too large.')
                        store.restore(backup.getvalue().decode('utf-8'))
                    except (ValueError, TypeError, KeyError, UnicodeDecodeError):
                        st.error('The backup could not be restored. Use an export from this Season 18 app.')
                    else:
                        st.session_state['topboy_messages'] = ['Competition backup restored. Existing starting values and organiser reviews were preserved.']
                        st.rerun()
        with st.expander('MFL scoring data · for checking field coverage'):
            st.caption('Contains public player competition records only. Use this to check whether MFL supplies win appearances; no token or password is included.')
            st.download_button('Download MFL scoring records', json.dumps(tb.records(store, 'topboy_competitions'), indent=2), 'top_boy_mfl_scoring_records.json', 'application/json')

    st.caption('Keep a backup of both competitions after capturing or verifying data. Local Streamlit storage can reset on a reboot or redeploy.')
