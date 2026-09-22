import grower_or_shower as gos

def main():
    conn = gos.db()
    gos.init_db(conn)
    token = gos.refresh_access_token()

    errors = []
    for player_id, owner in gos.ENTRANTS.items():
        try:
            gos.sync_player(conn, token, player_id, owner)
            print(f"✓ Synced {owner} ({player_id})")
        except Exception as exc:
            errors.append(f"{owner} ({player_id}): {type(exc).__name__}: {exc}")

    conn.close()

    if errors:
        print("\nSync errors:")
        for error in errors:
            print(f"- {error}")
        raise RuntimeError(f"{len(errors)} player sync(s) failed")

    print("\nGrower or Shower sync completed successfully.")

if __name__ == "__main__":
    main()
