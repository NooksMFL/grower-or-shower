"""Progress table and player cards using preserved Season 18 starting values."""
import html
import backend as b


def fmt(value):
    return f'{value:g}' if isinstance(value,(int,float)) else '—'


def gain(value):
    if value is None:return '<span class="gos-gain gos-unknown" title="Starting value unavailable">—</span>'
    style='up' if value>0 else 'down' if value<0 else 'flat'
    label=f'{value:+g}' if value else '±0'
    return f'<span class="gos-gain gos-{style}" title="Change since starting value">{label}</span>'


def card_html(row):
    esc=lambda v:html.escape(str(v),quote=True)
    player=row.get('player') or f"Player #{row['player_id']}"
    club=row.get('club') or ('No current club' if row.get('club_known') else 'Club awaiting MFL data')
    gains=row.get('gains',{})
    attrs=''.join(f'<div class="gos-card-attribute"><span>{label}</span><b>{fmt(row.get(field))}</b>{gain(gains.get(field))}</div>' for field,label in b.LABELS.items() if field!='overall')
    return f'''<div class="player gos-player"><a href="{esc(row['player_url'])}" target="_blank" rel="noopener noreferrer">
<img src="https://d13e14gtps4iwl.cloudfront.net/players/v2/{int(row['player_id'])}/photo.webp" alt="{esc(player)}">
<div class="owner">{esc(row['entrant'])}</div><div class="name">{esc(player)}</div>
<div class="sub">{esc(row.get('positions') or 'Position pending')} · Age {fmt(row.get('age'))}<br>{esc(club)}</div>
<div class="ovr">{fmt(row.get('overall'))} <small>OVR</small> {gain(gains.get('overall'))}</div>
<div class="stats">{attrs}</div></a></div>'''


def progress_table_html(rows):
    esc=lambda v:html.escape(str(v),quote=True)
    ordered=sorted(rows,key=lambda r:(r.get('gains',{}).get('overall') is None,-(r.get('gains',{}).get('overall') or 0),-(r.get('attribute_gain') or 0),r['entrant'].casefold()))
    body=[]
    for row in ordered:
        pid=int(row['player_id']);gains=row.get('gains',{})
        attrs=''.join(f'<td class="gos-attribute">{gain(gains.get(f))}</td>' for f in b.FIELDS[1:])
        body.append(f'''<tr><th scope="row" class="gos-entrant">{esc(row['entrant'])}</th><td class="gos-player-cell"><a href="{esc(row['player_url'])}" target="_blank" rel="noopener noreferrer"><img src="https://d13e14gtps4iwl.cloudfront.net/players/v2/{pid}/photo.webp" alt="" loading="lazy"><span><strong>{esc(row.get('player') or f'Player #{pid}')}</strong><small>{esc(row['entrant'])}</small></span></a></td><td class="gos-current">{fmt(row.get('overall'))}</td><td class="gos-ovr-gain">{gain(gains.get('overall'))}</td><td class="gos-total">{gain(row.get('attribute_gain'))}</td>{attrs}</tr>''')
    attrs=''.join(f'<th class="gos-attribute" scope="col">{label}</th>' for label in list(b.LABELS.values())[1:])
    return '<div class="gos-progress-wrap"><div class="gos-progress-title"><strong>PLAYER PROGRESS</strong><span>SEASON 18</span></div><table class="gos-progress" aria-label="Grower or Shower player progress"><thead><tr><th class="gos-entrant" scope="col">ENTRANT</th><th scope="col">PLAYER</th><th class="gos-current" scope="col">OVR</th><th scope="col">OVR +/−</th><th scope="col">ATTR +/−</th>'+attrs+'</tr></thead><tbody>'+''.join(body)+'</tbody></table></div>'
