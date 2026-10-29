# Mutual-Fund

Reports to show daily, weekly and monthly market value of my mutual funds.

See [SPECIFICATION.md](SPECIFICATION.md) for the full specification.

## What it does

Tracks 10 accounts across 3 institutions:

**Manulife (8)** — Fanny: TFSA, RRSP, Spousal RRSP, Non-Reg; KC: RRSP,
Spousal RRSP, LIRA, TFSA
**Carte (1)** — Joint Non-Registered
**TD Bank (1)** — TD Non-Registered

Computes market value of holdings over time (units × NAV × FX rate), and
produces:

1. **Daily report**
2. **Weekly report**
3. **Monthly report**
4. **Consolidated report** across all accounts (with per-institution subtotals)
5. **Dashboard** — an HTML overview (cards, allocation donut, value-by-account
   bars, value-history chart, holdings table with gain/loss)

Reports are written to `~/Documents/Mutual-Fund-Reports/` (outside `src/`, per
the specification): the four reports as CSV, plus `dashboard.html`, an HTML
version of each period report (`daily_report.html`, `weekly_report.html`,
`monthly_report.html`), and two multi-period summaries
(`weekly_summary.html`, `monthly_summary.html`). A terminal summary is also
printed.

When a statement reports a **cost basis (ACB / book value)**, holdings also
show **gain/loss** and a **Cost (ACB)** total. Accounts without a cost basis
are reported as `n/a` and flagged with a `*` in the totals.

## Setup

Python 3.9+, no external dependencies.

```bash
pip install -e .
```

## Data (CSV files in `data/`)

| File | Columns | Notes |
|---|---|---|
| `accounts.csv` | `account_id,name,owner,type,institution,currency` | Your accounts |
| `transactions.csv` | `date,account_id,fund,action,units,price` | Changes only; optional |
| `nav.csv` | `date,fund,nav,currency` | NAV per unit (auto-fetched, see below) |
| `nav_overrides.csv` | `date,fund,nav,currency` | Optional precise NAVs that win over `nav.csv` |
| `funds.csv` | `fund,name,currency,source,identifier,pattern` | Where each fund's NAV comes from |
| `snapshot.csv` | `date,account_id,fund,units,cost` | Holdings baseline; `cost` = ACB/book value (optional) |
| `fx.csv` | `date,currency,rate` | Rate **to CAD**. Optional if all funds are CAD |

- `data/` is gitignored — your real financial data is never committed.
- `examples/` contains dummy sample data; copy it to `data/` to try things out.
- NAVs and FX rates are forward filled: on a date without a new value, the
  last known one is used (markets are closed on weekends/holidays).
- `nav_overrides.csv` is optional. Any row in it overrides the same
  `(date, fund)` in `nav.csv` and is never touched by `fetch-nav` — use it to
  pin a precise NAV where a public feed only publishes a rounded one.
- `snapshot.csv`'s `cost` column is optional. Leave it blank for holdings
  whose book value you don't have (gain/loss then shows `n/a`). A BUY/SELL
  recorded with `add` adjusts the cost basis automatically (a sale removes
  cost proportionally).

## Usage

```bash
# Terminal summary of the latest value (per-account + consolidated)
mutual-fund show

# Write daily/weekly/monthly reports + HTML dashboard (default: ~/Documents/Mutual-Fund-Reports)
mutual-fund report

# Write only the CSV reports (skip the HTML files)
mutual-fund report --no-html

# Start the series earlier than the snapshot (see "Starting before the snapshot")
mutual-fund report --from 2026-01-01
mutual-fund show --from 2026-01-01

# Custom output directory / data directory / base currency
mutual-fund report --out ~/MyReports
mutual-fund --data examples show
mutual-fund --base USD report
```

Without installing: `PYTHONPATH=src python3 -m mutual_fund show`

Add `--strict` to fail (instead of skipping) when a fund has no NAV yet.

### Starting before the snapshot

By default reports start at your snapshot date (the baseline). `--from` lets
the series start earlier — useful for a full-year view:

```bash
mutual-fund report --from 2026-01-01
```

