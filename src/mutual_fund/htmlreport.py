"""HTML dashboard and period reports (dark theme, self-contained).

Design mirrors the dashboard in the separate Finance project: summary
cards, an allocation donut, value-by-account bars, a value-history line
chart and a holdings table with gain/loss. Everything is inline, so each
file opens (or emails) with no external dependencies.

The numbers are the same ones the CSV reports use.
"""

from __future__ import annotations

import html
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .loader import Account, Transaction
from .valuation import Valuation

_PALETTE = [
    "#4f8ef7", "#3ddc84", "#ffb020", "#ff6b81", "#a78bfa", "#38bdf8",
    "#f472b6", "#34d399", "#facc15", "#60a5fa", "#c084fc", "#fb923c",
]

CSS = """
:root { --bg:#0f1420; --card:#171d2c; --line:#242c40; --txt:#e8ecf4; --mut:#8b97ad;
        --pos:#3ddc84; --neg:#ff6b81; --acc:#4f8ef7; --flat:#8b97ad; --sub:#ffd24a; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--txt);
       font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
.wrap { max-width:1120px; margin:0 auto; padding:28px 20px 60px; }
h1 { font-size:22px; margin:0 0 2px; }
.sub { color:var(--mut); margin-bottom:22px; }
a { color:var(--acc); }
.cards { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:22px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px 18px; }
.card .k { color:var(--mut); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }
.card .v { font-size:24px; font-weight:650; margin-top:6px; }
.card .d { color:var(--mut); font-size:12px; margin-top:4px; }
.chg-sub { color: var(--sub); font-weight: 600; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:22px; }
.panel { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px 18px; }
.panel h2 { font-size:14px; margin:0 0 14px; color:var(--mut); font-weight:600;
            text-transform:uppercase; letter-spacing:.04em; }
.donutwrap { display:flex; align-items:center; gap:18px; }
.donut { position:relative; flex:0 0 auto; }
.donut .mid { position:absolute; inset:0; display:flex; flex-direction:column;
              align-items:center; justify-content:center; }
.donut .mid .m1 { font-size:11px; color:var(--mut); text-transform:uppercase; letter-spacing:.04em; }
.donut .mid .m2 { font-size:17px; font-weight:650; }
.legend { list-style:none; margin:0; padding:0; font-size:13px; min-width:0; }
.legend li { display:flex; align-items:center; gap:8px; margin:4px 0; }
.legend .sw { width:10px; height:10px; border-radius:3px; flex:0 0 auto; }
.legend .nm { color:var(--txt); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.legend .vv { margin-left:auto; color:var(--mut); white-space:nowrap; }
.bar { margin:9px 0; }
.bar .top { display:flex; justify-content:space-between; font-size:13px; margin-bottom:3px; }
.bar .top .nm { color:var(--txt); } .bar .top .vv { color:var(--mut); }
.bar .track { height:8px; background:#0b0f1a; border-radius:6px; overflow:hidden; }
.bar .fill { height:100%; border-radius:6px; }
.insthdr { color:var(--mut); font-size:11px; text-transform:uppercase; letter-spacing:.05em;
           margin:12px 0 2px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { padding:8px 10px; text-align:right; border-bottom:1px solid var(--line); white-space:nowrap; }
th { color:var(--mut); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
th:first-child, td:first-child { text-align:left; }
th.l, td.l { text-align:left; }
tr.sub td { color:var(--sub); font-weight:600; background:rgba(255,210,74,0.07);
            border-bottom:1px solid var(--line); }
tr.total td { font-weight:700; border-top:2px solid var(--line); border-bottom:none; }
.muted { color:var(--mut); }
.note { color:var(--mut); font-size:12px; margin-top:16px; }
.chip { display:inline-block; background:#0b0f1a; border:1px solid var(--line);
        border-radius:999px; padding:1px 9px; font-size:11px; color:var(--mut); }
@media (max-width:820px){ .cards{grid-template-columns:1fr 1fr;} .grid2{grid-template-columns:1fr;}
  .donutwrap{flex-direction:column; align-items:flex-start;} }
"""


# ---------------------------------------------------------------------------
# small formatting helpers
# ---------------------------------------------------------------------------

def _esc(s) -> str:
    return html.escape(str(s))


def _money(v: float) -> str:
    return f"${v:,.2f}"


def _smoney(v: float) -> str:
    return ("+" if v >= 0 else "-") + f"${abs(v):,.2f}"


