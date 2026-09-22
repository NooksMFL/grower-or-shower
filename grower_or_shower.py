"""Grower or Shower - MFL progression tracker.

Uses the same MFL API/auth pattern as the user's existing MFL tools.
Stores current player data, progression history and Season 17 match rating in SQLite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.playmfl.com"
DB_PATH = Path(os.getenv("GROWER_DB", "grower_or_shower.db"))
SEASON_NAME = os.getenv("GROWER_SEASON", "Season 17")

BROWSER_HEADERS = {
    "Accept": "*/*",
    "Origin": "https://app.playmfl.com",
    "Referer": "https://app.playmfl.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36 Edg/152.0.0.0"
    ),
}

STAT_FIELDS = ("pace", "shooting", "passing", "dribbling", "defense", "physical")

# Current confirmed competition entries.
ENTRANTS = {
    411569: "Shootz",       # Freek Kuipers
    411974: "Nooks",        # Leonardo Silvestri
    405648: "ClarkyIsland", # Edwin Troy
    408253: "Doineann",     # Samy Bikindou
    145758: "Hawkeye",      # Gilson Teixeira
    411222: "Sherlock",     # Giovane Alves
    411483: "Minty",        # Leo Heider
    253140: "DamienV",      # Cristhian Cortez
    406518: "Rhythm",       # Lukasz Kijas
    411242: "Krystian",     # Guido Di Renzo
    402676: "hcy",
    409412: "mmewse",
    342247: "Ricky",
}


def refresh_access_token() -> str:
    refresh_token = os.getenv("MFL_REFRESH_TOKEN")
    if not refresh_token:
        raise RuntimeError("MFL_REFRESH_TOKEN is missing from .env")
    response = requests.post(
        f"{BASE_URL}/auth/refresh",
        headers=BROWSER_HEADERS,
        json={"refreshToken": refresh_token},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    access = data.get("access")
    if access is None and isinstance(data.get("data"), dict):
        access = data["data"].get("access")
    if isinstance(access, dict):
        access = access.get("token")
    if not access:
        raise RuntimeError("MFL refresh succeeded but no access token was returned")
    return access


def mfl_get(token: str, endpoint: str, params: dict | None = None) -> Any:
    headers = BROWSER_HEADERS.copy()
    headers["Authorization"] = f"Bearer {token}"
    last_error = None
    for attempt in range(3):
        r = requests.get(f"{BASE_URL}{endpoint}", headers=headers, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        last_error = RuntimeError(f"GET {endpoint}: HTTP {r.status_code} - {r.text[:300]}")
        if r.status_code not in (429, 500, 502, 503, 504):
            raise last_error
        time.sleep(0.7 * (attempt + 1))
    raise last_error or RuntimeError(f"GET {endpoint} failed")


def unwrap(data: Any, keys: tuple[str, ...] = ()) -> Any:
    """Unwrap common API envelopes without assuming one exact response shape."""
    if not isinstance(data, dict):
        return data
    for key in keys + ("data", "item", "player"):
        value = data.get(key)
        if value is not None:
            return value
    return data


def rows_from(data: Any, keys: tuple[str, ...]) -> list[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in keys + ("data", "items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
            if isinstance(value, dict):
                nested = rows_from(value, keys)
                if nested:
                    return nested
    return []


def metadata_of(player: dict) -> dict:
    meta = player.get("metadata")
    return meta if isinstance(meta, dict) else player


def player_name(player: dict) -> str:
    meta = metadata_of(player)
    first = meta.get("firstName") or player.get("firstName") or ""
    last = meta.get("lastName") or player.get("lastName") or ""
    return f"{first} {last}".strip() or str(player.get("id", "Unknown"))


def get_value(obj: dict, *keys: str) -> Any:
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None


def extract_stats(obj: dict) -> dict[str, Any]:
    meta = metadata_of(obj)
    attrs = meta.get("attributes") if isinstance(meta.get("attributes"), dict) else {}
    out = {"overall": get_value(meta, "overall", "ovr")}
    for field in STAT_FIELDS:
        out[field] = get_value(meta, field) if get_value(meta, field) is not None else get_value(attrs, field)
    return out


def event_timestamp(event: dict) -> str | None:
    for key in ("createdAt", "date", "timestamp", "created_at", "updatedAt"):
        value = event.get(key)
        if value:
            return str(value)
    return None


def event_reason(event: dict) -> str:
    return str(event.get("reasonType") or event.get("reason") or event.get("type") or "UNKNOWN")


def event_stats(event: dict) -> dict[str, Any]:
    # Progression records have previously exposed OVR/attributes either directly
    # or inside metadata/data. Keep this tolerant of both shapes.
    candidates = [event]
    for key in ("metadata", "attributes", "player", "data", "after", "newValues"):
        if isinstance(event.get(key), dict):
            candidates.append(event[key])
    result = {"overall": None, **{f: None for f in STAT_FIELDS}}
    for candidate in candidates:
        stats = extract_stats(candidate)
        for key, value in stats.items():
            if result.get(key) is None and value is not None:
                result[key] = value
    return result


def event_id(player_id: int, event: dict) -> str:
    explicit = event.get("id") or event.get("experienceId") or event.get("uuid")
    if explicit:
        return str(explicit)
    stable = json.dumps(event, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{player_id}|{stable}".encode()).hexdigest()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS entrants (
        player_id INTEGER PRIMARY KEY,
        owner TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        added_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id INTEGER NOT NULL,
        captured_at TEXT NOT NULL,
        name TEXT,
        age INTEGER,
        positions TEXT,
        club TEXT,
        overall REAL,
        pace REAL, shooting REAL, passing REAL, dribbling REAL, defense REAL, physical REAL,
        avg_rating REAL,
        appearances INTEGER,
        raw_json TEXT
    );
    CREATE TABLE IF NOT EXISTS progression (
        event_id TEXT PRIMARY KEY,
        player_id INTEGER NOT NULL,
        occurred_at TEXT,
        reason TEXT,
        overall REAL,
        pace REAL, shooting REAL, passing REAL, dribbling REAL, defense REAL, physical REAL,
        raw_json TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_snapshots_player ON snapshots(player_id, captured_at);
    CREATE INDEX IF NOT EXISTS idx_progress_player ON progression(player_id, occurred_at);
    """)
    now = datetime.now(timezone.utc).isoformat()
    for player_id, owner in ENTRANTS.items():
        conn.execute(
            "INSERT INTO entrants(player_id, owner, active, added_at) VALUES(?,?,1,?) "
            "ON CONFLICT(player_id) DO UPDATE SET owner=excluded.owner, active=1",
            (player_id, owner, now),
        )
    conn.commit()


