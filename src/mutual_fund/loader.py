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
    owner: str
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
    """Units held in an account/fund as of a statement date.

    ``cost`` is the book value / adjusted cost base (ACB) in the account's
    currency, when it is known from a statement. It is ``None`` when the
    statement only reported units (gain/loss is then reported as n/a).
    """

    date: date
    account_id: str
    fund: str
    units: float
    cost: float | None = None


def _parse_optional_float(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text or text.startswith("#"):
        return None
    return float(text)


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
        name = r["name"].strip()
        owner = (r.get("owner") or "").strip()
        if not owner:
            if name.startswith("Fanny"):
                owner = "Fanny"
            elif name.startswith("KC"):
                owner = "KC"
            elif name.startswith("Joint"):
                owner = "Joint"
            elif name.startswith("TD"):
                owner = "TD"
            else:
                owner = r["institution"].strip()
        acct = Account(
            account_id=r["account_id"].strip(),
            name=name,
            owner=owner,
            institution=r["institution"].strip(),
            currency=r["currency"].strip().upper(),
        )
        accounts[acct.account_id] = acct
    if not accounts:
        raise ValueError(f"No accounts found in {data_dir / 'accounts.csv'}")
    return accounts


def load_fund_names(data_dir: Path) -> dict[str, str]:
    """Return {fund_code: display name} from funds.csv (optional)."""
    path = data_dir / "funds.csv"
    if not path.exists():
        return {}
    names: dict[str, str] = {}
    for r in _read_csv(path):
        code = (r.get("fund") or "").strip()
        name = (r.get("name") or "").strip()
        if code:
            names[code] = name or code
    return names


def load_transactions(data_dir: Path) -> list[Transaction]:
    """Load transactions (optional; absent means no changes recorded yet)."""
    path = data_dir / "transactions.csv"
    if not path.exists():
        return []
    rows = _read_csv(path)
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


def _parse_nav_rows(rows) -> list[tuple[date, str, float, str]]:
    out = []
    for r in rows:
        d = (r.get("date") or "").strip()
        if not d or d.startswith("#"):
            continue  # blank or comment line
        out.append(
            (
                date.fromisoformat(d),
                r["fund"].strip(),
                float(r["nav"]),
                r["currency"].strip().upper(),
            )
        )
    return out


def load_navs(data_dir: Path) -> list[tuple[date, str, float, str]]:
    """Return NAV observations as (date, fund, nav, currency), sorted by date.

    Values in the optional `nav_overrides.csv` (same columns as nav.csv) take
    precedence for the same (date, fund). Use it to pin a precise NAV that a
    public feed only publishes rounded — it survives future fetches.
    """
    out = _parse_nav_rows(_read_csv(data_dir / "nav.csv"))
    overrides_path = data_dir / "nav_overrides.csv"
    if overrides_path.exists():
        by_key = {(d, f): (d, f, n, c) for d, f, n, c in out}
        for row in _parse_nav_rows(_read_csv(overrides_path)):
            by_key[(row[0], row[1])] = row
        out = list(by_key.values())
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def load_fx(data_dir: Path) -> list[tuple[date, str, float]]:
    """Return FX rates as (date, currency, rate_to_CAD), sorted by date.

    Optional: if fx.csv is absent, an empty list is returned. This is fine
    while every fund is priced in the base currency; a conversion will then
    fail with a clear error if a foreign-currency fund shows up.
    """
    path = data_dir / "fx.csv"
    if not path.exists():
        return []
    rows = _read_csv(path)
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
            cost=_parse_optional_float(r.get("cost")),
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