def _pct(v: float) -> str:
    return f"{v:+.2f}%"


def _cls(v: float) -> str:
    return "pos" if v > 0 else ("neg" if v < 0 else "flat")


def _chg(v: float | None, pct: float | None = None, subtotal: bool = False) -> str:
    """Signed money (and optional %) as coloured HTML, or 'n/a'."""
    if v is None:
        return '<span class="muted">n/a</span>'
    cls = "chg-sub" if subtotal else _cls(v)
    s = f'<span class="{cls}">{_smoney(v)}'
    if pct is not None:
        s += f" ({_pct(pct)})"
    return s + "</span>"


# ---------------------------------------------------------------------------
# data shaping
# ---------------------------------------------------------------------------

def _holdings_on(valuations: list[Valuation], d: date) -> dict[tuple[str, str], Valuation]:
    return {(v.account.account_id, v.fund): v for v in valuations if v.date == d}


def _total_by_date(valuations: list[Valuation]) -> dict[date, float]:
    out: dict[date, float] = defaultdict(float)
    for v in valuations:
        out[v.date] += v.market_value
    return dict(sorted(out.items()))


def _rows_for_date(
    valuations: list[Valuation],
    accounts: dict[str, Account],
    fund_names: dict[str, str],
    latest: date,
    prev: date | None,
) -> list[dict]:
    cur = _holdings_on(valuations, latest)
    prv = _holdings_on(valuations, prev) if prev else {}
    total = sum(v.market_value for v in cur.values()) or 1.0
    inst_order = {a.institution: i for i, a in enumerate(accounts.values())}
    acct_order = {aid: i for i, aid in enumerate(accounts)}

    rows = []
    for (aid, fund), v in cur.items():
        p = prv.get((aid, fund))
        today = (v.market_value - p.market_value) if p is not None else None
        today_pct = None
        if p is not None and p.market_value:
            today_pct = (v.market_value - p.market_value) / p.market_value * 100.0
        rows.append(
            {
                "account_id": aid,
                "account": v.account,
                "fund": fund,
                "fund_name": fund_names.get(fund, fund),
                "units": v.units,
                "nav": v.nav,
                "currency": v.currency,
                "value": v.market_value,
                "weight": v.market_value / total * 100.0,
                "cost": v.cost,
                "gain": v.gain_loss,
                "gain_pct": v.gain_loss_pct,
                "today": today,
                "today_pct": today_pct,
            }
        )
    rows.sort(
        key=lambda r: (
            inst_order.get(r["account"].institution, 99),
            acct_order.get(r["account_id"], 99),
            -r["value"],
        )
    )
    return rows


def _group(rows: list[dict], keyfn) -> list[dict]:
    out: dict = {}
    order: list = []
    for r in rows:
        k = keyfn(r)
        g = out.get(k)
        if g is None:
            g = {"key": k, "value": 0.0, "cost": 0.0, "cost_known": True,
                 "today": 0.0, "today_known": False}
            out[k] = g
            order.append(k)
        g["value"] += r["value"]
        if r["cost"] is None:
            g["cost_known"] = False
        else:
            g["cost"] += r["cost"]
        if r["today"] is not None:
            g["today"] += r["today"]
            g["today_known"] = True
    result = []
    for k in order:
        g = out[k]
        g["gain"] = (g["value"] - g["cost"]) if g["cost_known"] else None
        g["gain_pct"] = (
            (g["value"] - g["cost"]) / g["cost"] * 100.0
            if (g["cost_known"] and g["cost"]) else None
        )
        g["today"] = g["today"] if g["today_known"] else None
        result.append(g)
    return result


# ---------------------------------------------------------------------------
# charts (inline SVG / HTML)
# ---------------------------------------------------------------------------

def _donut_svg(items: list[tuple[str, float, str]], total: float, size: int = 178,
               thickness: int = 26) -> str:
    r = (size - thickness) / 2.0
    c = size / 2.0
    circ = 2 * 3.141592653589793 * r
    parts = []
    offset = 0.0
    for _label, val, color in items:
        seg = (val / total * circ) if total else 0.0
        parts.append(
            f'<circle cx="{c:.1f}" cy="{c:.1f}" r="{r:.1f}" fill="none" '
            f'stroke="{color}" stroke-width="{thickness}" '
            f'stroke-dasharray="{seg:.3f} {circ - seg:.3f}" '
            f'stroke-dashoffset="{-offset:.3f}" '
            f'transform="rotate(-90 {c:.1f} {c:.1f})"/>'
        )
        offset += seg
    return (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        f'role="img">{"".join(parts)}</svg>'
    )


