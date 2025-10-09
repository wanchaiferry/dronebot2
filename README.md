# Dronebot Live Trading Bot

## Overview
This repository contains a single Python trading bot that connects to Interactive Brokers (IB) and executes a live mean-reversion strategy focused on drone and defense-related tickers. The bot continuously evaluates streamed market data, enforces strict risk controls, and records fills and PnL snapshots for later review.

## Core Loop
* Connects to IB using configurable host, port, and client ID environment variables before entering a resilient reconnect loop. The bot restarts automatically on disconnects and logs any errors to `bot_errors.log` while sleeping briefly between retries.
* Streams market data for tickers defined in `targets.txt`, deriving blended reference prices from pre-market, initial balance, and regular trading hours median prices obtained via historical bar downloads.
* Computes a live volume-weighted volatility (VWV) z-score per symbol using recent dollar-volume increments to adapt buy/sell thresholds dynamically.
* Shows buy/sell ladder levels and submits Immediate-Or-Cancel (IOC) orders whenever the last price crosses the chosen anchor level. The bot only trades long, enforcing non-negative positions by syncing broker positions each loop and automatically covering any unexpected shorts.

## Ladder Levels & Clips
* Each ticker prints three ladder prices (L1/L2/L3 for buys and U1/U2/U3 for sells) around the blended reference. The multipliers remain centered so the mid rung reflects the live anchor while the outer rungs fan out for context.
* The bot now treats all three ladders as automated triggers. When price trades through L1, L2, or L3 while VWV momentum is positive, it scales in with progressively larger clips sized from the live plan. As price bounces into U1/U2/U3 with negative VWV momentum, the bot unwinds the matching rungs so the book steps down in the same order it was built.
* Ladder clips are denominated in USD and expand with depth (default multipliers are 1.0x/1.6x/2.3x of the base clip). The base clip itself is computed dynamically from the ticker's risk class, its share of the equity allocation, and the latest price; `targets.txt` can still override that baseline with a fixed `clip=` amount.
* Capital sizing is tuned for roughly two-thirds utilization of the configured live equity (≈$100k when the default $150k budget is supplied). The dynamic plan recomputes share targets each loop so deeper ladders keep putting more notional to work as prices fall while trimming uses the same tiers when price reverses higher.
* VWV momentum gating still enforces that automated buys only fire when the current z-score is positive (buying into strength) and ladder or breakeven sells only trigger on negative z-scores (selling into weakness). Hard stops and trailing exits remain ungated so protective logic fires immediately on sharp reversals.

## Risk Management
* Applies spread filters with class-specific limits, configurable hard stops, trailing stops, and breakeven trims to lock in gains when prices recover to average cost.
* Sizes trades dynamically based on per-class equity allocations, per-ticker budgets, and inverse price weighting; fixed USD clips can be supplied per ticker in `targets.txt`.

## Configuration & Outputs
* `targets.txt` configures ticker classes (`risky` / `safe`), percentage offsets for buys and trims, and optional clip overrides. Global allocations (class fractions and total live equity) can be adjusted via `@config` directives or environment variables.
* Executed fills append to `fills_live.csv`, and a running PnL log is written to `pnl_summary_live.csv`. Fatal errors are captured in `bot_errors.log` for troubleshooting.

## Utilities
* `init_venv.bat` bootstraps a Windows virtual environment and installs dependencies (`ib_insync`, `pandas`, `numpy`, `python-dateutil`).
* `run_live.bat` activates the environment, sets useful defaults for key environment variables, launches `dronebot.py`, and displays the tail of `bot_errors.log` if the bot exits unexpectedly.
* `pre_session_anchors.py` can be run before the opening bell to print the previous session's AM and PM blended anchors, ladder levels, and clip sizing for each symbol configured in `targets.txt`. Use `python pre_session_anchors.py` (optionally `--date YYYY-MM-DD`) after connecting TWS or IB Gateway to review plan levels ahead of the session.
