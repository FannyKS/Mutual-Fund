"""Fetch fund NAVs from public sources.

Fund NAVs are published publicly every business day after market close, so
they can be fetched without any account access. Each fund is mapped to a
source in data/funds.csv:

    fund,name,currency,source,identifier,pattern
    MIF001,Manulife X Fund,CAD,yahoo,0P0000XXXX.TO,
    TDB900,TD Canadian Bond,CAD,html,https://example.com/td-funds,"\\$([0-9.]+)"

Supported sources:
  yahoo     - Yahoo Finance chart API (works for many funds/ETFs by ticker)
  fidelity  - Fidelity Canada's public fund data feed, by fund code
              (e.g. 223 = Fidelity Dividend Plus Series B)
  manulife  - Manulife Investment Management fund profile, by fund code
              (e.g. MGF1916). Server-rendered, includes full NAV history.
  globe     - The Globe and Mail fund quote, by symbol (e.g. TDB619.CF).
              Latest NAV only; works for many Canadian funds.
  barchart  - Barchart end-of-day series behind Globe and Mail fund pages,
              by symbol (e.g. MGF1916.CF). Full daily history, works for
              most Canadian funds.
  html      - scrape a public fund page; `pattern` is a regex with one capture
              group for the price
  csv       - a public CSV URL; last numeric column is used as the NAV
"""

from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) mutual-fund/0.1"


@dataclass(frozen=True)
class FundSource:
    fund: str
    name: str
    currency: str
    source: str
    identifier: str
    pattern: str = ""


def _get(url: str, timeout: int = 20, headers: dict | None = None) -> str:
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def load_fund_sources(path: Path) -> list[FundSource]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Create it to list where each fund's NAV comes "
            "from (see examples/funds.csv)."
        )
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = [
            r
            for r in csv.DictReader(f)
            if (r.get("fund") or "").strip()
            and not (r.get("fund") or "").strip().startswith("#")
        ]
    out = []
    for r in rows:
        out.append(
            FundSource(
                fund=r["fund"].strip(),
                name=r.get("name", "").strip(),
                currency=r.get("currency", "CAD").strip().upper(),
                source=r["source"].strip().lower(),
                identifier=r["identifier"].strip(),
                pattern=r.get("pattern", "").strip(),
            )
        )
    if not out:
        raise ValueError(f"No funds found in {path}")
    return out


# ---------------------------------------------------------------------------
# Source adapters — each returns [(date, nav), ...]
# ---------------------------------------------------------------------------