For dates before the snapshot the tool holds the snapshot's units constant
(there is no earlier holdings data to use), so it answers "what would I be
worth if I had held today's units?" — buys/sells and reinvested distributions
before the snapshot are not reflected. A warning is printed. Fetch NAV history
first so the earlier dates have prices (`fetch-nav` covers this automatically).

## Reading screenshots (OCR)

Holdings often arrive as phone screenshots. `scripts/ocr.swift` extracts the
text with the macOS Vision framework (no installs needed):

```bash
swift scripts/ocr.swift Holdings/Fanny/*.jpeg
```

Then transcribe fund code, units, NAV **and ACB** (cost) into
`snapshot.csv` / `nav.csv`. Manulife statements label it `ACB`; TD labels it
`Book Cost`. (The `.xlsx` exports, like Carte's, can be read directly, but
may not include a cost basis.)

## NAVs: automatic daily fetch

Fund NAVs are public data — no account access needed — so they are fetched
automatically. Map each fund to a source in `data/funds.csv`:

```
fund,name,currency,source,identifier,pattern
MIF001,Manulife Monthly High Income,CAD,yahoo,0P0000XXXX.TO,
TDB900,TD Canadian Bond,CAD,html,https://example.com/td/tdb900,"\$([0-9]+\.[0-9]+)"
MGF1916,Manulife Strategic Dividend Bundle GIF,CAD,barchart,MGF1916.CF,
```

Sources: `barchart` (Barchart EOD series behind Globe and Mail fund pages —
symbol like `MGF1916.CF`; **includes full daily history**), `yahoo` (ticker),
`fidelity` (Fidelity Canada fund code), `manulife` (Manulife fund code, e.g.
MGF1916 — includes full NAV history), `globe` (Globe and Mail symbol, e.g.
TDB619.CF; latest only), `html` (scrape a public fund page with a regex),
`csv` (a public CSV URL). Then:

```bash
mutual-fund fetch-nav              # fetch the last year, merge into nav.csv
mutual-fund fetch-nav --since 2026-01-01
mutual-fund fetch-nav --dry-run
```

Foreign-currency funds are converted with rates from the Bank of Canada:

```bash
mutual-fund fetch-fx               # writes data/fx.csv (USD/CAD, EUR/CAD, ...)
```

`fetch-fx` defaults to the currencies used by `funds.csv`, so it only fetches
what you actually need.

Useful for back-filling history: `fetch-nav --since 2020-01-01` gives you
daily NAVs going back years, so weekly/monthly reports cover past dates.
(Your **holdings** still come from snapshots — those can't be fetched.)

## Daily automation

`scripts/daily.sh` fetches NAVs and FX rates, then writes the reports and logs
to `~/Documents/Mutual-Fund-Reports/daily.log`. Run it each morning, after the
previous day's NAVs are published (mutual fund NAVs are final only after
market close).

**macOS (launchd)** — edit the path in `scripts/com.mutual-fund.daily.plist`
(replace `REPO_DIR`), then:

```bash
cp scripts/com.mutual-fund.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mutual-fund.daily.plist
```

It runs at 07:00 daily. Reports start at `MUTUAL_FUND_FROM` (default
`2026-01-01`; set it to change the report window). **cron** alternative:

```
0 7 * * * MUTUAL_FUND_DATA=$HOME/src/Mutual-Fund/data /Users/fannyng/src/Mutual-Fund/scripts/daily.sh
```

**If a run logs `Operation not permitted` for a file under `~/Documents`**:
macOS ties a launchd job's write access to files the job created itself. Delete
that file (or the whole `~/Documents/Mutual-Fund-Reports` directory) and run
the job once more — let the job create the files. It works from then on, even
if you later edit them by hand:

```bash
launchctl kickstart -k gui/$(id -u)/com.mutual-fund.daily
```

## Workflow: snapshot + changes

You send a **holdings snapshot** (what you hold today). After that, you only
send **changes** (buys/sells). The tool keeps the running position and can
check a new snapshot against your records.

**Step 1 — initial snapshot.** Save your holdings export as `data/snapshot.csv`:

```
date,account_id,fund,units,cost
2026-10-16,F-TFSA,MIF001,400.0000,9000.00
2026-10-16,F-RRSP,MIF002,250.0000,
```