def get_profile(token: str, player_id: int) -> dict:
    data = mfl_get(token, f"/players/{player_id}")
    player = unwrap(data)
    return player if isinstance(player, dict) else {}


def get_progression(token: str, player_id: int) -> list[dict]:
    data = mfl_get(token, f"/players/{player_id}/experiences/history")
    return rows_from(data, ("history", "experiences"))


def get_competitions(token: str, player_id: int) -> list[dict]:
    data = mfl_get(token, f"/players/{player_id}/competitions")
    return rows_from(data, ("competitions",))


def season_performance(rows: list[dict]) -> tuple[float | None, int, str]:
    total_weighted_rating = 0.0
    rating_matches = 0
    appearances = 0
    clubs: list[str] = []
    for item in rows:
        competition = item.get("competition") or {}
        season = competition.get("season") or {}
        if season.get("name") != SEASON_NAME:
            continue
        stats = item.get("stats") or {}
        matches = int(stats.get("nbMatches") or 0)
        appearances += matches
        rating = stats.get("rating")
        if isinstance(rating, (int, float)) and matches:
            total_weighted_rating += float(rating) * matches
            rating_matches += matches
        club = item.get("club") or {}
        name = club.get("name")
        if name and name not in clubs:
            clubs.append(name)
    avg = round(total_weighted_rating / rating_matches, 2) if rating_matches else None
    return avg, appearances, " / ".join(clubs)


