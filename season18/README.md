# Grower or Shower & Top Boy — Season 18

A separate Streamlit app. The existing Season 17 app and Management Hub are unchanged.

## New Streamlit Community Cloud deployment

1. Visit https://share.streamlit.io/ and choose **Create app**.
2. Select repository **NooksMFL/grower-or-shower**, branch **season18-competitions**, main file **season18/app.py**.
3. Choose an available new app address, for example `mfl-grower-top-boy`.
4. Under Advanced settings → Secrets, copy `MFL_REFRESH_TOKEN` from your working Management Hub's Streamlit Secrets. Add a new private `ADMIN_PASSWORD` to allow backup restoration. Do not put either value in GitHub or chat.
5. Deploy, open **Grower or Shower**, and click **Refresh player data**.
6. Before Wednesday 4 November 2026, verify **11 / 11 starting values saved**. Download and retain the JSON competition backup under **Growth tracker**. Public CSV exports contain current and baseline attributes, clubs, ages, positions, and timestamps.

The public player endpoints are used first, matching the Management Hub's public client. If MFL requests authentication (HTTP 401), the app exchanges the refresh credential at `/auth/refresh`. A Cloudflare HTML block is reported as a server access problem, not an expired token. Credentials and raw API responses are not displayed or included in exports.

## Starting values and scoring

The first complete player snapshot before **2026-11-04 00:00 UTC** is saved once. Later refreshes cannot overwrite it. This conservative date boundary ensures no Wednesday training snapshot is silently used as starting stats. A player missing this window needs verified starting data from the organiser; the app will not substitute a post-training baseline. Both training XP and match XP count toward attribute development.

Growth displays as soon as baseline and current attributes are available. Official ranks remain disabled until the organiser confirms scoring. After confirmation, set `SCORING_CONFIRMED = true` in Streamlit Secrets to enable OVR gain → sum of six attribute gains → explicit average Season 18 league rating. All linked players must have complete baseline/current values before ranks appear. Missing ratings leave final ties unresolved; no entrant is awarded a win based on missing data. Baseline capture is independent of scoring confirmation.

## Data retention

The dedicated `competitions_s18.sqlite3` holds profiles, complete starting values, history and competition records. Streamlit Community Cloud filesystem storage is ephemeral: keep JSON backups outside the app, especially immediately after starting values are captured. On restart/redeploy, use the organiser password and **Restore missing records** to import the saved backup. Restoration never replaces an existing baseline. A file path on a persistent volume can be configured using `COMPETITIONS_DB` on other hosts. The backup contains public player data only, no secrets. Shared refresh attempts are limited to once per 15 minutes per app database; failures retain previous data and show warnings and per-record timestamps.

Top Boy is a clearly marked placeholder until entrants and scoring rules are supplied. There are no invented entries or results. BaldSherlock's missing player link and Mike's unconfirmed entry are documented separately.

## Local run and checks

```sh
python -m pip install -r season18/requirements.txt
python -m streamlit run season18/app.py
python -m unittest discover -s season18/tests -v
```

Configure local credentials via environment variables or ignored `.streamlit/secrets.toml`. No `.env`, token, wallet data or prior-season database is bundled. Live MFL requests from the development cloud were blocked by Cloudflare, so deployed connectivity must be verified with the refresh button on Streamlit.
