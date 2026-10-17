# Mutual-Fund

Reports to show daily, weekly and monthly market value of my mutual funds.

See [SPECIFICATION.md](SPECIFICATION.md) for the full specification.

## What it does

Tracks 7 accounts across 3 institutions — Fanny (TFSA, RRSP, Non-Reg) and
KC (RRSP, TFSA) at Manulife, Joint (Non-Reg) at Carte, and TD (Non-Reg) at
TD Bank. Computes market value of holdings over time (units × NAV × FX rate),
and produces:

1. **Daily report**
2. **Weekly report**
3. **Monthly report**
4. **Consolidated report** across all 7 accounts (with per-institution subtotals)

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
| `accounts.csv` | `account_id,name,owner,type,institution,currency` | Your 7 accounts |
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
(in base currency), grouped with a subtotal per institution, and a final
`CONSOLIDATED_<currency>` column:

```
date,Fanny TFSA (F-TFSA),Fanny RRSP (F-RRSP),...,MANULIFE_TOTAL,...,CARTE_TOTAL,TD BANK_TOTAL,CONSOLIDATED_CAD
2026-07-31,10152.14,14903.22,...,48973.61,...,20184.90,33381.47,101238.55
```

Weekly reports keep the last valuation date of each ISO week; monthly reports
keep the last valuation date of each month.