def save_progression(conn: sqlite3.Connection, player_id: int, events: list[dict]) -> int:
    inserted = 0
    for event in events:
        stats = event_stats(event)
        before = conn.total_changes
        conn.execute(
            """INSERT OR IGNORE INTO progression
            (event_id,player_id,occurred_at,reason,overall,pace,shooting,passing,dribbling,defense,physical,raw_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id(player_id, event), player_id, event_timestamp(event), event_reason(event),
             stats["overall"], stats["pace"], stats["shooting"], stats["passing"],
             stats["dribbling"], stats["defense"], stats["physical"],
             json.dumps(event, ensure_ascii=False, default=str)),
        )
        inserted += conn.total_changes - before
    return inserted


def sync_player(conn: sqlite3.Connection, token: str, player_id: int, owner: str) -> dict:
    profile = get_profile(token, player_id)
    progression = get_progression(token, player_id)
    competitions = get_competitions(token, player_id)
    new_events = save_progression(conn, player_id, progression)

    meta = metadata_of(profile)
    stats = extract_stats(profile)
    avg_rating, appearances, competition_club = season_performance(competitions)
    active_contract = profile.get("activeContract") or {}
    active_club = active_contract.get("club") if isinstance(active_contract, dict) else {}
    club_obj = active_club or profile.get("club") or meta.get("club") or {}
    club = club_obj.get("name") if isinstance(club_obj, dict) else str(club_obj or "")
    club = club or competition_club
    positions = meta.get("positions") or []
    if isinstance(positions, str):
        positions = [positions]

    conn.execute(
        """INSERT INTO snapshots
        (player_id,captured_at,name,age,positions,club,overall,pace,shooting,passing,dribbling,defense,physical,avg_rating,appearances,raw_json)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (player_id, datetime.now(timezone.utc).isoformat(), player_name(profile), meta.get("age"),
         ", ".join(positions), club, stats["overall"], stats["pace"], stats["shooting"],
         stats["passing"], stats["dribbling"], stats["defense"], stats["physical"],
         avg_rating, appearances, json.dumps(profile, ensure_ascii=False, default=str)),
    )
    conn.commit()
    return {"owner": owner, "player": player_name(profile), "new_events": new_events, "overall": stats["overall"]}


def latest_snapshot(conn: sqlite3.Connection, player_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM snapshots WHERE player_id=? ORDER BY id DESC LIMIT 1", (player_id,)
    ).fetchone()


def first_progress_stats(conn: sqlite3.Connection, player_id: int) -> sqlite3.Row | None:
    # Prefer the MFL INITIAL record. If absent, use the oldest progression record with OVR.
    row = conn.execute(
        "SELECT * FROM progression WHERE player_id=? AND UPPER(reason)='INITIAL' AND overall IS NOT NULL "
        "ORDER BY occurred_at, rowid LIMIT 1", (player_id,)
    ).fetchone()
    if row:
        return row
    return conn.execute(
        "SELECT * FROM progression WHERE player_id=? AND overall IS NOT NULL ORDER BY occurred_at, rowid LIMIT 1",
        (player_id,),
    ).fetchone()


def leaderboard(conn: sqlite3.Connection) -> list[dict]:
    result = []
    entrants = conn.execute("SELECT * FROM entrants WHERE active=1 ORDER BY owner").fetchall()
    for ent in entrants:
        current = latest_snapshot(conn, ent["player_id"])
        if not current:
            continue
        initial = first_progress_stats(conn, ent["player_id"])
        initial_ovr = initial["overall"] if initial else None
        growth = (current["overall"] - initial_ovr) if current["overall"] is not None and initial_ovr is not None else None
        attr_growth = {}
        for field in STAT_FIELDS:
            start = initial[field] if initial else None
            now = current[field]
            attr_growth[field] = (now - start) if now is not None and start is not None else None
        result.append({
            "owner": ent["owner"], "player_id": ent["player_id"], "player": current["name"],
            "club": current["club"], "age": current["age"], "positions": current["positions"],
            "ovr": current["overall"], "ovr_growth": growth, "avg_rating": current["avg_rating"],
            "apps": current["appearances"], **{f"{k}_growth": v for k, v in attr_growth.items()},
        })
    result.sort(key=lambda r: (
        r["ovr_growth"] is not None,
        r["ovr_growth"] if r["ovr_growth"] is not None else -999,
        r["avg_rating"] if r["avg_rating"] is not None else -999,
    ), reverse=True)
    return result


