# Mutual Fund Specification
To create a repository for my mutual fund market value reports.

## Accounts (10 total), across 3 institutions

**Manulife** (8):

1. Fanny — TFSA
2. Fanny — RRSP
3. Fanny — Spousal RRSP
4. Fanny — Non-Registered
5. KC — RRSP
6. KC — Spousal RRSP
7. KC — LIRA
8. KC — TFSA

**Carte** (1):

9. Joint — Non-Registered

**TD Bank** (1):

10. TD — Non-Registered

Accounts may hold different funds, or the same fund in different accounts
(the same fund can appear in multiple accounts).

## Data

I will provide the CSVs of my holdings (accounts, transactions, NAVs, FX rates).

**How data is provided:**

1. An initial **holdings snapshot** (`snapshot.csv`) — what I hold today,
   including the book value / adjusted cost base (`cost`) where the statement
   reports it (Manulife: `ACB`; TD: `Book Cost`).
2. After that, only **changes** (buys/sells) are submitted whenever they happen
   (`mutual-fund add ...`, which appends to `transactions.csv`). A buy adds to
   the cost basis; a sell removes it proportionally.
3. A fresh snapshot can be submitted later and reconciled against the recorded
   changes (`mutual-fund reconcile --snapshot ...`, preserving `cost`).

**NAV data** is fetched automatically from public sources each day
(`mutual-fund fetch-nav`), driven by `funds.csv`. Supported sources: Barchart
(`barchart`, by symbol like `MGF1916.CF` — includes full daily history), Fidelity
Canada (`fidelity`, by fund code), Manulife Investment Management (`manulife`,
by fund code — includes full history), The Globe and Mail (`globe`, by symbol
like `TDB619.CF`), Yahoo Finance (`yahoo`, by ticker) and generic HTML/CSV
pages. Foreign-currency NAVs are converted with daily rates from the Bank of
Canada (`mutual-fund fetch-fx`). The daily report runs the next morning, after
the previous day's NAVs are published.

A precise NAV can be pinned in `nav_overrides.csv` (overrides `nav.csv`, and
survives future fetches) where a public feed only publishes a rounded price.
Reports may also start **before** the baseline with `report --from YYYY-MM-DD`;
for those earlier dates the snapshot's units are held constant (and a warning
is printed), giving a full-period view of today's holdings.

## Reports

Reports on each account, plus a consolidated report across all accounts:

1. Daily report
2. Weekly report
3. Monthly report
4. Consolidated report (all 10 accounts)
5. Weekly summary — one row per week: fund total plus comparison with the
   previous week (change, %, contributions vs market movement) and gain/loss
   against cost
6. Monthly summary — the same, one row per month

Each is written as **CSV** and as a self-contained **HTML** page; an HTML
**dashboard** (`dashboard.html`) gives the at-a-glance view (cards, allocation
donut, value-by-account bars, value-history chart, holdings table). Where a
cost basis is available, reports also show **gain/loss**.

Reports should be written to my computer, not under SRC
(default: ~/Documents/Mutual-Fund-Reports).
