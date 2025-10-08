# Dronebot Live Trading Bot

## Overview
This repository contains a single Python trading bot that connects to Interactive Brokers (IB) and executes a live mean-reversion strategy focused on drone and defense-related tickers. The bot continuously evaluates streamed market data, enforces strict risk controls, and records fills and PnL snapshots for later review.

## Core Loop
* Connects to IB using configurable host, port, and client ID environment variables before entering a resilient reconnect loop. The bot restarts automatically on disconnects and logs any errors to `bot_errors.log` while sleeping briefly between retries.
* Streams market data for tickers defined in `targets.txt`, deriving blended reference prices from pre-market, initial balance, and regular trading hours median prices obtained via historical bar downloads.
* Computes a live volume-weighted volatility (VWV) z-score per symbol using recent dollar-volume increments to adapt buy/sell thresholds dynamically.
* Shows buy/sell ladder levels and submits Immediate-Or-Cancel (IOC) orders whenever the last price crosses the chosen anchor level. The bot only trades long, enforcing non-negative positions by syncing broker positions each loop and automatically covering any unexpected shorts.

## Risk Management
* Applies spread filters with class-specific limits, configurable hard stops, trailing stops, and breakeven trims to lock in gains when prices recover to average cost.
* Sizes trades dynamically based on per-class equity allocations, per-ticker budgets, and inverse price weighting; fixed USD clips can be supplied per ticker in `targets.txt`.

## Configuration & Outputs
* `targets.txt` configures ticker classes (`risky` / `safe`), percentage offsets for buys and trims, and optional clip overrides. Global allocations (class fractions and total live equity) can be adjusted via `@config` directives or environment variables.
* Executed fills append to `fills_live.csv`, and a running PnL log is written to `pnl_summary_live.csv`. Fatal errors are captured in `bot_errors.log` for troubleshooting.

## Utilities
* `init_venv.bat` bootstraps a Windows virtual environment and installs dependencies (`ib_insync`, `pandas`, `numpy`, `python-dateutil`).
* `run_live.bat` activates the environment, sets useful defaults for key environment variables, launches `dronebot.py`, and displays the tail of `bot_errors.log` if the bot exits unexpectedly.
