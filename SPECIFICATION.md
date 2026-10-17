# Mutual Fund Specification
To create a repository for my mutual fund market value reports.

## Accounts (7 total), across 3 institutions

**Manulife** (5):

1. Fanny — TFSA
2. Fanny — RRSP
3. Fanny — Non-Registered
4. KC — RRSP
5. KC — TFSA

**Carte** (1):

6. Joint — Non-Registered

**TD Bank** (1):

7. TD — Non-Registered

Accounts may hold different funds, or the same fund in different accounts
(the same fund can appear in multiple accounts).

## Data

I will provide the CSVs of my holdings (accounts, transactions, NAVs, FX rates).

**How data is provided:**

1. An initial **holdings snapshot** (`snapshot.csv`) — what I hold today.
2. After that, only **changes** (buys/sells) are submitted whenever they happen
   (`mutual-fund add ...`, which appends to `transactions.csv`).
3. A fresh snapshot can be submitted later and reconciled against the recorded
   changes (`mutual-fund reconcile --snapshot ...`).

**NAV data** is fetched automatically from public sources each day
(`mutual-fund fetch-nav`), driven by `funds.csv`. The daily report runs the
next morning, after the previous day's NAVs are published.

## Reports

Reports on each account, plus a consolidated report across all accounts:

1. Daily report
2. Weekly report
3. Monthly report
4. Consolidated report (all 7 accounts)

Reports should be written to my computer, not under SRC
(default: ~/Documents/Mutual-Fund-Reports).