def fetch_yahoo(src: FundSource, start: date, end: date) -> list[tuple[date, float]]:
    p1 = int(datetime(start.year, start.month, start.day).timestamp())
    p2 = int(datetime(end.year, end.month, end.day).timestamp()) + 86400
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(src.identifier)}"
        f"?period1={p1}&period2={p2}&interval=1d"
    )
    data = json.loads(_get(url))
    result = (data.get("chart") or {}).get("result")
    if not result:
        raise ValueError(
            f"Yahoo returned no data for '{src.identifier}' "
            f"(fund {src.fund}). Check the ticker."
        )
    chart = result[0]
    stamps = chart.get("timestamp") or []
    closes = ((chart.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    out = []
    for ts, close in zip(stamps, closes):
        if close is None:
            continue
        out.append((datetime.fromtimestamp(ts).date(), float(close)))
    return out


def fetch_html(src: FundSource, start: date, end: date) -> list[tuple[date, float]]:
    if not src.pattern:
        raise ValueError(f"Fund {src.fund}: 'html' source needs a pattern column.")
    html = _get(src.identifier)
    m = re.search(src.pattern, html)
    if not m:
        raise ValueError(
            f"Fund {src.fund}: pattern {src.pattern!r} not found on {src.identifier}"
        )
    price = float(m.group(1).replace(",", ""))
    return [(date.today(), price)]


def fetch_csv(src: FundSource, start: date, end: date) -> list[tuple[date, float]]:
    text = _get(src.identifier)
    reader = csv.reader(text.splitlines())
    rows = [r for r in reader if r]
    if not rows:
        raise ValueError(f"Fund {src.fund}: empty CSV at {src.identifier}")
    out = []
    for r in rows:
        try:
            d = date.fromisoformat(r[0].strip())
            price = float(r[-1].strip().replace(",", "").replace("$", ""))
        except ValueError:
            continue  # header or unparsable row
        if start <= d <= end:
            out.append((d, price))
    return out


FIDELITY_URL = "https://www.fidelity.ca/content/fidelity-data/pnp-cached-en.json"
_FIDELITY_CACHE: dict | None = None


def _fidelity_feed() -> dict:
    global _FIDELITY_CACHE
    if _FIDELITY_CACHE is None:
        _FIDELITY_CACHE = json.loads(_get(FIDELITY_URL))
    return _FIDELITY_CACHE


def fetch_fidelity(src: FundSource, start: date, end: date) -> list[tuple[date, float]]:
    """Fidelity Canada: look up a fund series by its code in the public feed.

    The feed carries only the latest NAV per series, so this returns one
    observation per fetch (accumulate daily historical data in nav.csv over
    time). `identifier` is the fund code, e.g. 223 or 1241.
    """
    data = _fidelity_feed()
    want = str(src.identifier).strip()
    for fund in data.get("funds", []):
        for series in fund.get("series", []):
            for code in series.get("codes") or []:
                if str(code.get("code")) != want:
                    continue
                nav = series.get("price_nav")
                raw_date = series.get("price_nav_date")
                if not nav or nav == "-" or not raw_date or raw_date == "-":
                    raise ValueError(
                        f"Fund {src.fund}: Fidelity series '{series.get('title')}' "
                        f"(code {want}) has no NAV published yet."
                    )
                d = datetime.strptime(raw_date, "%d-%b-%Y").date()
                if not (start <= d <= end):
                    return []
                return [(d, float(nav))]
    raise ValueError(
        f"Fund {src.fund}: Fidelity fund code '{want}' not found. "
        "Check the code against your statement."
    )


MANULIFE_PROFILE = "https://funds.manulife.ca/en-US/profiles/{code}"
_MANULIFE_ROW = re.compile(
    r"<td>(\d{4}/\d{2}/\d{2})</td>\s*<td class=\"col-number\">\s*\$([\d.]+)"
)


def fetch_manulife(src: FundSource, start: date, end: date) -> list[tuple[date, float]]:
    """Manulife fund profile page: full historical NAV table, server-rendered.

    `identifier` is the fund code, e.g. MGF1916. Because the page carries the
    whole history, this also backfills past dates.
    """
    html = _get(MANULIFE_PROFILE.format(code=src.identifier))
    rows = _MANULIFE_ROW.findall(html)
    if not rows:
        raise ValueError(
            f"Fund {src.fund}: no NAV table found for Manulife code "
            f"'{src.identifier}'. Check the fund code."
        )
    out: list[tuple[date, float]] = []
    for raw_date, raw_nav in rows:
        d = datetime.strptime(raw_date, "%Y/%m/%d").date()
        if start <= d <= end:
            out.append((d, float(raw_nav)))
    return out


GLOBE_QUOTE = "https://www.theglobeandmail.com/investing/markets/funds/{symbol}/"
_GLOBE_PRICE = re.compile(
    r'"lastPrice":"([\d.]+)"'
    r'.*?"tradeTime":"(\d{2})\\/(\d{2})\\/(\d{2})"',
    re.S,
)


def fetch_globe(src: FundSource, start: date, end: date) -> list[tuple[date, float]]:
    """The Globe and Mail fund quote (latest price + trade date).

    `identifier` is the quote symbol, e.g. TDB619.CF. Only the latest
    observation is available, so history accumulates in nav.csv over time.
    """
    html = _get(GLOBE_QUOTE.format(symbol=src.identifier))
    m = _GLOBE_PRICE.search(html)
    if not m:
        raise ValueError(
            f"Fund {src.fund}: no quote found for Globe symbol "
            f"'{src.identifier}'. Check the symbol."
        )
    price, mm, dd, yy = m.groups()
    d = date(2000 + int(yy), int(mm), int(dd))
    if not (start <= d <= end):
        return []
    return [(d, float(price))]


BARCHART_EOD = (
    "https://globeandmail.pl.barchart.com/proxies/timeseries/queryeod.ashx"
)


def fetch_barchart(src: FundSource, start: date, end: date) -> list[tuple[date, float]]:
    """Barchart end-of-day prices (the source behind Globe and Mail fund pages).

    `identifier` is the symbol, e.g. MGF1916.CF. Returns full daily history, so
    this backfills past dates as well. Response lines look like:

        MGF1916.CF,2026-10-16,19.6878,19.6878,19.6878,19.6878,0
        symbol,date,open,high,low,close,volume
    """
    # Barchart returns the most recent `maxrecords` rows; ask for enough to
    # comfortably cover the requested window.
    span_days = (end - start).days
    maxrecords = max(250, int(span_days * 0.75) + 30)
    url = (
        f"{BARCHART_EOD}?symbol={urllib.parse.quote(src.identifier)}"
        f"&data=daily&maxrecords={maxrecords}&order=desc"
    )
    text = _get(url, headers={"Referer": "https://www.theglobeandmail.com/"})
    out: list[tuple[date, float]] = []
    for line in text.splitlines():
        parts = line.strip().split(",")
        if len(parts) < 6:
            continue
        try:
            d = date.fromisoformat(parts[1].strip())
            close = float(parts[5])
        except ValueError:
            continue  # header or non-numeric row
        if start <= d <= end:
            out.append((d, close))
    if not out:
        raise ValueError(
            f"Fund {src.fund}: no Barchart prices for '{src.identifier}' in "
            f"{start.isoformat()}..{end.isoformat()}. Check the symbol."
        )
    out.sort()
    return out


ADAPTERS = {
    "yahoo": fetch_yahoo,
    "fidelity": fetch_fidelity,
    "manulife": fetch_manulife,
    "globe": fetch_globe,
    "barchart": fetch_barchart,
    "html": fetch_html,
    "csv": fetch_csv,
}


def fetch(src: FundSource, start: date, end: date) -> list[tuple[date, float]]:
    adapter = ADAPTERS.get(src.source)
    if adapter is None:
        raise ValueError(
            f"Fund {src.fund}: unknown source '{src.source}'. "
            f"Use one of: {', '.join(ADAPTERS)}"
        )
    return adapter(src, start, end)


# ---------------------------------------------------------------------------
# Merge into nav.csv
# ---------------------------------------------------------------------------

def merge_nav(
    nav_path: Path,
    new_rows: list[tuple[date, FundSource, float]],
    overwrite: bool = False,
) -> int:
    """Add fetched NAVs to nav.csv. Returns the number of new rows written."""
    existing: dict[tuple[str, str], tuple[str, str, str, str]] = {}
    if nav_path.exists():
        with nav_path.open(newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                key = (r["date"].strip(), r["fund"].strip())
                existing[key] = (
                    r["date"].strip(),
                    r["fund"].strip(),
                    r["nav"].strip(),
                    r.get("currency", "CAD").strip() or "CAD",
                )

    added = 0
    for d, src, nav in new_rows:
        key = (d.isoformat(), src.fund)
        row = (d.isoformat(), src.fund, f"{nav:.4f}", src.currency)
        if key in existing and not overwrite:
            continue
        existing[key] = row
        added += 1

    nav_path.parent.mkdir(parents=True, exist_ok=True)
    with nav_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "fund", "nav", "currency"])
        for key in sorted(existing):
            w.writerow(existing[key])
    return added


def update_navs(
    data_dir: Path,
    funds_path: Path | None = None,
    start: date | None = None,
    end: date | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> tuple[int, list[str]]:
    """Fetch NAVs for every fund and merge them into data/nav.csv.

    Returns (rows_added, errors).
    """
    funds_path = funds_path or (data_dir / "funds.csv")
    end = end or date.today()
    start = start or (end - timedelta(days=365))

    fund_sources = load_fund_sources(funds_path)
    rows: list[tuple[date, FundSource, float]] = []
    errors: list[str] = []

    for src in fund_sources:
        try:
            obs = fetch(src, start, end)
        except Exception as e:  # keep going; report at the end
            errors.append(f"{src.fund}: {e}")
            continue
        if not obs:
            errors.append(f"{src.fund}: no observations returned")
            continue
        for d, nav in obs:
            rows.append((d, src, nav))

    if dry_run:
        return len(rows), errors
    added = merge_nav(data_dir / "nav.csv", rows, overwrite=overwrite)
    return added, errors