def _line_svg(points: list[tuple[date, float]], w: int = 1040, h: int = 250,
              pad: int = 38) -> str:
    if not points:
        return ""
    vals = [p[1] for p in points]
    vmin, vmax = min(vals), max(vals)
    if vmax == vmin:
        vmax = vmin + 1.0
    n = len(points)

    def X(i: int) -> float:
        return pad + (w - 2 * pad) * (i / (n - 1) if n > 1 else 0.5)

    def Y(v: float) -> float:
        return h - pad - (h - 2 * pad) * ((v - vmin) / (vmax - vmin))

    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_d, v) in enumerate(points))
    area = f"{X(0):.1f},{h - pad:.1f} {pts} {X(n - 1):.1f},{h - pad:.1f}"
    last_date, last_val = points[-1]
    first_date = points[0][0]
    grid = (
        f'<line x1="{pad}" y1="{Y(vmax):.1f}" x2="{w - pad}" y2="{Y(vmax):.1f}" '
        f'stroke="#242c40" stroke-width="1"/>'
        f'<line x1="{pad}" y1="{Y(vmin):.1f}" x2="{w - pad}" y2="{Y(vmin):.1f}" '
        f'stroke="#242c40" stroke-width="1"/>'
    )
    labels = (
        f'<text x="{pad}" y="{pad - 12}" fill="#8b97ad" font-size="11">'
        f'{first_date.isoformat()}</text>'
        f'<text x="{w - pad}" y="{pad - 12}" fill="#8b97ad" font-size="11" '
        f'text-anchor="end">{last_date.isoformat()}</text>'
        f'<text x="{pad}" y="{h - 8}" fill="#8b97ad" font-size="11">'
        f'low {_money(vmin)}</text>'
        f'<text x="{w - pad}" y="{h - 8}" fill="#8b97ad" font-size="11" '
        f'text-anchor="end">high {_money(vmax)}</text>'
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:auto" role="img">'
        f'<polygon points="{area}" fill="rgba(79,142,247,0.12)"/>'
        f'{grid}'
        f'<polyline points="{pts}" fill="none" stroke="#4f8ef7" stroke-width="2"/>'
        f'<circle cx="{X(n - 1):.1f}" cy="{Y(last_val):.1f}" r="3.5" fill="#4f8ef7"/>'
        f'{labels}</svg>'
    )


def _bars_accounts(rows: list[dict], vmax: float) -> str:
    """Bars aggregated per account, grouped by institution with subtotals."""
    acct: dict[str, dict] = {}
    order: list[str] = []
    by_inst: dict[str, list[str]] = {}
    for r in rows:
        aid = r["account_id"]
        if aid not in acct:
            acct[aid] = {"name": r["account"].name, "inst": r["account"].institution, "value": 0.0}
            order.append(aid)
            by_inst.setdefault(r["account"].institution, []).append(aid)
        acct[aid]["value"] += r["value"]
    out = []
    for inst, aids in by_inst.items():
        inst_total = sum(acct[a]["value"] for a in aids)
        color = _PALETTE[list(by_inst).index(inst) % len(_PALETTE)]
        out.append(f'<div class="insthdr">{_esc(inst)} &middot; {_money(inst_total)}</div>')
        for a in aids:
            val = acct[a]["value"]
            w = (val / vmax * 100.0) if vmax else 0.0
            name = f'{acct[a]["name"]} ({a})'
            out.append(
                f'<div class="bar"><div class="top"><span class="nm">{_esc(name)}</span>'
                f'<span class="vv">{_money(val)}</span></div>'
                f'<div class="track"><div class="fill" style="width:{w:.2f}%;'
                f'background:{color}"></div></div></div>'
            )
    return "".join(out)


# ---------------------------------------------------------------------------
# page shells
# ---------------------------------------------------------------------------

def _page(title: str, body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{_esc(title)}</title><style>{CSS}</style></head>"
        f"<body><div class=\"wrap\">{body}</div></body></html>\n"
    )


