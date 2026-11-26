# Formatted workbook with tabs

[**Download Excel workbook: All prices + Patient + MID + Quick sell + supporting tabs**](https://github.com/NooksMFL/grower-or-shower/raw/refs/heads/main/valuations/2026-11-22/Nooks_All_Listing_Prices_with_Tabs.xlsx)

Open this **.xlsx file in Excel** for the coloured, filtered tables and 12 tabs. The All prices sheet puts **Patient price, MID price and Quick sell price** side by side. CSV files are plain text and cannot hold tabs or formatting. Prices remain based on the 22 November 2026 snapshot.

---

# Agency valuations

## Download one CSV with all three prices

[**Download all listing prices: Patient, MID and Quick sell**](https://github.com/NooksMFL/grower-or-shower/raw/refs/heads/main/valuations/2026-11-22/all_listing_prices.csv)

The first five columns are **Player ID, Player, Patient price, MID price, Quick sell price**. The file includes all 436 CSV players; two lack supported prices and are left blank for manual review. Prices use the 22 November 2026 market snapshot. Patient is the upper-quartile ask rounded up; MID is the median ask rounded up; Quick sell is the lower-quartile ask rounded down, with a minimum of 1. These are marketplace asking suggestions, not MFL's instant Quick Sell feature or guaranteed sale proceeds.

---

# Agency valuations

## 22 November 2026

- [Download the Excel workbook](https://github.com/NooksMFL/grower-or-shower/raw/refs/heads/main/valuations/2026-11-22/Nooks_Agency_Valuations_2026-11-22.xlsx)
- [Download the complete ZIP: Excel and CSV evidence](https://github.com/NooksMFL/grower-or-shower/raw/refs/heads/main/valuations/2026-11-22/Nooks_Agency_Valuations_2026-11-22.zip)

The workbook covers 436 players from the supplied CSV. It includes 434 suggested patient-sale asking prices, two unpriced players for review, comparable listing evidence, retirement warnings, and 57 additional owned no-club players outside the CSV.

These are asking-price estimates from 4,000 sampled active listings, not completed-sale values or guaranteed proceeds. Review low-confidence prices and retirement timing before listing. No marketplace listings were created.

## Alternative marketplace listing prices

Based on the same **22 November 2026** market snapshot; created 26 November. These are not refreshed market valuations.

- [Download Half patient CSV](https://github.com/NooksMFL/grower-or-shower/raw/refs/heads/main/valuations/2026-11-22/half_patient_listing_prices.csv): median comparable ask, rounded up. 434 players; suggested asking subtotal 5,549 in MFL displayed marketplace price amounts.
- [Download Quick sell CSV](https://github.com/NooksMFL/grower-or-shower/raw/refs/heads/main/valuations/2026-11-22/quick_sell_listing_prices.csv): 25th-percentile comparable ask, rounded down with a minimum of 1. 434 players; suggested asking subtotal 4,289.
- [Manual-review players CSV](https://github.com/NooksMFL/grower-or-shower/raw/refs/heads/main/valuations/2026-11-22/listing_prices_manual_review.csv): the two players without sufficient evidence, excluded from both priced files.

Use the `listing_price` column. These are marketplace listing suggestions, not MFL's instant Quick Sell feature and not a claimed supported bulk-import format. Every row retains its confidence flag and source date. Review low-confidence prices and retirement warnings before listing. The API omits currency; retain MFL displayed price units and confirm the currency and payout in MFL. Subtotals are gross asking prices, not expected sale proceeds. No players have been listed.
