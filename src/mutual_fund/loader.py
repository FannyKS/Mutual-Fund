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


@dataclass(frozen=True)
class SnapshotPosition:
    """Units held in an account/fund as of a statement date."""

    date: date
    account_id: str
    fund: str
    units: float


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


def load_snapshot(data_dir: Path) -> list[SnapshotPosition]:
    """Load the holdings snapshot (data/snapshot.csv) if present.

    This is the baseline: units held per account/fund as of the snapshot
    date. Transactions dated on or before that date are assumed to be
    already reflected in it.
    """
    path = data_dir / "snapshot.csv"
    if not path.exists():
        return []
    rows = _read_csv(path)
    out = [
        SnapshotPosition(
            date=date.fromisoformat(r["date"].strip()),
            account_id=r["account_id"].strip(),
            fund=r["fund"].strip(),
            units=float(r["units"]),
        )
        for r in rows
    ]
    return out


def append_transaction(data_dir: Path, txn: Transaction) -> Path:
    """Append one transaction to data/transactions.csv, creating it if needed."""
    path = data_dir / "transactions.csv"
    data_dir.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["date", "account_id", "fund", "action", "units", "price"])
        w.writerow(
            [
                txn.date.isoformat(),
                txn.account_id,
                txn.fund,
                txn.action,
                f"{txn.units:.4f}",
                f"{txn.price:.4f}",
            ]
        )
    return path