That date becomes the baseline; reports start from it and grow daily (use
`report --from YYYY-MM-DD` to start the series earlier — see "Starting before
the snapshot").

**Step 2 — record a change** (a buy or sell) whenever one happens:

```bash
mutual-fund add --account F-RRSP --fund MIF001 --units 200 --price 26.50
mutual-fund add --account J-NONREG --fund MIF001 --units 150 --price 27.10 --action SELL
# optional --date YYYY-MM-DD (defaults to today)
```

This appends one row to `data/transactions.csv`. That's the whole "sending a
change" step — one command, no file editing.

**Step 3 — verify against a fresh snapshot** (recommended after a few months,
or whenever you re-download holdings). Save the new export anywhere and run:

```bash
mutual-fund reconcile --snapshot ~/Downloads/new_holdings.csv

# if everything matches, make it the new baseline:
mutual-fund reconcile --snapshot ~/Downloads/new_holdings.csv --accept
```

`reconcile` compares each account/fund's units (snapshot vs. snapshot + your
recorded changes) and reports differences, so a missed or double-counted
transaction is caught before it corrupts your history.

## Report format

Each report CSV has one row per valuation date with per-account market values
(in base currency), grouped with a subtotal per institution, and a final
`CONSOLIDATED_<currency>` column:

```
date,Fanny TFSA (F-TFSA),Fanny RRSP (F-RRSP),...,MANULIFE_TOTAL,...,CARTE_TOTAL,TD BANK_TOTAL,CONSOLIDATED_CAD
2026-07-31,10152.14,14903.22,...,48973.61,...,20184.90,33381.47,101238.55
```

Weekly reports keep the last valuation date of each ISO week; monthly reports
keep the last valuation date of each month.

### Value log

`report` also writes `value_log.csv` — a consolidated one-row-per-day log:

```
date,market_value,today_change,gain_loss
2026-10-15,2446536.18,14571.80,586806.93
2026-10-16,2437749.54,-8786.64,578020.29
```

It is regenerated from the full series on each run (so it stays de-duplicated
by date and picks up any NAV back-fill), covering all accounts in the base
currency. `today_change` is blank on the first date; `gain_loss` uses the cost
basis where known.

### Weekly and monthly summaries

`weekly_summary.csv` / `monthly_summary.csv` have **one row per week/month**
covering the whole report window, so periods can be compared side by side:

```
period,start,end,market_value_CAD,change,change_pct,contributions,market_movement,cost,gain_loss,gain_loss_pct
W43 (Oct 19 - Oct 23),2026-10-19,2026-10-23,2422219.52,,,0.00,,1859729.25,562490.27,30.25
W44 (Oct 26 - Oct 28),2026-10-26,2026-10-28,2442857.61,20638.09,0.85,0.00,20638.09,1859729.25,583128.36,31.36
```

- `market_value_<currency>` — the fund total at the end of that period.
- `change` / `change_pct` — end-of-period total minus the **previous**
  period's total (blank for the first period).
- `contributions` — net buys/sells during the period; `market_movement` is
  `change` minus contributions.
- `gain_loss` / `gain_loss_pct` — the period-end total minus the cost basis.

Unlike `weekly_report.csv` (current week-to-date only), the summaries keep
every period in the report window. The window follows `--from`; with the
launchd job it is pinned to your inception date via `MUTUAL_FUND_FROM`.

### HTML output

Alongside the CSVs, `report` writes a self-contained, dark-themed set of HTML
files (no external assets, so they open anywhere):

| File | Contents |
|---|---|
| `dashboard.html` | Cards (value, today's change, gain/loss, cost), allocation donut, value-by-account bars, value-history chart, holdings table |
| `daily_report.html` | Latest day: start/end value, change, split into contributions vs market movement, by account, by fund, daily rows |
| `weekly_report.html` | Current week-to-date, same layout |
| `monthly_report.html` | Current month-to-date, same layout |
| `weekly_summary.html` | Every week in the window: total, change vs prior week, % and gain/loss vs cost, plus a value-by-week chart |
| `monthly_summary.html` | Every month in the window, same layout |

"Contributions" is the net of recorded buys/sells in the period; the rest of
the change is labelled "market". Use `--no-html` to skip these files.
