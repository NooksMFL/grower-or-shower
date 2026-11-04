"""Signed browser recovery for both competitions; no secrets leave the server."""
import base64
import hashlib
import hmac
import json
import zlib

import streamlit as st
from streamlit_js_eval import streamlit_js_eval

KEY='mfl_season18_competitions_signed_backup_v1'


def seal(content,secret):
    compressed=zlib.compress(content.encode('utf-8'),9)
    data=base64.b64encode(compressed).decode('ascii')
    signature=hmac.new(secret.encode('utf-8'),data.encode('ascii'),hashlib.sha256).hexdigest()
    return json.dumps({'data':data,'signature':signature},separators=(',',':'))


def unseal(value,secret):
    obj=json.loads(value)
    if not isinstance(obj,dict) or not isinstance(obj.get('data'),str) or not isinstance(obj.get('signature'),str) or len(obj['data'])>8*1024*1024:
        raise ValueError('Invalid browser backup.')
    expected=hmac.new(secret.encode('utf-8'),obj['data'].encode('ascii'),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,str(obj.get('signature',''))):raise ValueError('Backup signature does not match.')
    decoder=zlib.decompressobj()
    raw=decoder.decompress(base64.b64decode(obj['data'],validate=True),10*1024*1024+1)
    if len(raw)>10*1024*1024 or decoder.unconsumed_tail or not decoder.eof:raise ValueError('Backup is too large or incomplete.')
    return raw.decode('utf-8')


def restore(store,secret):
    if not secret:return False
    reply=streamlit_js_eval(js_expressions='({ready:true,value:localStorage.getItem('+json.dumps(KEY)+')})',key='competitions_browser_read')
    ready=isinstance(reply,dict) and reply.get('ready') is True
    if not ready:return False
    if not st.session_state.get('competition_browser_restored'):
        value=reply.get('value')
        if value:
            try:store.restore(unseal(value,secret))
            except (ValueError,TypeError,KeyError,UnicodeDecodeError,zlib.error):
                st.session_state['competition_browser_error']=True
        st.session_state['competition_browser_restored']=True
    if st.session_state.get('competition_browser_error'):
        st.warning('Your browser backup could not be verified. It has been kept unchanged; use your downloaded backup to restore.')
    return ready and not st.session_state.get('competition_browser_error')


def save(store,secret,ready):
    if not ready or not secret:return
    raw=store.backup()
    value=seal(raw,secret)
    signature=hashlib.sha256(value.encode()).hexdigest()[:16]
    if signature!=st.session_state.get('competition_browser_saved'):
        expression='(()=>{try{localStorage.setItem('+json.dumps(KEY)+','+json.dumps(value)+');return {saved:true}}catch(e){return {saved:false}}})()'
        reply=streamlit_js_eval(js_expressions=expression,key='competition_browser_write_'+signature)
        if isinstance(reply,dict) and reply.get('saved') is True:
            st.session_state['competition_browser_saved']=signature
        elif isinstance(reply,dict) and reply.get('saved') is False:
            st.warning('This browser could not save a backup. Download a competition backup to keep a separate copy.')
