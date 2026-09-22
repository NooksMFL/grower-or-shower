import grower_or_shower as gos
conn=gos.get_conn()
token=gos.refresh_access_token()
errors=[]
for player_id,owner in gos.ENTRANTS.items():
    try:
        gos.sync_player(conn,token,player_id,owner)
    except Exception as exc:
        errors.append(f"{owner} ({player_id}): {type(exc).__name__}: {exc}")
conn.close()
if errors:
    raise RuntimeError("\n".join(errors))
