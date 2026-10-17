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

Reports are CSV files written to `~/Documents/Mutual-Fund-Reports/`
(outside `src/`, per the specification), plus an optional terminal summary.

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
| `funds.csv` | `fund,name,currency,source,identifier,pattern` | Where each fund's NAV comes from |
| `snapshot.csv` | `date,account_id,fund,units` | Holdings baseline (see workflow below) |
| `fx.csv` | `date,currency,rate` | Rate **to CAD**. Optional if all funds are CAD |

- `data/` is gitignored — your real financial data is never committed.
- `examples/` contains dummy sample data; copy it to `data/` to try things out.
- NAVs and FX rates are forward filled: on a date without a new value, the
  last known one is used (markets are closed on weekends/holidays).

## Usage

```bash
# Terminal summary of the latest value (per-account + consolidated)
mutual-fund show

# Write daily/weekly/monthly CSV reports (default: ~/Documents/Mutual-Fund-Reports)
mutual-fund report

# Custom output directory / data directory / base currency
mutual-fund report --out ~/MyReports
mutual-fund --data examples show
mutual-fund --base USD report
```

Without installing: `PYTHONPATH=src python3 -m mutual_fund show`

Add `--strict` to fail (instead of skipping) when a fund has no NAV yet.

## Reading screenshots (OCR)

Holdings often arrive as phone screenshots. `scripts/ocr.swift` extracts the
text with the macOS Vision framework (no installs needed):

```bash
swift scripts/ocr.swift Holdings/Fanny/*.jpeg
```

Then transcribe fund code, units and NAV into `snapshot.csv` / `nav.csv`.
(The `.xlsx` exports, like Carte's, can be read directly.)

## NAVs: automatic daily fetch

Fund NAVs are public data — no account access needed — so they are fetched
automatically. Map each fund to a source in `data/funds.csv`:

```
fund,name,currency,source,identifier,pattern
MIF001,Manulife Monthly High Income,CAD,yahoo,0P0000XXXX.TO,
TDB900,TD Canadian Bond,CAD,html,https://example.com/td/tdb900,"\$([0-9]+\.[0-9]+)"
```

Sources: `yahoo` (ticker), `html` (scrape a public fund page with a regex),
`csv` (a public CSV URL). Then:

```bash
mutual-fund fetch-nav              # fetch the last year, merge into nav.csv
mutual-fund fetch-nav --since 2026-01-01
mutual-fund fetch-nav --dry-run
```

Useful for back-filling history: `fetch-nav --since 2020-01-01` gives you
daily NAVs going back years, so weekly/monthly reports cover past dates.
(Your **holdings** still come from snapshots — those can't be fetched.)

## Daily automation

`scripts/daily.sh` fetches NAVs, then writes the reports and logs to
`~/Documents/Mutual-Fund-Reports/daily.log`. Run it each morning, after the
previous day's NAVs are published (mutual fund NAVs are final only after
market close).

**macOS (launchd)** — edit the path in `scripts/com.mutual-fund.daily.plist`
(replace `REPO_DIR`), then:

```bash
cp scripts/com.mutual-fund.daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mutual-fund.daily.plist
```

It runs at 07:00 daily. **cron** alternative:

```
0 7 * * * MUTUAL_FUND_DATA=$HOME/src/Mutual-Fund/data /Users/fannyng/src/Mutual-Fund/scripts/daily.sh
```

## Workflow: snapshot + changes

You send a **holdings snapshot** (what you hold today). After that, you only
send **changes** (buys/sells). The tool keeps the running position and can
check a new snapshot against your records.

**Step 1 — initial snapshot.** Save your holdings export as `data/snapshot.csv`:

```
date,account_id,fund,units
2026-10-16,F-TFSA,MIF001,400.0000
2026-10-16,F-RRSP,MIF002,250.0000
```

That date becomes the baseline; reports start from it and grow daily.

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
