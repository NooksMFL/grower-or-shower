from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Resolve this standalone app's backend even when Streamlit starts at repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import backend as b

st.set_page_config(page_title='Grower or Shower · Top Boy', page_icon='🌱', layout='wide')


def setting(key, default=''):
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return os.getenv(key, default)


@st.cache_resource
def storage():
    return b.Store(os.getenv('COMPETITIONS_DB', str(b.ROOT / 'competitions_s18.sqlite3')))


st.markdown('''<style>
.stApp {background:#0b1018;color:#edf2f7}
.block-container {max-width:1450px;padding-top:2.4rem}
h1 {font-size:clamp(2.5rem,6vw,4.8rem)!important;letter-spacing:-.055em;line-height:1.03!important}
h2,h3 {letter-spacing:-.025em}
.kicker {color:#b7f36b;font-weight:800;letter-spacing:.18em;font-size:.76rem;margin-bottom:.8rem}
.competition-choice {border:1px solid #293548;border-radius:18px;padding:2rem;background:#111b2a;min-height:175px;margin:1.5rem 0 1rem}
.competition-choice h2 {font-size:clamp(1.8rem,3.5vw,2.6rem);margin:0 0 .8rem}
.competition-choice p {color:#acb8ca;margin:0}
.player {border:1px solid #293548;border-radius:18px;padding:1.15rem;background:linear-gradient(140deg,#162132,#0e1724);margin-bottom:1rem;min-height:230px}
.player img {width:70px;height:82px;object-fit:contain;float:right;margin-left:12px}
.player .owner {color:#b7f36b;font-size:.8rem;font-weight:700}
.player .name {font-size:1.3rem;font-weight:750;margin:.45rem 0}
.player .sub {color:#a6b4c8;font-size:.85rem;line-height:1.6}
.player .ovr {font-size:2.4rem;font-weight:800;letter-spacing:-.05em}
.player .stats {display:flex;justify-content:space-between;border-top:1px solid #293548;padding-top:.75rem;margin-top:.8rem;font-size:.8rem}
.player .stats span {text-align:center;color:#a6b4c8}.player .stats b {display:block;color:#edf2f7;font-size:1.05rem}
.player a {text-decoration:none;color:inherit}
[data-testid="stMetric"] {border:1px solid #293548;border-radius:14px;padding:1rem;background:#111b2a}
button[kind="primary"] {background:#b7f36b;color:#0b1018;border:0}
</style>''', unsafe_allow_html=True)

page = st.session_state.get('competition_page')
if page not in ('Grower or Shower', 'Top Boy'):
    st.markdown('<div class="kicker">WORKTHESPACE · SEASON 18</div>', unsafe_allow_html=True)
    st.title('Competitions')
    grower_choice, topboy_choice = st.columns(2)
    with grower_choice:
        st.markdown(f'<div class="competition-choice"><h2>Grower or Shower</h2><p>{len(b.entrants())} entrants</p></div>', unsafe_allow_html=True)
        if st.button('Grower or Shower', key='open_grower', type='primary', width='stretch'):
            st.session_state['competition_page'] = 'Grower or Shower'
            st.rerun()
    with topboy_choice:
        st.markdown(f'<div class="competition-choice"><h2>Top Boy</h2><p>{len(b.entrants("top_boy"))} entrants</p></div>', unsafe_allow_html=True)
        if st.button('Top Boy', key='open_topboy', type='primary', width='stretch'):
            st.session_state['competition_page'] = 'Top Boy'
            st.rerun()
    st.stop()

if st.button('← Competitions', key='back_to_competitions'):
    st.session_state.pop('competition_page', None)
    st.rerun()
st.markdown('<div class="kicker">WORKTHESPACE · SEASON 18</div>', unsafe_allow_html=True)
st.title(page)
if page == 'Top Boy':
    import top_boy_page
    top_boy_page.render(storage(), setting)
    st.stop()

store = storage()
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
left, right = st.columns([1, 3])
with left:
    refresh = st.button('↻ Refresh player data', type='primary', width='stretch')
with right:
    st.caption('Fetches names, age, positions, current clubs, OVR and all six attributes. Shared refresh limit: once every 15 minutes.')
