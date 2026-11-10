from __future__ import annotations

import base64
import hmac
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Resolve this standalone app's backend even when Streamlit starts at repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import backend as b
import rendering

st.set_page_config(page_title='Grower or Shower · Top Boy', page_icon='🌱', layout='wide')


def setting(key, default=''):
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return os.getenv(key, default)


@st.cache_resource
def storage():
    return b.Store(os.getenv('COMPETITIONS_DB', str(b.ROOT / 'competitions_s18.sqlite3')))


font = base64.b64encode((b.ROOT / 'assets/fonts/OpenSans-CondBold.ttf').read_bytes()).decode('ascii')
st.html('<style>@font-face{font-family:"WTS Condensed";src:url(data:font/ttf;base64,' + font + ') format("truetype");font-weight:700;font-display:swap}' + (b.ROOT / 'wts.css').read_text() + '</style>')
st.html('''<div class="wts-brandbar"><div class="wts-brandname">WORKTHESPACE<small>MFL COMMUNITY</small></div><a class="mfl-brand" href="https://app.playmfl.com" target="_blank" rel="noopener noreferrer" aria-label="MFL"><img class="mfl-logo" src="https://res.cloudinary.com/lancers-technology/image/upload/v1770748400/web3-explorer/dapp-logos/mfl.png" alt="MFL logo"></a></div>''')

# Restore a server-signed backup before reading either competition's tables.
import browser_backup
store=storage()
backup_secret=str(setting('BACKUP_SIGNING_KEY') or setting('MFL_REFRESH_TOKEN'))
backup_ready=browser_backup.restore(store,backup_secret)
for entry in b.entrants():store.recover_baseline(entry['player_id'])

page = st.session_state.get('competition_page')
if page not in ('Grower or Shower', 'Top Boy'):
    st.html('<div class="wts-hero"><div class="wts-hero-title"><span>WORKTHESPACE</span><span>MFL COMMUNITY</span></div><div class="wts-season">SEASON 18</div></div>')
    st.title('Competitions')
    grower_choice, topboy_choice = st.columns(2)
    with grower_choice, st.container(key='landing_grower'):
        st.html(f'<div class="competition-choice"><div class="entry-number">01</div><h2>Grower or Shower</h2><p>{len(b.entrants())} entrants</p></div>')
        if st.button('Grower or Shower', key='open_grower', type='primary', width='stretch'):
            st.session_state['competition_page'] = 'Grower or Shower'
            st.rerun()
    with topboy_choice, st.container(key='landing_topboy'):
        st.html(f'<div class="competition-choice"><div class="entry-number">02</div><h2>Top Boy</h2><p>{len(b.entrants("top_boy"))} entrants</p></div>')
        if st.button('Top Boy', key='open_topboy', type='primary', width='stretch'):
            st.session_state['competition_page'] = 'Top Boy'
            st.rerun()
    browser_backup.save(store,backup_secret,backup_ready)
    st.stop()

if st.button('← Competitions', key='back_to_competitions'):
    st.session_state.pop('competition_page', None)
    st.rerun()
st.html('<div class="kicker">WORKTHESPACE MFL COMMUNITY · SEASON 18</div>')
st.title(page)
if page == 'Top Boy':
    import top_boy_page
    top_boy_page.render(store, setting)
    browser_backup.save(store,backup_secret,backup_ready)
    st.stop()

store = storage()
import grower_live
grower_snapshot=grower_live.fetch()
grower_live.apply(store,grower_snapshot)
if grower_snapshot:
    checked=b.timestamp(grower_snapshot.get('last_complete_at'))
    if checked:st.caption('Player development updated '+checked.strftime('%d %b, %H:%M GMT'))
    if grower_snapshot.get('errors'):st.info('Some players could not be checked. Their saved data is kept.')
confirmed = str(setting('SCORING_CONFIRMED', 'false')).lower() == 'true'
entries = b.entrants()
data = b.standings(store, confirmed=confirmed)
saved = sum(bool(r.get('checked_at')) for r in data)
baselines = sum(bool(r.get('baseline_at')) for r in data)
cols = st.columns(4)
for col, title, value in zip(cols, ['Linked entries', 'Players loaded', 'Starting values saved', 'First training / games'],
                             [len(entries), f'{saved} / {len(entries)}', f'{baselines} / {len(entries)}', '4 Nov']):
    col.metric(title, value)

st.write('')
import grower_controls
grower_controls.render(store,setting)
if baselines < len(entries):
    st.info(f'{baselines} of {len(entries)} starting values are available. Refresh reads dated player history to recover missing values from before 4 November. Missing starting values stay unranked; current stats are never used as a replacement.')
if not backup_secret:
    st.warning('Automatic browser backup is unavailable. Download a competition backup after refreshing.')
elif backup_ready:
    st.caption('Automatic backup is enabled for this browser. Keep a downloaded competition backup as a separate copy.')
rendering.download('Download competition backup',store.backup(),'competitions_s18_backup.json','application/json',key='grower_visible_backup')

if not confirmed:
    st.caption('Growth is measured from saved starting values. Competition ranks await confirmation of scoring and tie-break rules.')

growth, overview, table, details = st.tabs(['Progress table', 'Player cards', 'Entry register', 'Rules & prizes'])
import grower_view


