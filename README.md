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
* The ladder math treats every rung as live on both sides: the entry loop counts how many of the seven buy thresholds the last price has touched and immediately places shares for the next unused rung, while the trim loop checks all seven sell rungs to peel layers off in reverse when price recovers.【F:dronebot.py†L963-L999】 Because the rung clip multipliers start at 1.0× and climb through 2.3×, that first buy rung deploys the smallest notional and each additional dip adds progressively larger clips until the ladder is fully active.【F:dronebot.py†L115-L118】【F:dronebot.py†L951-L977】
* Ladder clips are denominated in USD and expand with depth (default multipliers run from 1.0x out to 2.3x of the base clip). The base clip itself is computed dynamically from the ticker's risk class, its share of the equity allocation, and the latest price; `targets.txt` can still override that baseline with a fixed `clip=` amount.
* Base buy/sell percentage offsets still originate from `targets.txt`. The configured `buy=` and `sell=` values are applied to every rung before the ladder is widened for the HUD, so per-ticker tuning continues to flow directly from the targets file.
* Capital sizing is tuned for roughly two-thirds utilization of the configured live equity (≈$100k when the default $150k budget is supplied). The dynamic plan recomputes share targets each loop so deeper ladders keep putting more notional to work as prices fall while trimming uses the same tiers when price reverses higher.
* VWV momentum gating still enforces that automated buys only fire when the current z-score is positive (buying into strength) and ladder or breakeven sells only trigger on negative z-scores (selling into weakness). Hard stops and trailing exits remain ungated so protective logic fires immediately on sharp reversals.

## Risk Management
* Applies spread filters with class-specific limits, configurable hard stops, trailing stops, and breakeven trims to lock in gains when prices recover to average cost.
* Sizes trades dynamically based on per-class equity allocations, per-ticker budgets, and inverse price weighting; fixed USD clips can be supplied per ticker in `targets.txt`.

## Configuration & Outputs
* `targets.txt` configures ticker classes (`risky` / `safe`), percentage offsets for buys and trims, and optional clip overrides. Global allocations (class fractions and total live equity) can be adjusted via `@config` directives or environment variables. The IB connection parameters (`IB_HOST`, `IB_PORT`, `IB_CID`) accept flexible inputs such as `localhost:4002` or `http://127.0.0.1`; the bot normalizes these into the host/port pair expected by the API and falls back to `127.0.0.1` if the provided hostname cannot be resolved.
* Executed fills append to `fills_live.csv`, and a running PnL log is written to `pnl_summary_live.csv`. Fatal errors are captured in `bot_errors.log` for troubleshooting.

## Utilities
* `init_venv.bat` bootstraps a Windows virtual environment from the repository directory and installs dependencies (`ib_insync`, `pandas`, `numpy`, `python-dateutil`). Run it once after cloning or whenever you need to recreate the `.venv` folder.
* `dronebot_launcher.bat` is a single Windows entry point that activates the environment and presents an interactive menu for launching the live bot, the entry dashboard, and the pre-session/fill review helpers. Each long-running process opens in its own Command Prompt window with the environment already activated.
* `pre_session_anchors.py` can still be run directly to print the previous session's AM and PM blended anchors, ladder levels, and clip sizing for each symbol configured in `targets.txt`. Use `python pre_session_anchors.py` (optionally `--date YYYY-MM-DD`) after connecting TWS or IB Gateway to review plan levels ahead of the session. The launcher calls this script for you and can optionally chain into the fill review helpers.
* `entry_dashboard.py` launches a lightweight HTTP server that renders a color-coded dashboard showing when entry conditions are satisfied. It now auto-detects the snapshot path, exposes a `/healthz` endpoint, and displays a status summary (counts of entry-ready / trim-ready / velocity-active symbols) alongside a more resilient UI that keeps retrying on fetch errors. Run `python entry_dashboard.py --host 0.0.0.0 --port 8765` while the bot is active, then open the reported URL in a browser to watch entry (green) and trim (red) readiness at a glance.
* `fill_analysis.py` exposes a small CLI: `python fill_analysis.py [fills_live.csv] --summary --interactive` prints a per-symbol table and then lets you iteratively request detailed stats for tickers. Add `--symbol XYZ` to immediately describe one symbol and exit, or run without flags to simply print the summary table.

### Entry dashboard controls & ladder math

The dashboard "sliders" are now numeric up/down inputs so you can tap or type the base percentage offsets precisely instead of dragging a range control. Each box writes back to `dashboard_overrides.json`, which the bot reads on its next loop, and the value shown in the badge underneath the control flips between **Default** and **Override** once the override file acknowledges the change.

