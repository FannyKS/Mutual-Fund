"""Aggregate valuations into daily, weekly and monthly reports and write CSVs.

Reports are written to a directory OUTSIDE src/ (spec requirement); the
default is ~/Documents/Mutual-Fund-Reports.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .loader import Account
from .valuation import Valuation

DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "Mutual-Fund-Reports"


def daily_totals(valuations: list[Valuation]) -> dict[date, dict[str, float]]:
    """{date: {account_id: market value in base currency}}."""
    out: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for v in valuations:
        out[v.date][v.account.account_id] += v.market_value
    return dict(sorted(out.items()))


def _last_date_of_iso_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def resample(
    totals: dict[date, dict[str, float]], period: str
) -> dict[date, dict[str, float]]:
    """Keep the last valuation date of each day/week/month."""
    if period == "daily":
        return totals
    buckets: dict[date, date] = {}
    for d in sorted(totals):
        if period == "weekly":
            key = _last_date_of_iso_week(d)
        elif period == "monthly":
            key = d.replace(day=1)
        else:
            raise ValueError(f"Unknown period: {period}")
        buckets[key] = d  # last date seen in the bucket wins
    return {buckets[k]: totals[buckets[k]] for k in sorted(buckets)}


def consolidate(
    totals: dict[date, dict[str, float]]
) -> dict[date, float]:
    """{date: total across all accounts}."""
    return {d: sum(accts.values()) for d, accts in totals.items()}


def write_report(
    totals: dict[date, dict[str, float]],
    accounts: dict[str, Account],
    period: str,
    output_dir: Path,
    base_currency: str = "CAD",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{period}_report.csv"
    acct_ids = list(accounts)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        header = ["date"] + [
            f"{accounts[a].name} ({a})" for a in acct_ids
        ] + [f"CONSOLIDATED_{base_currency}"]
        w.writerow(header)
        for d, accts in totals.items():
            total = sum(accts.values())
            w.writerow(
                [d.isoformat()]
                + [f"{accts.get(a, 0.0):.2f}" for a in acct_ids]
                + [f"{total:.2f}"]
            )
    return path


def write_all_reports(
    valuations: list[Valuation],
    accounts: dict[str, Account],
    output_dir: Path,
    base_currency: str = "CAD",
) -> list[Path]:
    totals = daily_totals(valuations)
    paths = []
    for period in ("daily", "weekly", "monthly"):
        paths.append(
            write_report(
                resample(totals, period),
                accounts,
                period,
                output_dir,
                base_currency,
            )
        )
    return paths


# ---------------------------------------------------------------------------
# Terminal output
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    return f"{v:>15,.2f}"


def print_summary(
    valuations: list[Valuation],
    accounts: dict[str, Account],
    base_currency: str = "CAD",
) -> None:
    totals = daily_totals(valuations)
    latest = max(totals)
    daily = resample(totals, "daily")
    weekly = resample(totals, "weekly")
    monthly = resample(totals, "monthly")
    dates = sorted(daily)
    prev = dates[-2] if len(dates) > 1 else None

    print(f"Valuation date: {latest.isoformat()}  (base currency: {base_currency})\n")
    print(f"{'Account':<32}{'Value':>15}   {'Since prev. day':>15}")
    print("-" * 66)
    for acct_id, acct in accounts.items():
        cur = daily[latest].get(acct_id, 0.0)
        if prev:
            before = daily[prev].get(acct_id, 0.0)
            pct = (cur / before - 1) * 100 if before else 0.0
            chg = f"{pct:+.2f}%"
        else:
            chg = "n/a"
        print(f"{acct.name + ' (' + acct_id + ')':<32}{_fmt(cur)}   {chg:>15}")
    print("-" * 66)
    print(f"{'CONSOLIDATED':<32}{_fmt(sum(daily[latest].values())):>15}")

    print()
    print(f"{'Period':<16}{'Value':>15}")
    print("-" * 33)
    for label, series in (
        ("Daily (prev)", _prev_of(daily, latest)),
        ("Weekly (prev)", _prev_of(weekly, latest)),
        ("Monthly (prev)", _prev_of(monthly, latest)),
    ):
        if series is None:
            continue
        d, vals = series
        print(f"{label + ' ' + d.isoformat():<16}{_fmt(sum(vals.values())):>15}")


def _prev_of(series: dict[date, dict[str, float]], latest: date):
    """Most recent entry strictly before the latest date."""
    prior = [d for d in series if d < latest]
    if not prior:
        return None
    d = max(prior)
    return d, series[d]
