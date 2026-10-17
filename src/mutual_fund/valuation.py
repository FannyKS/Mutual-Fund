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

from .loader import Account, Transaction


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
) -> list[Valuation]:
    if not navs:
        raise ValueError("No NAV data supplied — nothing to value.")

    nav_series = _Series(navs, lambda o: (o[2], o[3]))  # (nav, currency)
    fx_series = _Series(fx, lambda o: o[2])

    # Replay transactions to get units held per (account, fund) on each date.
    # positions[date] = delta applied on that date; carry forward by scanning.
    value_dates = sorted({o[0] for o in navs})

    txns_by_date: dict[date, list[Transaction]] = defaultdict(list)
    for t in transactions:
        txns_by_date[t.date].append(t)

    positions: dict[tuple[str, str], float] = defaultdict(float)
    txn_dates = sorted(txns_by_date)
    ti = 0
    active_txn_dates: set[date] = set()

    valuations: list[Valuation] = []
    unknown_accounts: set[str] = set()
    missing_nav: set[str] = set()

    for d in value_dates:
        while ti < len(txn_dates) and txn_dates[ti] <= d:
            active_txn_dates.add(txn_dates[ti])
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
        raise ValueError(
            f"No NAV on or before the valuation date for fund(s): "
            f"{', '.join(sorted(missing_nav))}"
        )

    valuations.sort(key=lambda v: (v.date, v.account.account_id, v.fund))
    return valuations
