# Mutual-Fund

Reports to show daily, weekly and monthly market value of my mutual funds.

See [SPECIFICATION.md](SPECIFICATION.md) for the full specification.

## What it does

Tracks 4 accounts (3 Manulife + 1 TD Canada Trust), computes market value of
holdings over time (units × NAV × FX rate), and produces:

1. **Daily report**
2. **Weekly report**
3. **Monthly report**
4. **Consolidated report** across all 4 accounts

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
| `accounts.csv` | `account_id,name,institution,currency` | Your 4 accounts |
| `transactions.csv` | `date,account_id,fund,action,units,price` | `action` = BUY/SELL |
| `nav.csv` | `date,fund,nav,currency` | NAV per unit, from your fund company |
| `fx.csv` | `date,currency,rate` | Rate **to CAD** (e.g. USD→CAD ≈ 1.37). Not needed for CAD-only funds |

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

## Report format

Each report CSV has one row per valuation date with per-account market values
(in base currency) and a final `CONSOLIDATED_<currency>` column:

```
date,Manulife RRSP (M1),Manulife TFSA (M2),Manulife Non-Reg (M3),TD Direct Investing (TD1),CONSOLIDATED_CAD
2026-07-31,21209.07,7474.77,18686.92,20184.90,67555.66
```

Weekly reports keep the last valuation date of each ISO week; monthly reports
keep the last valuation date of each month.
