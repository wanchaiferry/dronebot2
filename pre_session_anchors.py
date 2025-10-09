"""Pre-session anchor preview tool.

Connects to IB, pulls the previous session's minute bars for each configured
symbol, and prints the AM and PM blended anchors plus ladder levels so you can
size clips ahead of the upcoming open.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
from typing import Dict, List, Optional, Tuple

from ib_insync import IB

from dronebot import (
    TZ,
    HOST,
    PORT,
    CLIENT_ID,
    TARGETS_TXT,
    BUY_LADDER_MULTS,
    SELL_LADDER_MULTS,
    AM_START,
    AM_END,
    PM_START,
    PM_END,
    read_targets,
    fetch_today_minute_bars,
    anchors_from_bars,
    blended_ref,
    dynamic_clip_usd,
)

# Use a separate client ID so we do not interfere with the live bot.
ANCHORBOT_CLIENT_ID = int(os.getenv("ANCHORBOT_CLIENT_ID", str(CLIENT_ID + 900)))


def log(msg: str) -> None:
    now = dt.datetime.now(TZ).strftime("%H:%M:%S")
    print(f"[{now}] {msg}")


def eastern_today() -> dt.date:
    return dt.datetime.now(TZ).date()


def level_grid(ref: Optional[float], pct: float, mults: List[float], direction: str) -> List[Optional[float]]:
    if ref is None:
        return [None for _ in mults]
    if direction == "down":
        return [ref * (1.0 - (pct * m) / 100.0) for m in mults]
    return [ref * (1.0 + (pct * m) / 100.0) for m in mults]


def format_price(px: Optional[float]) -> str:
    if px is None:
        return "      --"
    if px >= 100:
        return f"{px:8.2f}"
    if px >= 10:
        return f"{px:8.3f}"
    return f"{px:8.4f}"


def resolve_clip_usd(sym: str, last: Optional[float], rec: Dict[str, object], targets: Dict[str, dict]) -> Optional[float]:
    override = rec.get("clip")
    if override is not None:
        try:
            return float(override)
        except (TypeError, ValueError):
            pass
    if last is None:
        return None
    try:
        return dynamic_clip_usd(sym, float(last), targets)
    except Exception:
        return None


def previous_trading_day(day: dt.date) -> dt.date:
    prev = day - dt.timedelta(days=1)
    while prev.weekday() >= 5:  # Saturday/Sunday
        prev -= dt.timedelta(days=1)
    return prev


def bars_in_window(bars: List[object], start: dt.time, end: dt.time) -> List[object]:
    def eastern_time(bar) -> dt.time:
        return dt.datetime.fromtimestamp(bar.date.timestamp(), TZ).time()

    return [bar for bar in bars if start <= eastern_time(bar) < end]


def anchor_for_window(
    date: dt.date,
    window_bars: List[object],
    window_end: dt.time,
    buy_pct: float,
    sell_pct: float,
) -> Tuple[Optional[float], List[Optional[float]], List[Optional[float]]]:
    if not window_bars:
        return None, level_grid(None, buy_pct, BUY_LADDER_MULTS, "down"), level_grid(
            None, sell_pct, SELL_LADDER_MULTS, "up"
        )

    feats = anchors_from_bars(window_bars)
    last_close = getattr(window_bars[-1], "close", None)
    fallback = float(last_close) if last_close is not None else None
    anchor_time = dt.datetime.combine(date, window_end) - dt.timedelta(minutes=1)
    anchor_time = anchor_time.replace(tzinfo=TZ)
    ref = blended_ref(anchor_time, feats, fallback) if (feats or fallback) else fallback

    buy_levels = level_grid(ref, buy_pct, BUY_LADDER_MULTS, "down")
    sell_levels = level_grid(ref, sell_pct, SELL_LADDER_MULTS, "up")
    return ref, buy_levels, sell_levels


def run(ymd: Optional[str], targets_path: str) -> None:
    targets = read_targets(targets_path)
    if not targets:
        log(f"No tickers found in {targets_path}; nothing to do.")
        return

    session_date = dt.datetime.strptime(ymd, "%Y-%m-%d").date() if ymd else eastern_today()
    prev_date = previous_trading_day(session_date)
    log(
        "Fetching AM/PM anchors for %d symbols using %s session data..."
        % (len(targets), prev_date.isoformat())
    )

    ib = IB()
    try:
        ib.connect(HOST, PORT, clientId=ANCHORBOT_CLIENT_ID, readonly=True)
    except Exception as exc:
        log(f"Failed to connect to IB: {exc}")
        return

    windows = (("AM", AM_START, AM_END), ("PM", PM_START, PM_END))
    results = []

    for sym in sorted(targets):
        rec = targets[sym]
        try:
            _contract, bars = fetch_today_minute_bars(ib, sym, prev_date.strftime("%Y-%m-%d"))
        except Exception as exc:
            log(f"{sym}: error fetching bars: {exc}")
            continue

        last = bars[-1].close if bars else None
        buy_pct = max(0.1, float(rec.get("buy", 2.0)))
        sell_pct = max(0.1, float(rec.get("sell", 1.5)))
        clip_usd = resolve_clip_usd(sym, last, rec, targets)
        shares = int(round((clip_usd or 0) / last)) if clip_usd and last else None

        window_rows = {}
        for label, start, end in windows:
            window_bars = bars_in_window(bars, start, end)
            ref, buy_levels, sell_levels = anchor_for_window(
                prev_date, window_bars, end, buy_pct, sell_pct
            )
            window_rows[label] = {
                "anchor": ref,
                "buy_levels": buy_levels,
                "sell_levels": sell_levels,
            }

        results.append(
            {
                "sym": sym,
                "class": rec.get("class", "risky"),
                "last": last,
                "windows": window_rows,
                "clip_usd": clip_usd,
                "shares": shares,
            }
        )

    ib.disconnect()

    headers = ["SYM", "CLASS", "LAST"]
    for label, _, _ in windows:
        headers.extend(
            [
                f"{label}_ANC",
                f"{label}_L1",
                f"{label}_L2",
                f"{label}_L3",
                f"{label}_U1",
                f"{label}_U2",
                f"{label}_U3",
            ]
        )
    headers.extend(["CLIP$", "CLIP SH"])
    print("\n" + " ".join(f"{h:>8}" for h in headers))
    print("-" * (9 * len(headers)))

    for row in results:
        line = [
            f"{row['sym']:>8}",
            f"{row['class']:>8}",
            format_price(row["last"]),
        ]

        for label, _, _ in windows:
            window = row["windows"].get(label, {})
            line.append(format_price(window.get("anchor")))
            line.extend(format_price(px) for px in window.get("buy_levels", []))
            line.extend(format_price(px) for px in window.get("sell_levels", []))

        line.extend(
            [
                f"{row['clip_usd']:8.0f}" if row["clip_usd"] else "      --",
                f"{row['shares']:8d}" if row["shares"] else "      --",
            ]
        )
        print(" ".join(line))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print pre-session anchor ladder for configured tickers.")
    parser.add_argument("--date", help="Override the session date (YYYY-MM-DD). Defaults to today (US/Eastern).")
    parser.add_argument("--targets", default=TARGETS_TXT, help="Path to targets.txt configuration file.")
    args = parser.parse_args()
    run(args.date, args.targets)
