"""Aggregate valuations into daily, weekly and monthly reports and write CSVs.

Reports are written to a directory OUTSIDE src/ (spec requirement); the
default is ~/Documents/Mutual-Fund-Reports.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .loader import Account, Transaction
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


def _bucket_key(d: date, period: str) -> date:
    if period == "weekly":
        return _last_date_of_iso_week(d)
    if period == "monthly":
        return d.replace(day=1)
    raise ValueError(f"Unknown period: {period}")


@dataclass(frozen=True)
class PeriodSummary:
    """One row of the weekly/monthly summary report."""

    label: str
    start: date
    end: date
    value: float
    change: float | None       # period-end value minus previous period-end value
    change_pct: float | None
    contributions: float       # net new money during the period
    market: float | None       # change minus contributions
    cost: float                # cost basis at period end
    gain: float | None         # value minus cost
    gain_pct: float | None


def _period_label(key: date, start: date, end: date, period: str) -> str:
    if period == "weekly":
        week = key.isocalendar()[1]
        return f"W{week:02d} ({start.strftime('%b %d')} - {end.strftime('%b %d')})"
    return key.strftime("%B %Y")


def period_summaries(
    valuations: list[Valuation],
    transactions: list[Transaction],
    period: str,
) -> list[PeriodSummary]:
    """Summarise every week/month: period total plus comparison vs the previous one.

    `change` is the period-end value minus the *previous* period-end value, so
    the first period has no comparison. `gain` compares the period-end value
    with the cost basis (ACB) held at that date.
    """
    value: dict[date, float] = defaultdict(float)
    cost: dict[date, float] = defaultdict(float)
    for v in valuations:
        value[v.date] += v.market_value
        cost[v.date] += v.cost or 0.0

    buckets: dict[date, list[date]] = defaultdict(list)
    for d in sorted(value):
        buckets[_bucket_key(d, period)].append(d)

    out: list[PeriodSummary] = []
    prev_value: float | None = None
    prev_end: date | None = None
    for key in sorted(buckets):
        dates = sorted(buckets[key])
        start, end = dates[0], dates[-1]
        val = value[end]
        cst = cost[end]

        # Net new money inside this period (between the previous period end and
        # this one, so weekend transactions are not lost).
        lo = prev_end if prev_end is not None else start
        contributions = sum(
            t.units * t.price * (1.0 if t.action == "BUY" else -1.0)
            for t in transactions
            if lo < t.date <= end
        )

        change = None if prev_value is None else val - prev_value
        change_pct = (
            change / prev_value * 100.0
            if (change is not None and prev_value)
            else None
        )
        market = None if change is None else change - contributions
        gain = val - cst
        gain_pct = (gain / cst * 100.0) if cst else None

        out.append(
            PeriodSummary(
                label=_period_label(key, start, end, period),
                start=start,
                end=end,
                value=val,
                change=change,
                change_pct=change_pct,
                contributions=contributions,
                market=market,
                cost=cst,
                gain=gain,
                gain_pct=gain_pct,
            )
        )
        prev_value, prev_end = val, end
    return out


def consolidate(
    totals: dict[date, dict[str, float]]
) -> dict[date, float]:
    """{date: total across all accounts}."""
    return {d: sum(accts.values()) for d, accts in totals.items()}


def _institution_groups(accounts: dict[str, Account]) -> dict[str, list[str]]:
    """{institution: [account_id, ...]} preserving first-seen order."""
    groups: dict[str, list[str]] = defaultdict(list)
    for acct_id, acct in accounts.items():
        groups[acct.institution].append(acct_id)
    return dict(groups)


def write_report(
    totals: dict[date, dict[str, float]],
    accounts: dict[str, Account],
    period: str,
    output_dir: Path,
    base_currency: str = "CAD",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{period}_report.csv"
    groups = _institution_groups(accounts)

    header = ["date"]
    for inst, acct_ids in groups.items():
        header += [f"{accounts[a].name} ({a})" for a in acct_ids]
        header.append(f"{inst.upper()}_TOTAL")
    header.append(f"CONSOLIDATED_{base_currency}")

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for d, accts in totals.items():
            row = [d.isoformat()]
            for inst, acct_ids in groups.items():
                col_total = 0.0
                for a in acct_ids:
                    v = accts.get(a, 0.0)
                    col_total += v
                    row.append(f"{v:.2f}")
                row.append(f"{col_total:.2f}")
            row.append(f"{sum(accts.values()):.2f}")
            w.writerow(row)
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


def write_summary_csvs(
    valuations: list[Valuation],
    transactions: list[Transaction],
    output_dir: Path,
    base_currency: str = "CAD",
) -> list[Path]:
    """Write weekly_summary.csv and monthly_summary.csv.

    One row per week/month: the period total and its comparison with the
    previous period, plus the gain/loss against the cost basis.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    header = [
        "period",
        "start",
        "end",
        f"market_value_{base_currency}",
        "change",
        "change_pct",
        "contributions",
        "market_movement",
        "cost",
        "gain_loss",
        "gain_loss_pct",
    ]
    paths = []
    for period in ("weekly", "monthly"):
        path = output_dir / f"{period}_summary.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            for s in period_summaries(valuations, transactions, period):
                w.writerow(
                    [
                        s.label,
                        s.start.isoformat(),
                        s.end.isoformat(),
                        f"{s.value:.2f}",
                        "" if s.change is None else f"{s.change:.2f}",
                        "" if s.change_pct is None else f"{s.change_pct:.2f}",
                        f"{s.contributions:.2f}",
                        "" if s.market is None else f"{s.market:.2f}",
                        f"{s.cost:.2f}",
                        "" if s.gain is None else f"{s.gain:.2f}",
                        "" if s.gain_pct is None else f"{s.gain_pct:.2f}",
                    ]
                )
        paths.append(path)
    return paths


def write_value_log(
    valuations: list[Valuation],
    output_dir: Path,
    base_currency: str = "CAD",
) -> Path:
    """Write a consolidated daily value log to value_log.csv.

    Columns: date,market_value,today_change,gain_loss — one row per valuation
    date (consolidated, in the base currency). It is regenerated each run from
    the full series, so it stays de-duplicated by date and always reflects the
    latest NAV history. `today_change` is blank for the first date (no prior
    day to compare with); `gain_loss` is value minus cost where cost is known.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "value_log.csv"
    agg: dict[date, list[float]] = {}
    for v in valuations:
        row = agg.setdefault(v.date, [0.0, 0.0])
        row[0] += v.market_value
        row[1] += v.cost or 0.0

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "market_value", "today_change", "gain_loss"])
        prev: float | None = None
        for d in sorted(agg):
            value, cost = agg[d]
            change = "" if prev is None else f"{value - prev:.2f}"
            w.writerow([d.isoformat(), f"{value:.2f}", change, f"{value - cost:.2f}"])
            prev = value
    return path


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
    groups = _institution_groups(accounts)
    for inst, acct_ids in groups.items():
        inst_total = 0.0
        for acct_id in acct_ids:
            acct = accounts[acct_id]
            cur = daily[latest].get(acct_id, 0.0)
            inst_total += cur
            if prev:
                before = daily[prev].get(acct_id, 0.0)
                pct = (cur / before - 1) * 100 if before else 0.0
                chg = f"{pct:+.2f}%"
            else:
                chg = "n/a"
            print(f"{'  ' + acct.name + ' (' + acct_id + ')':<32}{_fmt(cur)}   {chg:>15}")
        print(f"{'  ' + inst + ' subtotal':<32}{_fmt(inst_total)}")
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