def _allocation_panel(rows: list[dict], total: float) -> str:
    by_fund = _group(rows, lambda r: r["fund"])
    by_fund.sort(key=lambda g: -g["value"])
    names = {r["fund"]: r["fund_name"] for r in rows}
    top = by_fund[:9]
    other = by_fund[9:]
    segs: list[tuple[str, float, str]] = []
    legend = []
    for i, g in enumerate(top):
        color = _PALETTE[i % len(_PALETTE)]
        segs.append((names[g["key"]], g["value"], color))
        legend.append((names[g["key"]], g["key"], g["value"], color))
    if other:
        osum = sum(g["value"] for g in other)
        color = _PALETTE[len(top) % len(_PALETTE)]
        segs.append(("Other", osum, color))
        legend.append((f"Other ({len(other)})", "", osum, color))

    donut = (
        '<div class="donutwrap"><div class="donut">'
        + _donut_svg(segs, total)
        + f'<div class="mid"><div class="m1">Total</div>'
        f'<div class="m2">{_money(total)}</div></div></div>'
    )
    items = []
    for name, code, val, color in legend:
        pctv = (val / total * 100.0) if total else 0.0
        chip = f' <span class="chip">{_esc(code)}</span>' if code else ""
        items.append(
            f'<li><span class="sw" style="background:{color}"></span>'
            f'<span class="nm">{_esc(name)}{chip}</span>'
            f'<span class="vv">{pctv:.1f}% &middot; {_money(val)}</span></li>'
        )
    return (
        '<div class="panel"><h2>Allocation by fund</h2>'
        + donut + f'<ul class="legend">{"".join(items)}</ul></div>'
    )


def _holdings_table(rows: list[dict], accounts: dict[str, Account], base_currency: str) -> str:
    head = (
        "<tr><th class=\"l\">Account / Fund</th><th>Code</th><th>Units</th>"
        "<th>NAV</th><th>Value</th><th>Weight</th><th>Today</th>"
        "<th>Cost (ACB)</th><th>Gain / loss</th></tr>"
    )
    body = []
    by_inst: dict[str, list[dict]] = {}
    for r in rows:
        by_inst.setdefault(r["account"].institution, []).append(r)
    for inst, items in by_inst.items():
        by_owner: dict[str, list[dict]] = defaultdict(list)
        for i in items:
            by_owner[i["account"].owner].append(i)
        owner_order = sorted(by_owner.keys(), key=lambda o: (0 if o == "Fanny" else (1 if o == "KC" else 2), o))
        total_all = sum(r["value"] for r in rows) or 1
        show_owner_subtotals = len(by_owner) > 1
        for owner in owner_order:
            o_items = by_owner[owner]
            if show_owner_subtotals:
                o_value = sum(x["value"] for x in o_items)
                o_today = sum(x["today"] for x in o_items if x["today"] is not None)
                o_gain_known = all(x["cost"] is not None for x in o_items)
                o_cost = sum(x["cost"] for x in o_items if x["cost"] is not None)
                o_gain = (o_value - o_cost) if o_gain_known else None
                body.append(
                    f'<tr class="sub"><td class="l">{_esc(owner)} subtotal</td><td></td><td></td>'
                    f'<td></td><td>{_money(o_value)}</td>'
                    f'<td>{(o_value / total_all) * 100:.1f}%</td>'
                    f'<td>{_chg(o_today if o_value else None, subtotal=True)}</td>'
                    f'<td>{_money(o_cost) if o_gain_known else "n/a"}</td>'
                    f'<td>{_chg(o_gain, subtotal=True) if o_gain is not None else "n/a"}</td></tr>'
                )
            for r in o_items:
                body.append(
                    f'<tr><td class="l">{_esc(r["account"].name)}'
                    f'<div class="muted" style="font-size:11px">{_esc(r["fund_name"])}</div></td>'
                    f'<td class="muted">{_esc(r["fund"])}</td>'
                    f'<td>{r["units"]:,.4f}</td>'
                    f'<td>{r["nav"]:,.4f}</td>'
                    f'<td>{_money(r["value"])}</td>'
                    f'<td>{r["weight"]:.1f}%</td>'
                    f'<td>{_chg(r["today"], r["today_pct"])}</td>'
                    f'<td>{_money(r["cost"]) if r["cost"] is not None else "n/a"}</td>'
                    f'<td>{_chg(r["gain"], r["gain_pct"]) if r["gain"] is not None else "n/a"}</td></tr>'
                )
        inst_value = sum(i["value"] for i in items)
        inst_today = sum(i["today"] for i in items if i["today"] is not None)
        inst_gain_known = all(i["cost"] is not None for i in items)
        inst_cost = sum(i["cost"] for i in items if i["cost"] is not None)
        inst_gain = (inst_value - inst_cost) if inst_gain_known else None
        body.append(
            f'<tr class="sub"><td class="l">{_esc(inst)} subtotal</td><td></td><td></td>'
            f'<td></td><td>{_money(inst_value)}</td>'
            f'<td>{(inst_value / total_all) * 100:.1f}%</td>'
            f'<td>{_chg(inst_today if inst_value else None, subtotal=True)}</td>'
            f'<td>{_money(inst_cost) if inst_gain_known else "n/a"}</td>'
            f'<td>{_chg(inst_gain, subtotal=True)}</td></tr>'
        )
    total = sum(r["value"] for r in rows)
    total_today = sum(r["today"] for r in rows if r["today"] is not None)
    known = [r for r in rows if r["cost"] is not None]
    total_cost = sum(r["cost"] for r in known)
    partial = len(known) < len(rows)
    total_gain = (sum(r["value"] for r in known) - total_cost) if known else None
    star = "*" if partial else ""
    if known:
        cost_cell = _money(total_cost) + star
    else:
        cost_cell = "n/a"
    if total_gain is None:
        gain_cell = '<span class="muted">n/a</span>'
    else:
        gain_cell = _chg(total_gain) + (" " + star if partial else "")
    body.append(
        f'<tr class="total"><td class="l">CONSOLIDATED ({_esc(base_currency)})</td><td></td>'
        f'<td></td><td></td><td>{_money(total)}</td><td>100.0%</td>'
        f'<td>{_chg(total_today)}</td>'
        f'<td>{cost_cell}</td>'
        f'<td>{gain_cell}</td></tr>'
    )
    return f'<table>{head}{"".join(body)}</table>'


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

