# Grower or Shower — public dashboard

A Streamlit dashboard for the WorkTheSpace MFL Grower or Shower competition.

## Entrants
Includes the original 10 entrants plus:
- hcy — 402676
- mmewse — 409412
- Ricky — 342247

## Deploy on Streamlit Community Cloud
1. Create a GitHub repository and upload the files in this folder.
2. In Streamlit Community Cloud, create an app from the repo and set the main file to `app.py`.
3. In the app's Secrets, add:
   `MFL_REFRESH_TOKEN = "YOUR_REFRESH_TOKEN"`
4. Deploy.

Do NOT upload your `.env`, database, or refresh token to GitHub.

The public dashboard automatically checks for fresh MFL data when visitors open it. It syncs at most once every 15 minutes per running app instance.
