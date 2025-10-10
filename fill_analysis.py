from __future__ import annotations

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass
class Fill:
    timestamp: datetime
    symbol: str
    side: str
    quantity: int
    price: float
    reason: str
    realized_pnl: float

    @classmethod
    def from_row(cls, row: Sequence[str]) -> "Fill":
        if len(row) != 7:
            raise ValueError(f"Expected 7 columns per row, received {len(row)}: {row}")

        timestamp = datetime.fromisoformat(row[0])
        symbol = row[1].strip().upper()
        side = row[2].strip().upper()
        quantity = int(row[3])
        price = float(row[4])
        reason = row[5].strip()
        realized_pnl = float(row[6])
        return cls(timestamp, symbol, side, quantity, price, reason, realized_pnl)


def load_fills(path: Path | str) -> List[Fill]:
    path = Path(path)
    with path.open(newline="") as f:
        reader = csv.reader(f)
        return [Fill.from_row(row) for row in reader if row]


def describe_symbol_fills(fills: Iterable[Fill], symbol: str) -> str:
    symbol = symbol.upper()
    filtered = [fill for fill in fills if fill.symbol == symbol]
    if not filtered:
        return f"No fills found for {symbol}."

    buys = [f for f in filtered if f.side == "BUY"]
    sells = [f for f in filtered if f.side == "SELL"]

    total_buy_qty = sum(f.quantity for f in buys)
    total_sell_qty = sum(f.quantity for f in sells)
    gross_bought = sum(f.quantity * f.price for f in buys)
    gross_sold = sum(f.quantity * f.price for f in sells)

    avg_buy_price = gross_bought / total_buy_qty if total_buy_qty else 0.0
    avg_sell_price = gross_sold / total_sell_qty if total_sell_qty else 0.0

    realized_pnl = sum(f.realized_pnl for f in filtered)
    net_position = total_buy_qty - total_sell_qty
    net_cash_flow = gross_sold - gross_bought

    reasons = {}
    for f in filtered:
        reasons.setdefault(f.reason, 0)
        reasons[f.reason] += 1

    first_fill = min(filtered, key=lambda f: f.timestamp)
    last_fill = max(filtered, key=lambda f: f.timestamp)

    lines = [
        f"Symbol: {symbol}",
        f"Number of fills: {len(filtered)} (buys: {len(buys)}, sells: {len(sells)})",
        f"Net position: {net_position} shares",
        f"Total bought: {total_buy_qty} shares for ${gross_bought:,.2f} (avg ${avg_buy_price:.4f})",
        f"Total sold: {total_sell_qty} shares for ${gross_sold:,.2f} (avg ${avg_sell_price:.4f})",
        f"Net cash flow from sells minus buys: ${net_cash_flow:,.2f}",
        f"Realized PnL (reported): ${realized_pnl:,.2f}",
        "Fill reasons:",
    ]
    for reason, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"  • {reason}: {count}")

    lines.extend(
        [
            f"First fill: {first_fill.timestamp.isoformat()} {first_fill.side.lower()} {first_fill.quantity} @ ${first_fill.price}",
            f"Last fill: {last_fill.timestamp.isoformat()} {last_fill.side.lower()} {last_fill.quantity} @ ${last_fill.price}",
        ]
    )

    return "\n".join(lines)


def summarize_fills(fills: Sequence[Fill]) -> str:
    if not fills:
        return "No fills loaded."

    counts: Counter[str] = Counter()
    net_positions: Counter[str] = Counter()
    realized: Counter[str] = Counter()
    for fill in fills:
        counts[fill.symbol] += 1
        delta = fill.quantity if fill.side == "BUY" else -fill.quantity
        net_positions[fill.symbol] += delta
        realized[fill.symbol] += fill.realized_pnl

    symbol_width = max(max((len(sym) for sym in counts), default=0), len("Symbol"))
    total_realized = sum(realized.values())
    total_net = sum(net_positions.values())
    total_fills = sum(counts.values())

    lines = [
        f"{'Symbol':<{symbol_width}}  Fills  NetPos  RealizedPnL",
        f"{'-' * symbol_width}  -----  ------  ------------",
    ]
    for symbol in sorted(counts):
        lines.append(
            f"{symbol:<{symbol_width}}  {counts[symbol]:5}  {net_positions[symbol]:6}  ${realized[symbol]:11,.2f}"
        )
    lines.append(f"{'-' * symbol_width}  -----  ------  ------------")
    total_label = 'TOTAL'.ljust(symbol_width)
    lines.append(f"{total_label}  {total_fills:5}  {total_net:6}  ${total_realized:11,.2f}")
    return "\n".join(lines)


def interactive_symbol_prompt(fills: Sequence[Fill]) -> None:
    if not fills:
        print("No fills loaded.")
        return

    print("Enter a symbol to describe (leave blank to finish).")
    while True:
        try:
            symbol = input("Symbol: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not symbol:
            break
        print()
        print(describe_symbol_fills(fills, symbol))
        print()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill analysis utilities.")
    parser.add_argument(
        "csv",
        nargs="?",
        default="fills_live.csv",
        type=Path,
        help="Path to the fills CSV (default: fills_live.csv).",
    )
    parser.add_argument("--symbol", help="Describe a single symbol and exit.")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a per-symbol summary before exiting.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt repeatedly for symbols to describe.",
    )
    args = parser.parse_args(argv)

    csv_path = args.csv.expanduser()
    if not csv_path.exists():
        parser.error(f"Could not find fills CSV at '{csv_path}'.")

    fills = load_fills(csv_path)
    print(f"Loaded {len(fills)} fills from {csv_path}")
    print()

    if args.summary:
        print(summarize_fills(fills))
        print()

    if args.symbol:
        print(describe_symbol_fills(fills, args.symbol))
        print()

    if args.interactive:
        interactive_symbol_prompt(fills)

    if not (args.summary or args.symbol or args.interactive):
        # Default to a compact summary when no explicit action was requested.
        print(summarize_fills(fills))

    return 0


__all__ = [
    "Fill",
    "load_fills",
    "describe_symbol_fills",
    "summarize_fills",
    "interactive_symbol_prompt",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