def build_dashboard(
    valuations: list[Valuation],
    accounts: dict[str, Account],
    fund_names: dict[str, str],
    base_currency: str = "CAD",
) -> str:
    dates = sorted({v.date for v in valuations})
    latest = dates[-1]
    prev = dates[-2] if len(dates) > 1 else None
    rows = _rows_for_date(valuations, accounts, fund_names, latest, prev)

    total = sum(r["value"] for r in rows)
    today = sum(r["today"] for r in rows if r["today"] is not None)
    today_pct = (today / (total - today) * 100.0) if (total - today) else None
    known = [r for r in rows if r["cost"] is not None]
    cost = sum(r["cost"] for r in known)
    known_value = sum(r["value"] for r in known)
    partial = len(known) < len(rows)
    gain = (known_value - cost) if known else None
    gain_pct = ((known_value - cost) / cost * 100.0) if (known and cost) else None
    star = "*" if partial else ""

    header = (
        f'<h1>Mutual Fund Dashboard</h1>'
        f'<div class="sub">As of {latest.isoformat()} '
        f'&middot; base currency {_esc(base_currency)}'
        + (f' &middot; previous {prev.isoformat()}' if prev else "")
        + "</div>"
    )
    cards = (
        '<div class="cards">'
        f'<div class="card"><div class="k">Portfolio value</div>'
        f'<div class="v">{_money(total)}</div>'
        f'<div class="d">{len(rows)} holdings &middot; {len(accounts)} accounts</div></div>'
        f'<div class="card"><div class="k">Today\'s change</div>'
        f'<div class="v {_cls(today)}">{_smoney(today)}</div>'
        f'<div class="d">{_pct(today_pct) if today_pct is not None else "&nbsp;"}</div></div>'
        f'<div class="card"><div class="k">Gain / loss</div>'
        f'<div class="v {_cls(gain) if gain is not None else "flat"}">'
        f'{(("+" if gain >= 0 else "-") + "$" + format(abs(gain), ",.2f") + star) if gain is not None else "n/a"}</div>'
        f'<div class="d">{(str(_pct(gain_pct)) + star) if gain_pct is not None else "cost basis incomplete"}</div></div>'
        f'<div class="card"><div class="k">Cost (ACB)</div>'
        f'<div class="v">{_money(cost)}{star}</div>'
        f'<div class="d">{"book value" if not partial else "excludes accounts without ACB"}</div></div>'
        "</div>"
    )

    acct_tot: dict[str, float] = {}
    for r in rows:
        acct_tot[r["account_id"]] = acct_tot.get(r["account_id"], 0.0) + r["value"]
    vmax = max(acct_tot.values(), default=0.0)
    bars = (
        '<div class="panel"><h2>Value by account</h2>'
        + _bars_accounts(rows, vmax) + "</div>"
    )

    hist = list(_total_by_date(valuations).items())
    history = (
        '<div class="panel" style="margin-bottom:22px"><h2>Portfolio value history</h2>'
        + (_line_svg(hist) if len(hist) > 1 else '<div class="muted">Not enough history yet.</div>')
        + "</div>"
    )

    table = (
        '<div class="panel"><h2>Holdings</h2>'
        + _holdings_table(rows, accounts, base_currency) + "</div>"
    )

    note = ""
    if partial:
        missing = sorted({r["account"].institution for r in rows if r["cost"] is None})
        note = (
            f'<div class="note">* Gain/loss and cost cover only holdings with a '
            f'cost basis. Accounts without ACB: {", ".join(_esc(i) for i in missing)}. '
            f'Provide their ACB to complete the picture.</div>'
        )

    body = header + cards + '<div class="grid2">' + _allocation_panel(rows, total) + bars + "</div>" + history + table + note
    return _page("Mutual Fund Dashboard", body)


