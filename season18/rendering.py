"""Tables and downloads without Streamlit's lazy dataframe/download modules."""
import base64
import html
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def table(frame,**unused):
    if not isinstance(frame,pd.DataFrame):frame=pd.DataFrame(frame)
    frame=frame.astype(object).where(pd.notna(frame),'—')
    markup=frame.to_html(index=False,escape=True,na_rep='—',border=0,classes='mfl-data-table',
                         float_format=lambda n:f'{n:.3f}'.rstrip('0').rstrip('.'))
    st.html('''<style>
.mfl-data-wrap{overflow-x:auto;background:#fff;border:2px solid #101014;border-radius:10px;margin:.6rem 0 1rem}
.mfl-data-table{border-collapse:collapse;width:100%;font-size:.95rem;color:#101014;text-align:left}
.mfl-data-table thead{background:#101014;color:white}
.mfl-data-table th,.mfl-data-table td{padding:12px 14px;border-bottom:1px solid #dce1e3;white-space:nowrap;text-align:left!important}
.mfl-data-table tbody tr:nth-child(even){background:#f1f6f5}.mfl-data-table tbody tr:hover{background:#dbfff0}
</style><div class="mfl-data-wrap">'''+markup+'</div>')


def download(label,data,file_name,mime='application/octet-stream',**unused):
    content=data.encode('utf-8') if isinstance(data,str) else bytes(data)
    encoded=base64.b64encode(content).decode('ascii')
    # The inline iframe has no JS imports, external assets or package frontend.
    quote=lambda value:json.dumps(value).replace('<','\\u003c')
    script=('const bytes=Uint8Array.from(atob('+quote(encoded)+'),c=>c.charCodeAt(0));'
            'const link=document.getElementById("file");link.href=URL.createObjectURL(new Blob([bytes],{type:'+quote(mime)+'}));'
            'link.download='+quote(file_name)+';')
    components.html('''<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;font:600 14px Arial,sans-serif}a{display:inline-flex;align-items:center;min-height:40px;padding:0 16px;border:2px solid #101014;border-radius:6px;background:white;color:#101014;text-decoration:none;box-sizing:border-box}a:hover{background:#ff008b;color:white}
</style></head><body><a id="file">'''+html.escape(label)+'''</a><script>'''+script+'''</script></body></html>''',height=50,scrolling=False)
    if 'backup' in file_name.lower() and mime=='application/json':
        with st.expander('Backup text · copy if download is unavailable'):
            st.caption('Select all text below and save it in a .json file. It contains both competitions and saved starting values.')
            st.html('<textarea readonly aria-label="Competition backup JSON" style="width:100%;height:160px;font:12px monospace;background:white;color:#101014">'+html.escape(content.decode('utf-8'))+'</textarea>')
