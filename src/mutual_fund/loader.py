"""Load CSV inputs: accounts, transactions, NAVs and FX rates."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Account:
    account_id: str
    name: str
    institution: str
    currency: str


@dataclass(frozen=True)
class Transaction:
    date: date
    account_id: str
    fund: str
    action: str  # BUY or SELL
    units: float
    price: float


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing data file: {path}\n"
            f"Copy the files from examples/ into {path.parent} and edit them "
            "with your real data."
        )
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_accounts(data_dir: Path) -> dict[str, Account]:
    rows = _read_csv(data_dir / "accounts.csv")
    accounts = {}
    for r in rows:
        acct = Account(
            account_id=r["account_id"].strip(),
            name=r["name"].strip(),
            institution=r["institution"].strip(),
            currency=r["currency"].strip().upper(),
        )
        accounts[acct.account_id] = acct
    if not accounts:
        raise ValueError(f"No accounts found in {data_dir / 'accounts.csv'}")
    return accounts


def load_transactions(data_dir: Path) -> list[Transaction]:
    rows = _read_csv(data_dir / "transactions.csv")
    txns = []
    for r in rows:
        txns.append(
            Transaction(
                date=date.fromisoformat(r["date"].strip()),
                account_id=r["account_id"].strip(),
                fund=r["fund"].strip(),
                action=r["action"].strip().upper(),
                units=float(r["units"]),
                price=float(r["price"]),
            )
        )
    txns.sort(key=lambda t: t.date)
    return txns


def load_navs(data_dir: Path) -> list[tuple[date, str, float, str]]:
    """Return NAV observations as (date, fund, nav, currency), sorted by date."""
    rows = _read_csv(data_dir / "nav.csv")
    out = [
        (
            date.fromisoformat(r["date"].strip()),
            r["fund"].strip(),
            float(r["nav"]),
            r["currency"].strip().upper(),
        )
        for r in rows
    ]
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def load_fx(data_dir: Path) -> list[tuple[date, str, float]]:
    """Return FX rates as (date, currency, rate_to_CAD), sorted by date."""
    rows = _read_csv(data_dir / "fx.csv")
    out = [
        (
            date.fromisoformat(r["date"].strip()),
            r["currency"].strip().upper(),
            float(r["rate"]),
        )
        for r in rows
    ]
    out.sort(key=lambda x: (x[0], x[1]))
    return out