if refresh:
    bar = st.progress(0, text='Checking entrants with MFL…')
    messages = store.refresh(b.Client(str(setting('MFL_REFRESH_TOKEN'))), lambda value: bar.progress(value, text='Checking entrants with MFL…'))
    bar.empty()
    st.session_state['refresh_messages'] = messages
    st.rerun()
if 'refresh_messages' in st.session_state:
    messages = st.session_state['refresh_messages']
    if messages:
        st.warning('Refresh has notices. Any previously saved data is retained.')
        with st.expander('Refresh details', expanded=saved == 0):
            for message in messages:
                st.write(message)
    else:
        st.success(f'All {len(entries)} player profiles, progression histories and competition records refreshed.')

if baselines < len(entries):
    st.info('Starting values: the first complete player refresh before Wednesday, 4 November is saved as that player’s baseline. Refresh before training starts; later values cannot automatically become a baseline.')
if baselines:
    st.warning('Download a competition backup after capturing starting values. Streamlit’s local storage may reset on a reboot or redeploy; keep the backup to restore them.')
if not confirmed:
    st.caption('Growth is measured from saved starting values. Competition ranks await confirmation of scoring and tie-break rules.')

overview, table, growth, details = st.tabs(['Player cards', 'Entry register', 'Growth tracker', 'Rules & prizes'])


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
            club = row.get('club') or ('No current club' if row.get('club_known') else 'Club awaiting MFL data')
            player = row.get('player') or f"Player #{row['player_id']}"
            attrs = ''.join(f'<span>{label}<b>{fmt(row.get(field))}</b></span>' for field, label in b.LABELS.items() if field != 'overall')
            st.markdown(f'''<div class="player"><a href="{row['player_url']}" target="_blank" rel="noopener noreferrer">
            <img src="https://d13e14gtps4iwl.cloudfront.net/players/v2/{row['player_id']}/photo.webp" alt="">
            <div class="owner">{esc(row['entrant'])}</div><div class="name">{esc(player)}</div>
            <div class="sub">{esc(row.get('positions') or 'Position pending')} · Age {fmt(row.get('age'))}<br>{esc(club)}</div>
            <div class="ovr">{fmt(row.get('overall'))} <small style="font-size:.75rem;color:#acb8ca">OVR</small></div>
            <div class="stats">{attrs}</div></a></div>''', unsafe_allow_html=True)
            st.caption(f"Last checked: {row.get('checked_at') or 'Not fetched yet'}")
    st.caption('Cards open the official MFL player page. Missing data appears as —; it is never treated as zero.')

with table:
    df = export_rows()
    st.dataframe(df[['Entrant', 'Player', 'Player ID', 'Age', 'Position', 'Current club', 'OVR', 'PAC', 'SHO', 'PAS', 'DRI', 'DEF', 'PHY', 'Player URL', 'Profile checked (UTC)']],
                 hide_index=True, width='stretch',
                 column_config={'Player URL': st.column_config.LinkColumn('MFL player', display_text='Open player')})
    st.download_button('Download full player register CSV', df.to_csv(index=False).encode('utf-8-sig'),
                       'grower_or_shower_season18.csv', 'text/csv')
    st.info(f'BaldSherlock: player link still needed. Mike: entry not confirmed. Neither is counted among the {len(entries)} linked entries.')
    st.caption('Hawkeye’s final selection is #337204; the earlier #467300 has been replaced.')

with growth:
    st.subheader('Player growth')
    st.write('Training XP and match XP both contribute to player development. Starting values are saved once; future refreshes update current values only.')
    df = export_rows()
    columns = ['Entrant', 'Player', 'Start OVR', 'OVR', 'OVR gain', 'Attribute gain'] + [f'{label} gain' for label in ('PAC', 'SHO', 'PAS', 'DRI', 'DEF', 'PHY')] + ['Baseline saved (UTC)']
    if confirmed and all(r.get('rank') is not None for r in data):
        columns = ['Rank'] + columns
    st.dataframe(df[columns], hide_index=True, width='stretch')
    st.caption('No starting values means no calculated gain. League ratings use explicit average ratings; an ambiguous cumulative rating is left unavailable. Ties with missing ratings remain unresolved.')
    st.download_button('Download competition backup', store.backup(), 'competitions_s18_backup.json', 'application/json')

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