def fmt_delta(value: Any) -> str:
    if value is None:
        return "—"
    return f"+{value:g}" if value > 0 else f"{value:g}"


def print_leaderboard(conn: sqlite3.Connection) -> None:
    rows = leaderboard(conn)
    if not rows:
        print("No snapshots yet. Run: py grower_or_shower.py sync")
        return
    print("\nGROWER OR SHOWER - LIVE STANDINGS")
    print("=" * 112)
    print(f"{'#':<3} {'Owner':<14} {'Player':<23} {'OVR':>4} {'Growth':>7} {'Rating':>7} {'Apps':>5}  Attribute growth")
    print("-" * 112)
    for i, r in enumerate(rows, 1):
        attrs = " ".join(f"{f[:3].upper()} {fmt_delta(r[f + '_growth'])}" for f in STAT_FIELDS)
        rating = f"{r['avg_rating']:.2f}" if r["avg_rating"] is not None else "—"
        print(f"{i:<3} {r['owner']:<14} {r['player'][:22]:<23} {str(r['ovr']):>4} {fmt_delta(r['ovr_growth']):>7} {rating:>7} {r['apps']:>5}  {attrs}")
    print("=" * 112)
    print("Ranking: OVR growth first; Season 17 average match rating is the tiebreaker.")


def print_history(conn: sqlite3.Connection, player_id: int) -> None:
    ent = conn.execute("SELECT owner FROM entrants WHERE player_id=?", (player_id,)).fetchone()
    rows = conn.execute(
        "SELECT * FROM progression WHERE player_id=? ORDER BY occurred_at, rowid", (player_id,)
    ).fetchall()
    print(f"\nProgression history - {ent['owner'] if ent else player_id} ({player_id})")
    for row in rows:
        attrs = " ".join(f"{f[:3].upper()}={row[f]}" for f in STAT_FIELDS if row[f] is not None)
        print(f"{row['occurred_at'] or 'Unknown date'} | {row['reason']:<12} | OVR={row['overall']} | {attrs}")


def sync_all() -> None:
    conn = db(); init_db(conn)
    print("Refreshing MFL access token...")
    token = refresh_access_token()
    print(f"Syncing {len(ENTRANTS)} Grower or Shower entrants...\n")
    for player_id, owner in ENTRANTS.items():
        try:
            info = sync_player(conn, token, player_id, owner)
            print(f"OK  {owner:<14} {info['player']:<24} OVR {info['overall']} | new progression events: {info['new_events']}")
        except Exception as exc:
            print(f"ERR {owner:<14} player {player_id}: {exc}")
    print_leaderboard(conn)
    conn.close()


def export_json(conn: sqlite3.Connection, path: Path) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": SEASON_NAME,
        "standings": leaderboard(conn),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Track MFL Grower or Shower player progression")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("sync", help="Pull current profiles, progression history and match ratings")
    sub.add_parser("standings", help="Show saved leaderboard")
    hist = sub.add_parser("history", help="Show one player's saved progression history")
    hist.add_argument("player_id", type=int)
    exp = sub.add_parser("export", help="Export leaderboard as JSON")
    exp.add_argument("path", nargs="?", default="grower_or_shower_standings.json")
    args = parser.parse_args()

    if args.command in (None, "sync"):
        sync_all(); return
    conn = db(); init_db(conn)
    if args.command == "standings":
        print_leaderboard(conn)
    elif args.command == "history":
        print_history(conn, args.player_id)
    elif args.command == "export":
        export_json(conn, Path(args.path))
    conn.close()


if __name__ == "__main__":
    main()
