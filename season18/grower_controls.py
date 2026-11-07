"""Resumable refresh controls that unlock themselves after an API cooldown."""
import math
import time
import streamlit as st
import backend as b


@st.fragment(run_every=10)
def render(store,setting):
    import grower_live
    snapshot=grower_live.fetch()
    if snapshot:
        if st.button('↻ Load latest player update',type='primary',width='stretch',key='grower_load_live'):
            grower_live.fetch.clear()
            grower_live.apply(store,grower_live.fetch())
            st.rerun()
        st.caption('Player development is checked daily. Starting values stay fixed.')
        return
    state=store.refresh_state()
    waiting=state.get('retry_until',0)>time.time()
    partial=state.get('status') in ('paused','running')
    left,right=st.columns([1,3])
    with left:
        clicked=st.button('Continue player refresh' if partial else '↻ Refresh player data',type='primary',width='stretch',disabled=waiting,key='grower_refresh')
    with right:
        if partial:st.caption(f"{len(state.get('done',[]))} of {3*len(b.entrants())} requests saved. Continue checks the remaining requests.")
        else:st.caption('Updates profiles, player history and Season 18 results. Completed refreshes can run again after 15 minutes.')
        if waiting:st.caption(f"MFL asked us to wait. Ready in about {max(1,math.ceil((state['retry_until']-time.time())/60))} minutes; the button unlocks automatically.")
    if clicked:
        bar=st.progress(0,text='Checking entrants with MFL…')
        messages=store.refresh(b.Client(str(setting('MFL_REFRESH_TOKEN'))),lambda value:bar.progress(value,text='Checking entrants with MFL…'))
        bar.empty()
        st.session_state['refresh_messages']=messages
        st.rerun()
    if state.get('status')=='paused':
        st.warning('Refresh paused. Checked players and starting values are kept.')
        with st.expander('Refresh details',expanded=True):st.write(state.get('error') or 'Continue to finish the remaining requests.')
    elif state.get('status')=='complete':st.caption('Last full refresh: '+state.get('completed_at',''))
    messages=st.session_state.get('refresh_messages') or []
    if messages and state.get('status')!='paused':
        with st.expander('Refresh details'):
            for message in messages:st.write(message)
