from __future__ import annotations

import html
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

import grower_or_shower as gos

APP_DIR = Path(__file__).resolve().parent
HEADER = APP_DIR / "grower_or_shower_header.jpg"

st.set_page_config(
    page_title="Grower or Shower",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# On Streamlit Community Cloud, keep the MFL refresh token in app Secrets.
# Locally, the existing .env file still works.
try:
    if "MFL_REFRESH_TOKEN" in st.secrets and not os.getenv("MFL_REFRESH_TOKEN"):
        os.environ["MFL_REFRESH_TOKEN"] = st.secrets["MFL_REFRESH_TOKEN"]
except Exception:
    pass

AUTO_SYNC_MINUTES = 15

st.markdown("""
<style>
    .stApp {
        background:
            radial-gradient(circle at 12% 5%, rgba(100,255,0,.09), transparent 22rem),
            radial-gradient(circle at 90% 12%, rgba(255,140,0,.08), transparent 24rem),
            #090d0b;
        color: #f4f7f5;
    }
    .block-container {max-width: 1450px; padding-top: 1.2rem;}
    h1, h2, h3 {letter-spacing: .02em;}
    .hero-wrap {
        position: relative;
        overflow: hidden;
        border-radius: 22px;
        border: 1px solid rgba(183,255,0,.24);
        background:
            radial-gradient(circle at 92% 20%, rgba(183,255,0,.16), transparent 22rem),
            linear-gradient(115deg, #101713 0%, #0b100d 58%, #151b17 100%);
        box-shadow: 0 18px 55px rgba(0,0,0,.35);
        padding: 2.25rem 2.5rem 2rem;
        margin-bottom: 1.25rem;
        min-height: 220px;
    }
    .hero-accent {
        position:absolute; left:0; top:0; bottom:0; width:7px;
        background:#b7ff00;
    }
    .hero-kicker {
        font-weight:900; color:#b7ff00; font-size:.82rem;
        letter-spacing:.18em; text-transform:uppercase;
    }
    .hero-title {
        font-weight:1000; font-size:clamp(2.8rem,6vw,5.5rem);
        line-height:.92; margin:.55rem 0 .7rem; color:#fff;
        letter-spacing:-.035em;
    }
    .hero-sub {font-size:1rem; color:#b9c2bd; font-weight:650;}
    .hero-pills {margin-top:1.15rem;}
    .hero-pill {
        display:inline-block; margin:0 .45rem .35rem 0; padding:.38rem .72rem;
        border-radius:999px; font-size:.76rem; font-weight:800;
        color:#eaf0ed; background:rgba(255,255,255,.055);
        border:1px solid rgba(255,255,255,.10);
    }
    .hero-prize {
        position:absolute; right:2.5rem; top:50%; transform:translateY(-50%);
        text-align:right;
    }
    .hero-prize-label {
        color:#8f9a94; text-transform:uppercase; letter-spacing:.14em;
        font-size:.72rem; font-weight:900;
    }
    .hero-prize-main {color:#b7ff00; font-size:1.55rem; font-weight:1000;}
    .metric-card, .player-card {
        background: linear-gradient(145deg, rgba(23,31,27,.96), rgba(10,14,12,.96));
        border: 1px solid rgba(255,255,255,.08);
        border-radius: 18px; padding: 1rem 1.05rem;
        box-shadow: 0 12px 30px rgba(0,0,0,.20);
    }
    .metric-card .big {font-size:2rem; font-weight:950; color:#b7ff00;}
    .metric-card .label {font-size:.78rem; color:#9aa49f; text-transform:uppercase; letter-spacing:.12em;}
    .rank {font-size:2.2rem; font-weight:1000; color:#b7ff00; line-height:1;}
    .owner {font-size:.76rem; color:#9aa49f; text-transform:uppercase; letter-spacing:.11em;}
    .pname {font-size:1.15rem; font-weight:900; margin:.12rem 0 .35rem;}
    .chip {display:inline-block; margin:.15rem .25rem .15rem 0; padding:.22rem .5rem; border-radius:999px;
           background:rgba(183,255,0,.09); border:1px solid rgba(183,255,0,.24); font-size:.78rem;}
    .growth {font-size:1.7rem; font-weight:1000; color:#b7ff00;}
    .muted {color:#98a19d;}
    div[data-testid="stDataFrame"] {border:1px solid rgba(255,255,255,.08); border-radius:14px; overflow:hidden;}
    .stButton > button {
        border-radius: 999px; font-weight: 800; border: 1px solid rgba(183,255,0,.35);
    }
</style>
""", unsafe_allow_html=True)


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def fmt_delta(v):
    if v is None:
        return "—"
    try:
        v = float(v)
    except Exception:
        return str(v)
    return f"+{v:g}" if v > 0 else f"{v:g}"


def get_conn():
    conn = gos.db()
    gos.init_db(conn)
    return conn


def render_hero():
    st.markdown("""
    <div class="hero-wrap">
      <div class="hero-accent"></div>
      <div class="hero-kicker">WORKTHESPACE • MFL COMMUNITY CHALLENGE</div>
      <div class="hero-title">GROWER <span style="color:#b7ff00">OR</span> SHOWER</div>
      <div class="hero-sub">Season 16 live progression tracker</div>
      <div class="hero-pills">
        <span class="hero-pill">🌱 OVR GROWTH</span>
        <span class="hero-pill">⚡ TRAINING + MATCH XP</span>
        <span class="hero-pill">🏆 AVG RATING TIEBREAK</span>
      </div>
      <div class="hero-prize">
        <div class="hero-prize-label">Prize</div>
        <div class="hero-prize-main">COMMON 50–54 PACK</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


render_hero()

def sync_if_due():
    conn = get_conn()
    row = conn.execute("SELECT MAX(captured_at) AS last_sync FROM snapshots").fetchone()
    last = row["last_sync"] if row else None
    due = True
    if last:
        try:
            stamp = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            due = datetime.now(timezone.utc) - stamp >= timedelta(minutes=AUTO_SYNC_MINUTES)
        except Exception:
            due = True

    if due:
        try:
            token = gos.refresh_access_token()
            for player_id, owner in gos.ENTRANTS.items():
                try:
                    gos.sync_player(conn, token, player_id, owner)
                except Exception:
                    pass
        except Exception as exc:
            st.session_state["sync_error"] = str(exc)

    row = conn.execute("SELECT MAX(captured_at) AS last_sync FROM snapshots").fetchone()
    conn.close()
    return row["last_sync"] if row else None


with st.spinner("Updating live MFL standings…"):
    last_sync = sync_if_due()

if last_sync:
    try:
        shown = datetime.fromisoformat(last_sync.replace("Z", "+00:00")).astimezone().strftime("%d %b %Y • %H:%M")
    except Exception:
        shown = last_sync
    st.caption(f"Live MFL data • Last updated {shown} • refreshes automatically")
elif "sync_error" in st.session_state:
    st.warning("Live update is temporarily unavailable. The last saved standings will still be shown.")

conn = get_conn()
rows = gos.leaderboard(conn)

if not rows:
    st.warning("No player snapshots yet. Click **Sync MFL now** to populate the dashboard.")
    conn.close()
    st.stop()

leader = rows[0]
best_growth = leader.get("ovr_growth")
ratings = [r["avg_rating"] for r in rows if r.get("avg_rating") is not None]
total_events = conn.execute("SELECT COUNT(*) FROM progression").fetchone()[0]
latest_event = conn.execute(
    "SELECT occurred_at, reason FROM progression WHERE occurred_at IS NOT NULL ORDER BY occurred_at DESC LIMIT 1"
).fetchone()

m1, m2, m3, m4 = st.columns(4)
cards = [
    (m1, "Current leader", leader["owner"], leader["player"]),
    (m2, "Best OVR growth", fmt_delta(best_growth), "OVR"),
    (m3, "Tracked progression", total_events, "MFL events"),
    (m4, "Entrants", len(rows), "active players"),
]
for col, label, big, small in cards:
    with col:
        st.markdown(
            f'<div class="metric-card"><div class="label">{esc(label)}</div>'
            f'<div class="big">{esc(big)}</div><div class="muted">{esc(small)}</div></div>',
            unsafe_allow_html=True,
        )

st.markdown("## 🏆 Live standings")
st.caption("Ranked by OVR improvement. Average Season 16 match rating is the tiebreaker.")

# Visual podium / cards for top entrants
card_cols = st.columns(min(3, len(rows)))
for idx, r in enumerate(rows[:3]):
    with card_cols[idx]:
        rating = f"{r['avg_rating']:.2f}" if r.get("avg_rating") is not None else "—"
        st.markdown(
            f"""<div class="player-card">
                <div class="rank">#{idx+1}</div>
                <div class="owner">{esc(r['owner'])}</div>
                <div class="pname">{esc(r['player'])}</div>
                <span class="chip">OVR {esc(r['ovr'])}</span>
                <span class="chip">Growth {esc(fmt_delta(r['ovr_growth']))}</span>
                <span class="chip">Rating {esc(rating)}</span>
                <span class="chip">{esc(r['apps'])} apps</span>
                <div style="margin-top:.6rem" class="muted">{esc(r['club'])} • {esc(r['positions'])}</div>
            </div>""",
            unsafe_allow_html=True,
        )

table = []
for i, r in enumerate(rows, 1):
    table.append({
        "#": i,
        "Owner": r["owner"],
        "Player": r["player"],
        "Age": r["age"],
        "Pos": r["positions"],
        "Club": r["club"],
        "OVR": r["ovr"],
        "OVR ↑": fmt_delta(r["ovr_growth"]),
        "Rating": r["avg_rating"],
        "Apps": r["apps"],
        "PAC ↑": fmt_delta(r["pace_growth"]),
        "SHO ↑": fmt_delta(r["shooting_growth"]),
        "PAS ↑": fmt_delta(r["passing_growth"]),
        "DRI ↑": fmt_delta(r["dribbling_growth"]),
        "DEF ↑": fmt_delta(r["defense_growth"]),
        "PHY ↑": fmt_delta(r["physical_growth"]),
    })

df = pd.DataFrame(table)
st.dataframe(df, hide_index=True, use_container_width=True, height=min(520, 76 + len(df) * 35))

st.markdown("## 📈 Player progress")
selected = st.selectbox(
    "Choose a player",
    options=[r["player_id"] for r in rows],
    format_func=lambda pid: next(f"{r['owner']} — {r['player']}" for r in rows if r["player_id"] == pid),
)
chosen = next(r for r in rows if r["player_id"] == selected)
snap = gos.latest_snapshot(conn, selected)

c1, c2 = st.columns([1, 2])
with c1:
    st.markdown(
        f"""<div class="player-card">
        <div class="owner">{esc(chosen['owner'])}</div>
        <div class="pname" style="font-size:1.6rem">{esc(chosen['player'])}</div>
        <div class="growth">{esc(fmt_delta(chosen['ovr_growth']))} OVR</div>
        <div class="muted">Current OVR {esc(chosen['ovr'])} • Age {esc(chosen['age'])}</div>
        <div style="margin-top:.7rem">{esc(chosen['club'])}</div>
        <div class="muted">{esc(chosen['positions'])}</div>
        </div>""",
        unsafe_allow_html=True,
    )

    if snap:
        stat_names = [
            ("PAC", "pace"), ("SHO", "shooting"), ("PAS", "passing"),
            ("DRI", "dribbling"), ("DEF", "defense"), ("PHY", "physical")
        ]
        stat_html = "".join(
            f'<span class="chip">{label} {esc(snap[field])} ({esc(fmt_delta(chosen[field+"_growth"]))})</span>'
            for label, field in stat_names
        )
        st.markdown(f'<div style="margin-top:.6rem">{stat_html}</div>', unsafe_allow_html=True)

with c2:
    events = conn.execute(
        """SELECT occurred_at, reason, overall, pace, shooting, passing, dribbling, defense, physical
           FROM progression WHERE player_id=? ORDER BY occurred_at, rowid""",
        (selected,),
    ).fetchall()
    if events:
        evdf = pd.DataFrame([dict(x) for x in events])
        if "occurred_at" in evdf:
            evdf["occurred_at"] = pd.to_datetime(evdf["occurred_at"], errors="coerce")
        chart_df = evdf.dropna(subset=["occurred_at", "overall"]).set_index("occurred_at")[["overall"]]
        if not chart_df.empty:
            st.line_chart(chart_df, height=260)
        evdf = evdf.rename(columns={
            "occurred_at": "Date", "reason": "Reason", "overall": "OVR",
            "pace": "PAC", "shooting": "SHO", "passing": "PAS",
            "dribbling": "DRI", "defense": "DEF", "physical": "PHY"
        })
        st.dataframe(evdf.sort_values("Date", ascending=False), hide_index=True, use_container_width=True, height=300)
    else:
        st.info("No progression events stored for this player yet.")

st.markdown("## ⚡ Latest progression")
latest = conn.execute(
    """SELECT p.*, e.owner, s.name
       FROM progression p
       JOIN entrants e ON e.player_id=p.player_id
       LEFT JOIN snapshots s ON s.id=(SELECT id FROM snapshots WHERE player_id=p.player_id ORDER BY id DESC LIMIT 1)
       ORDER BY p.occurred_at DESC, p.rowid DESC LIMIT 25"""
).fetchall()
if latest:
    ldf = pd.DataFrame([dict(x) for x in latest])
    keep = ["occurred_at", "owner", "name", "reason", "overall", "pace", "shooting", "passing", "dribbling", "defense", "physical"]
    ldf = ldf[[c for c in keep if c in ldf.columns]]
    ldf.columns = ["Date", "Owner", "Player", "Reason", "OVR", "PAC", "SHO", "PAS", "DRI", "DEF", "PHY"][:len(ldf.columns)]
    st.dataframe(ldf, hide_index=True, use_container_width=True, height=390)

with st.expander("About this tracker"):
    st.write("Standings are ranked by OVR growth, with average Season 16 match rating used as the tiebreaker.")
    st.write("Player progression is pulled from MFL and refreshed automatically.")

conn.close()

st.markdown(
    "<div style='text-align:center;color:#77817c;padding:2rem 0 1rem'>"
    "GROWER OR SHOWER • Pack. Train. Progress. Win.</div>",
    unsafe_allow_html=True,
)
