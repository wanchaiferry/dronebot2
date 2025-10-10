# Dronebot Live Trading Bot

## Overview
This repository contains a single Python trading bot that connects to Interactive Brokers (IB) and executes a live mean-reversion strategy focused on drone and defense-related tickers. The bot continuously evaluates streamed market data, enforces strict risk controls, and records fills and PnL snapshots for later review.

## Prerequisites
* Install a supported Python 3 interpreter (3.10+ recommended). On Windows download the official installer from [python.org](https://www.python.org/downloads/windows/) and ensure that the “Add python.exe to PATH” option is checked. After installation confirm availability with `py --version` or `python --version` from a new Command Prompt.
* If the `python` alias still opens the Microsoft Store, use `py` when running the helper scripts (`py pre_session_anchors.py`) or disable the Windows Store alias under *Settings → Apps → Advanced app settings → App execution aliases*.
* With Python in place, you can run `init_venv.bat` once to create the virtual environment and install dependencies before launching the utilities or live bot.

## Core Loop
* Connects to IB using configurable host, port, and client ID environment variables before entering a resilient reconnect loop. The bot restarts automatically on disconnects and logs any errors to `bot_errors.log` while sleeping briefly between retries.
* Streams market data for tickers defined in `targets.txt`, deriving blended reference prices from pre-market, initial balance, and regular trading hours median prices obtained via historical bar downloads.
* Computes a live volume-weighted volatility (VWV) z-score per symbol using recent dollar-volume increments to adapt buy/sell thresholds dynamically.
* Shows buy/sell ladder levels and submits Immediate-Or-Cancel (IOC) orders whenever the last price crosses the chosen anchor level. The bot only trades long, enforcing non-negative positions by syncing broker positions each loop and automatically covering any unexpected shorts.

## Ladder Levels & Clips
* Each ticker prints seven ladder prices (L1–L7 for buys and U1–U7 for sells) around the blended reference. The multipliers remain centered so the mid rung reflects the live anchor while the outer rungs fan out for context without shifting the automated trigger.
* All seven rungs act as automated entries/exits. When price trades through deeper buy levels while VWV momentum is positive, the bot scales in with progressively larger clips sized from the live plan. As price bounces into any of the seven sell rungs with negative VWV momentum, the bot unwinds the matching tier so the position steps down in the same order it was built.
* Ladder clips are denominated in USD and expand with depth (default multipliers run from 1.0x out to 2.3x of the base clip). The base clip itself is computed dynamically from the ticker's risk class, its share of the equity allocation, and the latest price; `targets.txt` can still override that baseline with a fixed `clip=` amount.
* Base buy/sell percentage offsets still originate from `targets.txt`. The configured `buy=` and `sell=` values are applied to every rung before the ladder is widened for the HUD, so per-ticker tuning continues to flow directly from the targets file.
* Capital sizing is tuned for roughly two-thirds utilization of the configured live equity (≈$100k when the default $150k budget is supplied). The dynamic plan recomputes share targets each loop so deeper ladders keep putting more notional to work as prices fall while trimming uses the same tiers when price reverses higher.
* VWV momentum gating still enforces that automated buys only fire when the current z-score is positive (buying into strength) and ladder or breakeven sells only trigger on negative z-scores (selling into weakness). Hard stops and trailing exits remain ungated so protective logic fires immediately on sharp reversals.

## Risk Management
* Applies spread filters with class-specific limits, configurable hard stops, trailing stops, and breakeven trims to lock in gains when prices recover to average cost.
* Sizes trades dynamically based on per-class equity allocations, per-ticker budgets, and inverse price weighting; fixed USD clips can be supplied per ticker in `targets.txt`.

## Configuration & Outputs
* `targets.txt` configures ticker classes (`risky` / `safe`), percentage offsets for buys and trims, and optional clip overrides. Global allocations (class fractions and total live equity) can be adjusted via `@config` directives or environment variables.
* Executed fills append to `fills_live.csv`, and a running PnL log is written to `pnl_summary_live.csv`. Fatal errors are captured in `bot_errors.log` for troubleshooting.

## Utilities
* `init_venv.bat` bootstraps a Windows virtual environment from the repository directory and installs dependencies (`ib_insync`, `pandas`, `numpy`, `python-dateutil`). Run it once after cloning or whenever you need to recreate the `.venv` folder.
* `dronebot_launcher.bat` is a single Windows entry point that activates the environment and presents an interactive menu for launching the live bot, the entry dashboard, and the pre-session/fill review helpers. Each long-running process opens in its own Command Prompt window with the environment already activated.
* `pre_session_anchors.py` can still be run directly to print the previous session's AM and PM blended anchors, ladder levels, and clip sizing for each symbol configured in `targets.txt`. Use `python pre_session_anchors.py` (optionally `--date YYYY-MM-DD`) after connecting TWS or IB Gateway to review plan levels ahead of the session. The launcher calls this script for you and can optionally chain into the fill review helpers.
* `entry_dashboard.py` launches a lightweight HTTP server that renders a color-coded dashboard showing when entry conditions are satisfied. It now auto-detects the snapshot path, exposes a `/healthz` endpoint, and displays a status summary (counts of entry-ready / trim-ready / velocity-active symbols) alongside a more resilient UI that keeps retrying on fetch errors. Run `python entry_dashboard.py --host 0.0.0.0 --port 8765` while the bot is active, then open the reported URL in a browser to watch entry (green) and trim (red) readiness at a glance.
* `fill_analysis.py` exposes a small CLI: `python fill_analysis.py [fills_live.csv] --summary --interactive` prints a per-symbol table and then lets you iteratively request detailed stats for tickers. Add `--symbol XYZ` to immediately describe one symbol and exit, or run without flags to simply print the summary table.
