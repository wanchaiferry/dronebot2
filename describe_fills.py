from __future__ import annotations

import argparse
from pathlib import Path

from fill_analysis import describe_symbol_fills, load_fills


def main() -> None:
    parser = argparse.ArgumentParser(description="Describe fills for a specific symbol.")
    parser.add_argument("csv", type=Path, help="CSV file containing fills")
    parser.add_argument("symbol", help="Ticker symbol to describe")
    args = parser.parse_args()

    fills = load_fills(args.csv)
    print(describe_symbol_fills(fills, args.symbol))


if __name__ == "__main__":
    main()
