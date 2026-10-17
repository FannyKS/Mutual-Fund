"""Command line interface.

Usage:
    mutual-fund show                     # terminal summary of latest value
    mutual-fund report                   # write daily/weekly/monthly CSVs
    mutual-fund add --account F-RRSP --fund MIF001 --units 100 --price 25.10
    mutual-fund reconcile --snapshot new_holdings.csv
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .loader import (
    SnapshotPosition,
    Transaction,
    append_transaction,
    load_accounts,
    load_fx,
    load_navs,
    load_snapshot,
    load_transactions,
)
from .navfetch import update_navs
from .reports import (
    DEFAULT_OUTPUT_DIR,
    print_summary,
    write_all_reports,
)
from .valuation import compute_valuations, positions_as_of

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _load_and_value(data_dir: Path, base_currency: str, strict: bool = False):
    accounts = load_accounts(data_dir)
    transactions = load_transactions(data_dir)
    navs = load_navs(data_dir)
    fx = load_fx(data_dir)
    snapshot = load_snapshot(data_dir)
    valuations, warnings = compute_valuations(
        accounts, transactions, navs, fx, base_currency, snapshot, strict
    )
    return accounts, valuations, warnings


def _cmd_add(args) -> int:
    accounts = load_accounts(args.data)
    if args.account not in accounts:
        print(
            f"Error: unknown account '{args.account}'. Known accounts: "
            f"{', '.join(accounts)}",
            file=sys.stderr,
        )
        return 1
    txn = Transaction(
        date=args.date or date.today(),
        account_id=args.account,
        fund=args.fund,
        action=args.action.upper(),
        units=args.units,
        price=args.price,
    )
    path = append_transaction(args.data, txn)
    print(
        f"Recorded {txn.action} {txn.units:g} units of {txn.fund} in "
        f"{txn.account_id} on {txn.date.isoformat()} -> {path}"
    )
    return 0


def _cmd_reconcile(args) -> int:
    accounts = load_accounts(args.data)
    transactions = load_transactions(args.data)
    snapshot = load_snapshot(args.data)

    # Read the new snapshot file provided on the command line.
    rows = []
    with args.snapshot.open(newline="", encoding="utf-8-sig") as f:
        import csv

        for r in csv.DictReader(f):
            rows.append(
                SnapshotPosition(
                    date=date.fromisoformat(r["date"].strip()),
                    account_id=r["account_id"].strip(),
                    fund=r["fund"].strip(),
                    units=float(r["units"]),
                )
            )
    if not rows:
        print("Snapshot file is empty.", file=sys.stderr)
        return 1
    on = max(r.date for r in rows)

    expected = positions_as_of(snapshot, transactions, on)
    actual: dict[tuple[str, str], float] = {}
    for r in rows:
        actual[(r.account_id, r.fund)] = actual.get((r.account_id, r.fund), 0.0) + r.units

    keys = sorted(set(expected) | set(actual))
    print(f"Reconciling holdings as of {on.isoformat()}\n")
    print(f"{'Account':<14}{'Fund':<12}{'Expected':>14}{'Snapshot':>14}{'Diff':>14}")
    print("-" * 68)
    mismatches = 0
    for k in keys:
        acct_id, fund = k
        exp = expected.get(k, 0.0)
        act = actual.get(k, 0.0)
        diff = act - exp
        if abs(diff) > 1e-6:
            mismatches += 1
            print(f"{acct_id:<14}{fund:<12}{exp:>14,.4f}{act:>14,.4f}{diff:>+14,.4f}")
        else:
            print(f"{acct_id:<14}{fund:<12}{exp:>14,.4f}{act:>14,.4f}{'-':>14}")
    print("-" * 68)
    if mismatches:
        print(
            f"\n{mismatches} difference(s) found. The snapshot differs from your "
            "recorded transactions — either a transaction is missing, or it was "
            "already included in an earlier snapshot."
        )
    else:
        print("\nAll holdings match. Safe to use this snapshot as the new baseline.")
    if args.accept and not mismatches:
        target = args.data / "snapshot.csv"
        target.write_text(
            "date,account_id,fund,units\n"
            + "".join(
                f"{r.date.isoformat()},{r.account_id},{r.fund},{r.units:.4f}\n"
                for r in sorted(rows, key=lambda r: (r.account_id, r.fund))
            ),
            encoding="utf-8",
        )
        print(f"Snapshot saved to {target}.")
    elif args.accept:
        print("Not saved: fix the differences first (or update the snapshot).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mutual-fund",
        description="Market value reports for mutual fund accounts.",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory containing the CSV files (default: ./data)",
    )
    parser.add_argument(
        "--base",
        default="CAD",
        help="Base currency for reports (default: CAD)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail instead of skipping funds that have no NAV",
    )
    sub = parser.add_subparsers(dest="command")

    rep = sub.add_parser("report", help="Write daily/weekly/monthly CSV reports")
    rep.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    sub.add_parser("show", help="Print latest value to the terminal (default)")

    add = sub.add_parser("add", help="Record a buy/sell as a change to your holdings")
    add.add_argument("--account", required=True, help="e.g. F-RRSP")
    add.add_argument("--fund", required=True, help="e.g. MIF001")
    add.add_argument("--units", type=float, required=True, help="Number of units")
    add.add_argument("--price", type=float, required=True, help="Price/NAV per unit")
    add.add_argument(
        "--action", choices=["BUY", "SELL", "buy", "sell"], default="BUY"
    )
    add.add_argument(
        "--date", type=date.fromisoformat, default=None, help="YYYY-MM-DD (default: today)"
    )

    rec = sub.add_parser(
        "reconcile", help="Compare a new holdings snapshot against your records"
    )
    rec.add_argument("--snapshot", type=Path, required=True, help="New snapshot CSV")
    rec.add_argument(
        "--accept", action="store_true", help="Save as the new baseline if it matches"
    )

    fetch = sub.add_parser(
        "fetch-nav",
        help="Fetch fund NAVs from public sources into data/nav.csv",
    )
    fetch.add_argument(
        "--funds",
        type=Path,
        default=None,
        help="Fund/source mapping CSV (default: <data>/funds.csv)",
    )
    fetch.add_argument(
        "--since",
        type=date.fromisoformat,
        default=None,
        help="Start date YYYY-MM-DD (default: 1 year ago)",
    )
    fetch.add_argument(
        "--until",
        type=date.fromisoformat,
        default=None,
        help="End date YYYY-MM-DD (default: today)",
    )
    fetch.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace NAVs already recorded for the same date/fund",
    )
    fetch.add_argument(
        "--dry-run", action="store_true", help="Fetch but do not write nav.csv"
    )

    args = parser.parse_args(argv)

    if args.command == "fetch-nav":
        try:
            added, errors = update_navs(
                args.data,
                args.funds,
                args.since,
                args.until,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
            )
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        for err in errors:
            print(f"Warning: {err}", file=sys.stderr)
        verb = "would add" if args.dry_run else "added"
        print(f"NAV fetch complete: {verb} {added} row(s).")
        if errors:
            print(f"{len(errors)} fund(s) failed — see warnings above.", file=sys.stderr)
        return 1 if errors and not added else 0

    try:
        if args.command == "add":
            return _cmd_add(args)
        if args.command == "reconcile":
            return _cmd_reconcile(args)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    try:
        accounts, valuations, warnings = _load_and_value(
            args.data, args.base, args.strict
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    for w in warnings:
        print(f"Warning: {w}", file=sys.stderr)

    if not valuations:
        print("No valuations produced — check your data files.", file=sys.stderr)
        return 1

    if args.command == "report":
        paths = write_all_reports(valuations, accounts, args.out, args.base)
        print(f"Reports written to {args.out}:\n")
        for p in paths:
            print(f"  {p}")
        print()
        print_summary(valuations, accounts, args.base)
    else:  # show (default)
        print_summary(valuations, accounts, args.base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
