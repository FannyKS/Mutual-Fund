"""Compute market value of holdings per date.

Units held are derived by replaying transactions chronologically (position
carries forward until the next buy/sell). NAVs and FX rates are forward
filled: on a date without a new observation, the last known one is used.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .loader import Account, SnapshotPosition, Transaction


@dataclass(frozen=True)
class Valuation:
    date: date
    account: Account
    fund: str
    units: float
    nav: float
    currency: str
    fx_rate: float  # to base currency
    market_value: float  # in base currency

    @property
    def market_value_native(self) -> float:
        return self.units * self.nav


def _index_by_date(observations, key=lambda x: x[0]):
    """Group sorted observations into {date: [items]} plus sorted date list."""
    by_date: dict[date, list] = defaultdict(list)
    for obs in observations:
        by_date[key(obs)].append(obs)
    dates = sorted(by_date)
    return dates, by_date


class _Series:
    """A per-key time series with forward fill on arbitrary dates."""

    def __init__(self, observations, value_of):
        # observations: list of (date, key, ...), sorted by date
        self._dates: dict[str, list[date]] = defaultdict(list)
        self._values: dict[str, list] = defaultdict(list)
        for obs in observations:
            d, key = obs[0], obs[1]
            self._dates[key].append(d)
            self._values[key].append(value_of(obs))

    def get(self, key: str, on: date):
        dates = self._dates.get(key)
        if not dates:
            return None
        i = bisect_right(dates, on) - 1
        if i < 0:
            return None
        return self._values[key][i]


def compute_valuations(
    accounts: dict[str, Account],
    transactions: list[Transaction],
    navs: list[tuple[date, str, float, str]],
    fx: list[tuple[date, str, float]],
    base_currency: str = "CAD",
    snapshot: list[SnapshotPosition] | None = None,
    strict: bool = False,
) -> tuple[list[Valuation], list[str]]:
    """Value holdings over time.

    If a snapshot is supplied it is the baseline: valuation starts at the
    snapshot date, using the units held there, plus any transactions dated
    after it. Without a snapshot, units are built by replaying all
    transactions from scratch.

    Returns (valuations, warnings).
    """
    if not navs:
        raise ValueError("No NAV data supplied — nothing to value.")

    nav_series = _Series(navs, lambda o: (o[2], o[3]))  # (nav, currency)
    fx_series = _Series(fx, lambda o: o[2])

    warnings: list[str] = []
    snapshot = snapshot or []
    if snapshot:
        baseline_date = max(p.date for p in snapshot)
        positions: dict[tuple[str, str], float] = defaultdict(float)
        for p in snapshot:
            positions[(p.account_id, p.fund)] += p.units
        pending = [t for t in transactions if t.date > baseline_date]
        skipped = len(transactions) - len(pending)
        if skipped:
            warnings.append(
                f"{skipped} transaction(s) dated on or before the snapshot "
                f"date ({baseline_date.isoformat()}) were ignored — they are "
                "assumed to be included in the snapshot."
            )
        value_dates = sorted({o[0] for o in navs if o[0] >= baseline_date})
        if not value_dates:
            raise ValueError(
                f"No NAV data on or after the snapshot date "
                f"({baseline_date.isoformat()})."
            )
    else:
        positions = defaultdict(float)
        pending = list(transactions)
        value_dates = sorted({o[0] for o in navs})

    # Replay the remaining transactions chronologically across the dates.
    txns_by_date: dict[date, list[Transaction]] = defaultdict(list)
    for t in pending:
        txns_by_date[t.date].append(t)

    txn_dates = sorted(txns_by_date)
    ti = 0

    valuations: list[Valuation] = []
    unknown_accounts: set[str] = set()
    missing_nav: set[str] = set()

    for d in value_dates:
        while ti < len(txn_dates) and txn_dates[ti] <= d:
            for t in txns_by_date[txn_dates[ti]]:
                if t.account_id not in accounts:
                    unknown_accounts.add(t.account_id)
                    continue
                sign = 1.0 if t.action == "BUY" else -1.0
                positions[(t.account_id, t.fund)] += sign * t.units
            ti += 1

        for (acct_id, fund), units in positions.items():
            if abs(units) < 1e-9:
                continue
            nav_info = nav_series.get(fund, d)
            if nav_info is None:
                missing_nav.add(fund)
                continue
            nav, currency = nav_info
            if currency == base_currency:
                rate = 1.0
            else:
                rate = fx_series.get(currency, d)
                if rate is None:
                    raise ValueError(
                        f"No FX rate for {currency} on or before {d.isoformat()} "
                        f"(fund {fund}). Add rows to fx.csv."
                    )
            account = accounts[acct_id]
            valuations.append(
                Valuation(
                    date=d,
                    account=account,
                    fund=fund,
                    units=units,
                    nav=nav,
                    currency=currency,
                    fx_rate=rate,
                    market_value=units * nav * rate,
                )
            )

    if unknown_accounts:
        raise ValueError(
            f"Transactions reference unknown account_id(s): "
            f"{', '.join(sorted(unknown_accounts))}"
        )
    if missing_nav:
        msg = (
            f"No NAV on or before the valuation date for fund(s): "
            f"{', '.join(sorted(missing_nav))}. Those holdings are excluded "
            "from the totals — add their prices (see funds.csv / fetch-nav)."
        )
        if strict:
            raise ValueError(msg)
        warnings.append(msg)

    valuations.sort(key=lambda v: (v.date, v.account.account_id, v.fund))
    return valuations, warnings


def positions_as_of(
    snapshot: list[SnapshotPosition],
    transactions: list[Transaction],
    on: date,
) -> dict[tuple[str, str], float]:
    """Units per (account, fund) as of a date, from snapshot + later buys/sells."""
    positions: dict[tuple[str, str], float] = defaultdict(float)
    baseline_date = None
    if snapshot:
        baseline_date = max(p.date for p in snapshot)
        for p in snapshot:
            positions[(p.account_id, p.fund)] += p.units
    for t in transactions:
        if baseline_date is not None and t.date <= baseline_date:
            continue
        if t.date > on:
            continue
        sign = 1.0 if t.action == "BUY" else -1.0
        positions[(t.account_id, t.fund)] += sign * t.units
    return positions