These numbers set the *base* buy/sell percentages that come out of `targets.txt`. The live ladder widens those bases before printing the levels you see on screen: the bot multiplies the base value by a spread-class factor (5× for `risky`, 3× for `safe`) and then adjusts again for live VWV momentum (`buy_mult` and `sell_mult`).【F:dronebot.py†L867-L909】 As a result, a seemingly small 0.60% base buy offset still becomes roughly a 3% anchor for a risky symbol when the market is neutral (0.60 × 5 × 1.0 ≈ 3). The ladder rungs then fan out around that anchor using the `BUY_LADDER_MULTS`/`SELL_LADDER_MULTS` arrays so that rung four remains the live trigger while the surrounding tiers provide context.【F:dronebot.py†L112-L116】【F:dronebot.py†L890-L899】 If price action or spread conditions pull the anchors closer together, remember that the same multipliers continue to hold the actual execution levels apart — the display simply widens the outer rungs for readability without changing the trading triggers.【F:dronebot.py†L900-L913】

#### Worked override examples

The tables below show exactly how three different override inputs expand into ladder levels when the blended reference price is $100. In each case L4/U4 is the live trading anchor while the other rungs stay symmetric around it.【F:dronebot.py†L890-L903】 Percent offsets are rounded to three decimals and prices to two decimals for readability.

**Neutral risky (buy=0.60%, sell=0.60%, VWV z=0.0)**

| Rung | Buy % | Buy price | Sell % | Sell price |
| --- | --- | --- | --- | --- |
| L1/U1 | 1.125% | $98.88 | 1.125% | $101.12 |
| L2/U2 | 1.560% | $98.44 | 1.560% | $101.56 |
| L3/U3 | 2.163% | $97.84 | 2.163% | $102.16 |
| **L4/U4 (anchor)** | **3.000%** | **$97.00** | **3.000%** | **$103.00** |
| L5/U5 | 3.231% | $96.77 | 3.231% | $103.23 |
| L6/U6 | 3.480% | $96.52 | 3.480% | $103.48 |
| L7/U7 | 3.750% | $96.25 | 3.750% | $103.75 |

**Momentum risky (buy=0.60%, sell=0.60%, VWV z=+1.5)**

| Rung | Buy % | Buy price | Sell % | Sell price |
| --- | --- | --- | --- | --- |
| L1/U1 | 1.547% | $98.45 | 0.872% | $100.87 |
| L2/U2 | 2.145% | $97.86 | 1.209% | $101.21 |
| L3/U3 | 2.974% | $97.03 | 1.676% | $101.68 |
| **L4/U4 (anchor)** | **4.125%** | **$95.88** | **2.325%** | **$102.33** |
| L5/U5 | 4.443% | $95.56 | 2.504% | $102.50 |
| L6/U6 | 4.785% | $95.22 | 2.697% | $102.70 |
| L7/U7 | 5.156% | $94.84 | 2.906% | $102.91 |

**Safe class (buy=0.40%, sell=0.50%, VWV z=0.0)**

| Rung | Buy % | Buy price | Sell % | Sell price |
| --- | --- | --- | --- | --- |
| L1/U1 | 0.450% | $99.55 | 0.562% | $100.56 |
| L2/U2 | 0.624% | $99.38 | 0.780% | $100.78 |
| L3/U3 | 0.865% | $99.13 | 1.081% | $101.08 |
| **L4/U4 (anchor)** | **1.200%** | **$98.80** | **1.500%** | **$101.50** |
| L5/U5 | 1.292% | $98.71 | 1.615% | $101.62 |
| L6/U6 | 1.392% | $98.61 | 1.740% | $101.74 |
| L7/U7 | 1.500% | $98.50 | 1.875% | $101.88 |

How the numbers fall out:

* **Neutral risky example** – With a risky spread multiplier of 5× and neutral VWV momentum (multiplier 1.0), a 0.60% override produces a 3.00% anchor (`0.60 × 5 × 1.0`). That offset is applied at every rung multiplier so the ladder ranges from 1.125% to 3.75% below/above the reference.【F:dronebot.py†L112-L116】【F:dronebot.py†L885-L899】
* **Momentum risky example** – A +1.5 VWV z-score bumps the buy multiplier to 1.375 and trims the sell multiplier to 0.775, so the same 0.60% override yields a 4.125% buy anchor and a 2.325% sell anchor before the ladder fan-out.【F:dronebot.py†L867-L909】
* **Safe-class example** – Safe symbols use the 3× spread multiplier, so 0.40%/0.50% overrides translate into 1.200%/1.500% anchors even without momentum adjustment, producing a tighter ladder around the $100 reference.【F:dronebot.py†L885-L899】
