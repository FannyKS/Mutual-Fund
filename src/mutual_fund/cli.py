"""Command line interface.

Usage:
    mutual-fund show                    # terminal summary of latest value
    mutual-fund report                  # write daily/weekly/monthly CSVs
    mutual-fund report --out DIR        # custom output directory
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .loader import load_accounts, load_fx, load_navs, load_transactions
from .reports import (
    DEFAULT_OUTPUT_DIR,
    print_summary,
    write_all_reports,
)
from .valuation import compute_valuations

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def _load_and_value(data_dir: Path, base_currency: str):
    accounts = load_accounts(data_dir)
    transactions = load_transactions(data_dir)
    navs = load_navs(data_dir)
    fx = load_fx(data_dir)
    valuations = compute_valuations(
        accounts, transactions, navs, fx, base_currency
    )
    return accounts, valuations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mutual-fund",
        description="Market value reports for mutual fund accounts.",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory containing accounts/transactions/nav/fx CSVs "
        "(default: ./data)",
    )
    parser.add_argument(
        "--base",
        default="CAD",
        help="Base currency for reports (default: CAD)",
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

    args = parser.parse_args(argv)

    try:
        accounts, valuations = _load_and_value(args.data, args.base)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

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