def fmt(value):
    return f'{value:g}' if isinstance(value, (int, float)) else '—'


def export_rows():
    result = []
    for row in data:
        out = {'Entrant': row['entrant'], 'Player ID': row['player_id'], 'Player': row.get('player'),
               'Age': row.get('age'), 'Position': row.get('positions'), 'Current club': row.get('club'),
               'Club data available': row.get('club_known', False), 'Player URL': row['player_url'],
               'Profile checked (UTC)': row.get('checked_at'), 'Baseline saved (UTC)': row.get('baseline_at'),
               'S18 league apps': row.get('appearances'), 'S18 average rating': row.get('rating'),
               'Rated apps': row.get('rated_appearances'), 'Performance checked (UTC)': row.get('performance_checked_at'),
               'Attribute gain': row['attribute_gain'], 'Rank': row.get('rank')}
        baseline = store.baseline(row['player_id']) or {}
        for field, label in b.LABELS.items():
            out[label] = row.get(field)
            out[f'Start {label}'] = baseline.get(field)
            out[f'{label} gain'] = row['gains'][field]
        result.append(out)
    return pd.DataFrame(result)


with overview:
    search = st.text_input('Find an entrant, player or club', placeholder='Search the competition…')
    filtered = [r for r in data if search.casefold() in ' '.join(str(r.get(k) or '') for k in ('entrant', 'player', 'club', 'player_id')).casefold()]
    if not filtered:
        st.info('No entries match that search.')
    import html
    esc = lambda x: html.escape(str(x))
    grid = st.columns(3)
    for i, row in enumerate(filtered):
        with grid[i % 3]:
            st.html(grower_view.card_html(row))
            st.html(f'<div class="player-check">Last checked: {esc(row.get("checked_at") or "Not fetched yet")}</div>')
    st.caption('Changes are shown below each stat: green gains, red decreases, ±0 unchanged. — means a starting value is unavailable.')

with table:
    df = export_rows()
    rendering.table(df[['Entrant', 'Player', 'Player ID', 'Age', 'Position', 'Current club', 'OVR', 'PAC', 'SHO', 'PAS', 'DRI', 'DEF', 'PHY', 'Player URL', 'Profile checked (UTC)']],
                 hide_index=True, width='stretch',
                 column_config={'Player URL': st.column_config.LinkColumn('MFL player', display_text='Open player')})
    rendering.download('Download full player register CSV', df.to_csv(index=False).encode('utf-8-sig'),
                       'grower_or_shower_season18.csv', 'text/csv')
    st.info(f'BaldSherlock: player link still needed. Mike: entry not confirmed. Neither is counted among the {len(entries)} linked entries.')
    st.caption('Hawkeye’s final selection is #337204; the earlier #467300 has been replaced.')

with growth:
    st.html(grower_view.progress_table_html(data))
    st.caption('Changes since saved starting values · ATTR is the combined change across PAC, SHO, PAS, DRI, DEF and PHY. ±0 means unchanged; — means a starting value is unavailable.')
    rendering.download('Download competition backup', store.backup(), 'competitions_s18_backup.json', 'application/json')

with details:
    st.subheader('Competition notes')
    st.markdown('''
- First games / training: **Wednesday, 4 November 2026**. Baselines must be captured before that date.
- Players must participate in **Pro MFL**; Arena participation does not establish eligibility.
- Age was stated as **23 and under**; the chat also used “under 23”. Exact cutoff and any exceptions await confirmation.
- Proposed scoring from the existing hub: **OVR gain → total attribute gain → average league match rating**. Awaiting confirmation for Season 18.
''')
    st.subheader('Prize offers')
    st.markdown('''
- **Ricky:** one common pack for either the defender with the highest shooting increase or the attacker with the highest defending increase. Category allocation and eligible positions need confirmation.
- **BaldSherlock:** prizes mentioned; reward details and criteria still needed.
- **Mike:** best Mike-pack player prize suggested; not confirmed.
''')
    st.caption('Current age and club alone do not prove season-start age eligibility or Pro MFL participation. No automatic eligibility decisions are made.')

with st.expander('Organiser · restore saved competition data'):
    password = str(setting('ADMIN_PASSWORD'))
    if not password:
        st.caption('To enable backup restoration, set ADMIN_PASSWORD in this Streamlit app’s Secrets. Keep it private.')
    else:
        supplied = st.text_input('Organiser password', type='password')
        authorised = bool(supplied) and hmac.compare_digest(supplied, password)
        if authorised:
            file = st.file_uploader('Season 18 JSON backup', type=['json'])
            if file and st.button('Restore missing records'):
                try:
                    if file.size > 10 * 1024 * 1024:
                        raise ValueError('Backup is too large.')
                    store.restore(file.getvalue().decode('utf-8'))
                except (ValueError, TypeError, KeyError, UnicodeDecodeError):
                    st.error('The backup could not be restored. Check that it is an export from this Season 18 app.')
                else:
                    st.session_state['refresh_messages'] = ['Backup restored. Existing starting values were preserved.']
                    st.rerun()

st.divider()
st.caption('Season 18 · Grower or Shower & Top Boy · Independent competition app · All times shown in UTC')

browser_backup.save(store,backup_secret,backup_ready)