def write_dashboard(
    valuations: list[Valuation],
    accounts: dict[str, Account],
    fund_names: dict[str, str],
    output_dir: Path,
    base_currency: str = "CAD",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "dashboard.html"
    path.write_text(build_dashboard(valuations, accounts, fund_names, base_currency),
                    encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# period reports (daily / weekly / monthly, current period to date)
# ---------------------------------------------------------------------------

def _period_start(latest: date, period: str) -> date:
    if period == "weekly":
        return latest - timedelta(days=latest.weekday())
    if period == "monthly":
        return latest.replace(day=1)
    return latest  # daily: the day itself


def _fund_totals_on(valuations: list[Valuation], d: date) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for v in valuations:
        if v.date == d:
            out[v.fund] += v.market_value
    return out


def build_period_report(
    valuations: list[Valuation],
    accounts: dict[str, Account],
    fund_names: dict[str, str],
    transactions: list[Transaction],
    period: str,
    base_currency: str = "CAD",
) -> str:
    dates = sorted({v.date for v in valuations})
    latest = dates[-1]
    ws = _period_start(latest, period)

    total_by_date = _total_by_date(valuations)
    prior = [d for d in total_by_date if d < ws]
    start_date = max(prior) if prior else dates[0]
    start_value = total_by_date[start_date]
    end_value = total_by_date[latest]
    change = end_value - start_value

    contrib = 0.0
    for t in transactions:
        if start_date < t.date <= latest:
            contrib += t.units * t.price * (1 if t.action == "BUY" else -1)
    market = change - contrib

    title = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}[period]
    span = f"{ws.isoformat()} to {latest.isoformat()}"
    if period == "daily":
        span = latest.isoformat()

    header = (
        f'<h1>{title} Fund Report</h1>'
        f'<div class="sub">{_esc(span)} &middot; base currency {_esc(base_currency)}'
        f' &middot; <a href="dashboard.html">dashboard</a></div>'
    )
    cards = (
        '<div class="cards">'
        f'<div class="card"><div class="k">Start ({start_date.isoformat()})</div>'
        f'<div class="v">{_money(start_value)}</div></div>'
        f'<div class="card"><div class="k">End ({latest.isoformat()})</div>'
        f'<div class="v">{_money(end_value)}</div></div>'
        f'<div class="card"><div class="k">Change</div>'
        f'<div class="v {_cls(change)}">{_smoney(change)}'
        f'<span style="font-size:12px" class="muted"> '
        f'{_pct(change / start_value * 100) if start_value else ""}</span></div></div>'
        f'<div class="card"><div class="k">Contributions</div>'
        f'<div class="v {_cls(contrib)}">{_smoney(contrib)}</div>'
        f'<div class="d">market {_smoney(market)}</div></div>'
        "</div>"
    )

    # by account (institution grouped) over the period
    acct_start = {a: 0.0 for a in accounts}
    acct_end = {a: 0.0 for a in accounts}
    for v in valuations:
        if v.date == start_date:
            acct_start[v.account.account_id] += v.market_value
        elif v.date == latest:
            acct_end[v.account.account_id] += v.market_value
    inst_order = {a.institution: i for i, a in enumerate(accounts.values())}
    acc_rows = []
    by_inst: dict[str, list[str]] = defaultdict(list)
    for aid, a in accounts.items():
        by_inst[a.institution].append(aid)
    for inst, aids in by_inst.items():
        by_owner: dict[str, list[str]] = defaultdict(list)
        for a in aids:
            by_owner[accounts[a].owner].append(a)
        show_owner_subtotals = len(by_owner) > 1
        owner_order = sorted(by_owner.keys(), key=lambda o: (0 if o == "Fanny" else (1 if o == "KC" else 2), o))
        for owner in owner_order:
            o_aids = by_owner[owner]
            if show_owner_subtotals:
                s_o = sum(acct_start[a] for a in o_aids)
                e_o = sum(acct_end[a] for a in o_aids)
                acc_rows.append(
                    f'<tr class="sub"><td class="l">{_esc(owner)} subtotal</td>'
                    f'<td>{_money(s_o)}</td><td>{_money(e_o)}</td><td>{_chg(e_o - s_o, subtotal=True)}</td></tr>'
                )
            for a in sorted(o_aids):
                acc_rows.append(
                    f'<tr><td class="l">{_esc(accounts[a].name)} ({_esc(a)})</td>'
                    f'<td>{_money(acct_start[a])}</td><td>{_money(acct_end[a])}</td>'
                    f'<td>{_chg(acct_end[a] - acct_start[a])}</td></tr>'
                )
        s = sum(acct_start[a] for a in aids)
        e = sum(acct_end[a] for a in aids)
        acc_rows.append(
            f'<tr class="sub"><td class="l">{_esc(inst)} subtotal</td>'
            f'<td>{_money(s)}</td><td>{_money(e)}</td><td>{_chg(e - s, subtotal=True)}</td></tr>'
        )
    acc_rows.append(
        f'<tr class="total"><td class="l">CONSOLIDATED</td><td>{_money(start_value)}</td>'
        f'<td>{_money(end_value)}</td><td>{_chg(change)}</td></tr>'
    )
    acc_table = (
        '<div class="panel" style="margin-bottom:22px"><h2>By account</h2><table>'
        '<tr><th class="l">Account</th><th>Start</th><th>End</th><th>Change</th></tr>'
        + "".join(acc_rows) + "</table></div>"
    )

    # by fund over the period
    f_start = _fund_totals_on(valuations, start_date)
    f_end = _fund_totals_on(valuations, latest)
    fund_rows = []
    for fund in sorted(set(f_start) | set(f_end), key=lambda f: -(f_end.get(f, 0.0))):
        s = f_start.get(fund, 0.0)
        e = f_end.get(fund, 0.0)
        fund_rows.append(
            f'<tr><td class="l">{_esc(fund_names.get(fund, fund))} '
            f'<span class="chip">{_esc(fund)}</span></td>'
            f'<td>{_money(s)}</td><td>{_money(e)}</td><td>{_chg(e - s)}</td></tr>'
        )
    fund_table = (
        '<div class="panel" style="margin-bottom:22px"><h2>By fund</h2><table>'
        '<tr><th class="l">Fund</th><th>Start</th><th>End</th><th>Change</th></tr>'
        + "".join(fund_rows) + "</table></div>"
    )

    # daily rows within the period
    day_rows = []
    ordered = [d for d in dates if start_date < d <= latest]
    pv = start_value
    for d in ordered:
        val = total_by_date[d]
        day_rows.append(
            f'<tr><td class="l">{d.isoformat()}</td><td>{_money(val)}</td>'
            f'<td>{_chg(val - pv)}</td></tr>'
        )
        pv = val
    day_table = (
        '<div class="panel"><h2>Daily values</h2><table>'
        '<tr><th class="l">Date</th><th>Value</th><th>Change</th></tr>'
        + "".join(day_rows) + "</table></div>"
    )

    return _page(f"{title} Fund Report", header + cards + acc_table + fund_table + day_table)


def write_period_reports(
    valuations: list[Valuation],
    accounts: dict[str, Account],
    fund_names: dict[str, str],
    transactions: list[Transaction],
    output_dir: Path,
    base_currency: str = "CAD",
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for period in ("daily", "weekly", "monthly"):
        path = output_dir / f"{period}_report.html"
        path.write_text(
            build_period_report(
                valuations, accounts, fund_names, transactions, period, base_currency
            ),
            encoding="utf-8",
        )
        paths.append(path)
    return paths
