"""Fetch daily exchange rates from the Bank of Canada and write fx.csv.

The Bank of Canada publishes one USD/CAD rate per business day (and similar
for other currencies) via its public Valet API. Rates are quoted as CAD per
1 unit of the foreign currency, which is exactly the format fx.csv expects.
"""

from __future__ import annotations

import csv
import json
import urllib.request
from datetime import date, timedelta
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (Macintosh) mutual-fund/0.1"
VALET = "https://www.bankofcanada.ca/valet/observations/{series}/json"

# currency -> Bank of Canada Valet series name
SERIES = {
    "USD": "FXUSDCAD",
    "EUR": "FXEURCAD",
    "GBP": "FXGBPCAD",
    "JPY": "FXJPYCAD",
    "HKD": "FXHKDCAD",
    "AUD": "FXAUDCAD",
    "CHF": "FXCHFCAD",
    "CNY": "FXCNYCAD",
}


def fetch_rates(
    currencies: list[str],
    start: date,
    end: date,
) -> list[tuple[date, str, float]]:
    """Return [(date, currency, rate_to_CAD)] from the Bank of Canada."""
    out: list[tuple[date, str, float]] = []
    for ccy in currencies:
        ccy = ccy.upper()
        series = SERIES.get(ccy)
        if series is None:
            raise ValueError(
                f"No Bank of Canada series for {ccy}. "
                f"Supported: {', '.join(sorted(SERIES))}"
            )
        url = (
            f"{VALET.format(series=series)}"
            f"?start_date={start.isoformat()}&end_date={end.isoformat()}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for obs in data.get("observations", []):
            val = (obs.get(series) or {}).get("v")
            if not val or val == "nan":
                continue  # BoC returns "nan" for non-business days
            out.append((date.fromisoformat(obs["d"]), ccy, float(val)))
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def merge_fx(
    fx_path: Path,
    new_rows: list[tuple[date, str, float]],
    overwrite: bool = False,
) -> int:
    existing: dict[tuple[str, str], tuple[str, str, str]] = {}
    if fx_path.exists():
        with fx_path.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                existing[(r["date"].strip(), r["currency"].strip())] = (
                    r["date"].strip(),
                    r["currency"].strip(),
                    r["rate"].strip(),
                )
    added = 0
    for d, ccy, rate in new_rows:
        key = (d.isoformat(), ccy)
        if key in existing and not overwrite:
            continue
        existing[key] = (d.isoformat(), ccy, f"{rate:.6f}")
        added += 1

    fx_path.parent.mkdir(parents=True, exist_ok=True)
    with fx_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "currency", "rate"])
        for key in sorted(existing):
            w.writerow(existing[key])
    return added


def update_fx(
    data_dir: Path,
    currencies: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> tuple[int, list[str]]:
    """Fetch the currencies used by funds.csv and merge them into fx.csv."""
    from .navfetch import load_fund_sources

    funds_path = data_dir / "funds.csv"
    if currencies is None:
        currencies = []
        if funds_path.exists():
            for src in load_fund_sources(funds_path):
                if src.currency.upper() != "CAD":
                    currencies.append(src.currency.upper())
    currencies = sorted({c.upper() for c in currencies if c.upper() != "CAD"})
    if not currencies:
        return 0, []

    end = end or date.today()
    start = start or (end - timedelta(days=365))
    errors: list[str] = []
    try:
        rows = fetch_rates(currencies, start, end)
    except Exception as e:  # network / series problem
        return 0, [str(e)]
    if dry_run:
        return len(rows), errors
    added = merge_fx(data_dir / "fx.csv", rows, overwrite=overwrite)
    return added, errors
