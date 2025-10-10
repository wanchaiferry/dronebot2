"""Lightweight HTTP dashboard for monitoring dronebot entry conditions."""
from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple


_LAST_SNAPSHOT_NOTICE: Tuple[str | None, str | None] = (None, None)

_OVERRIDES_LOCK = threading.Lock()


def _read_overrides(path: Path) -> Dict[str, Dict[str, float]]:
    try:
        with path.open('r', encoding='utf-8') as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        print(f'Override file {path} is not valid JSON ({exc}). Ignoring contents.')
        return {}
    except OSError as exc:
        print(f'Unable to read override file {path}: {exc}.')
        return {}

    if not isinstance(raw, dict):
        return {}

    overrides: Dict[str, Dict[str, float]] = {}
    for sym, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        entry: Dict[str, float] = {}
        try:
            if 'buy' in payload:
                entry['buy'] = max(0.05, float(payload['buy']))
        except (TypeError, ValueError):
            pass
        try:
            if 'sell' in payload:
                entry['sell'] = max(0.05, float(payload['sell']))
        except (TypeError, ValueError):
            pass
        if entry:
            overrides[str(sym).upper()] = entry
    return overrides


def _write_overrides(path: Path, overrides: Dict[str, Dict[str, float]]) -> None:
    tmp_path = path.with_suffix(path.suffix + '.tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    with tmp_path.open('w', encoding='utf-8') as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def update_symbol_override(
    symbol: str,
    buy: float | None,
    sell: float | None,
    path: Path | None = None,
) -> Dict[str, float]:
    symbol_key = symbol.upper()
    override_path = path or DASHBOARD_OVERRIDES_PATH
    with _OVERRIDES_LOCK:
        overrides = _read_overrides(override_path)
        entry = overrides.get(symbol_key, {}).copy()
        if buy is not None:
            entry['buy'] = max(0.05, float(buy))
        if sell is not None:
            entry['sell'] = max(0.05, float(sell))
        entry = {k: v for k, v in entry.items() if v is not None}
        if entry:
            overrides[symbol_key] = entry
        elif symbol_key in overrides:
            overrides.pop(symbol_key, None)
        _write_overrides(override_path, overrides)
        return overrides.get(symbol_key, {})


def _format_snapshot_path(candidate: str | os.PathLike[str]) -> Path:
    path = Path(candidate).expanduser()
    try:
        return path.resolve()
    except OSError:
        # Fall back to the expanded path if resolve() fails (e.g. missing parents).
        return path


def _default_snapshot_path() -> Path:
    env_path = os.getenv('DASHBOARD_SNAPSHOT_PATH')
    if env_path:
        return _format_snapshot_path(env_path)
    return _format_snapshot_path(Path(__file__).with_name('dashboard_snapshot.json'))


def _default_overrides_path() -> Path:
    env_path = os.getenv('DASHBOARD_OVERRIDES_PATH')
    if env_path:
        return _format_snapshot_path(env_path)
    return _format_snapshot_path(Path(__file__).with_name('dashboard_overrides.json'))


DASHBOARD_OVERRIDES_PATH = _default_overrides_path()

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Dronebot Entry Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #0f172a;
      color: #e2e8f0;
    }
    body {
      margin: 0;
      padding: 24px;
      background: radial-gradient(circle at top, rgba(59,130,246,0.15), transparent 45%), #0f172a;
      min-height: 100vh;
    }
    h1 {
      margin-top: 0;
      font-size: 1.8rem;
      letter-spacing: 0.04em;
    }
    .updated {
      margin-bottom: 8px;
      font-size: 0.9rem;
      color: #94a3b8;
    }
    .summary {
      margin-bottom: 20px;
      font-size: 0.95rem;
      color: #cbd5f5;
    }
    .constants {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 20px;
    }
    .constants.hidden {
      display: none;
    }
    .constant-chip {
      background: rgba(30, 64, 175, 0.2);
      border: 1px solid rgba(96, 165, 250, 0.45);
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 0.8rem;
      color: #bfdbfe;
      box-shadow: inset 0 0 12px rgba(59,130,246,0.12);
    }
    .constant-chip .label {
      display: block;
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #c7d2fe;
      margin-bottom: 2px;
    }
    .constant-chip .value {
      font-weight: 600;
      font-size: 0.95rem;
      color: #e0f2fe;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      background-color: rgba(15, 23, 42, 0.65);
      backdrop-filter: blur(10px);
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 20px 40px rgba(15,23,42,0.45);
    }
    thead th {
      text-align: left;
      font-weight: 600;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      padding: 12px 16px;
      color: #cbd5f5;
      background-color: rgba(30, 41, 59, 0.9);
    }
    tbody td {
      padding: 12px 16px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.15);
      font-size: 0.95rem;
      white-space: nowrap;
    }
    tbody tr:last-child td {
      border-bottom: none;
    }
    tbody tr:hover td:not(.level-cell) {
      background-color: rgba(59,130,246,0.12);
    }
    .symbol-cell {
      font-weight: 600;
      letter-spacing: 0.05em;
    }
    .symbol-cell .signal-dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      margin-right: 6px;
      vertical-align: middle;
      background: rgba(34,197,94,0.9);
      box-shadow: 0 0 8px rgba(34,197,94,0.75);
      animation: pulse 1.6s ease-in-out infinite;
    }
    .symbol-cell .signal-dot.sell {
      background: rgba(239,68,68,0.9);
      box-shadow: 0 0 8px rgba(239,68,68,0.7);
      animation: pulseRed 1.6s ease-in-out infinite;
    }
    .symbol-cell .signal-dot.scout {
      background: rgba(74,222,128,0.7);
      box-shadow: 0 0 6px rgba(74,222,128,0.6);
      animation: scoutPulse 1.8s ease-in-out infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 0.4; transform: scale(0.9); }
      50% { opacity: 1; transform: scale(1.1); }
    }
    @keyframes pulseRed {
      0%, 100% { opacity: 0.55; transform: scale(0.9); }
      50% { opacity: 1; transform: scale(1.1); }
    }
    @keyframes scoutPulse {
      0%, 100% { opacity: 0.25; transform: scale(0.85); }
      50% { opacity: 0.8; transform: scale(1.05); }
    }
    .symbol-cell.symbol-buy {
      background: linear-gradient(135deg, rgba(34,197,94,0.35), rgba(16,185,129,0.15));
      color: #022c22;
    }
    .symbol-cell.symbol-sell {
      background: linear-gradient(135deg, rgba(248,113,113,0.4), rgba(239,68,68,0.2));
      color: #450a0a;
    }
    tbody tr.buy-interest td:first-child {
      border-left: 3px solid rgba(34,197,94,0.6);
    }
    tbody tr.sell-interest td:first-child {
      border-left: 3px solid rgba(248,113,113,0.6);
    }
    tbody tr.buy-ready-row td {
      background-image: linear-gradient(90deg, rgba(34,197,94,0.18), transparent 75%);
    }
    tbody tr.buy-ready-row td.level-cell {
      background-image: none;
    }
    tbody tr.sell-ready-row td {
      background-image: linear-gradient(90deg, rgba(248,113,113,0.12), transparent 75%);
    }
    tbody tr.sell-ready-row td.level-cell {
      background-image: none;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
      letter-spacing: 0.04em;
    }
    .entry-true {
      background: linear-gradient(135deg, #059669, #34d399);
      color: #022c22;
    }
    .entry-false {
      background: rgba(15,118,110,0.2);
      color: #5eead4;
    }
    .sell-true {
      background: linear-gradient(135deg, #f87171, #ef4444);
      color: #450a0a;
    }
    .sell-false {
      background: rgba(248,113,113,0.15);
      color: #fecaca;
    }
    .velocity-true {
      background: linear-gradient(135deg, #818cf8, #6366f1);
      color: #eef2ff;
    }
    .velocity-false {
      background: rgba(99,102,241,0.25);
      color: #c7d2fe;
    }
    .entry-scout {
      background: rgba(16,185,129,0.25);
      color: #6ee7b7;
      border: 1px solid rgba(16,185,129,0.45);
    }
    .status {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .numeric {
      font-variant-numeric: tabular-nums;
    }
    .level-cell {
      font-variant-numeric: tabular-nums;
      border-radius: 8px;
      transition: background-color 0.3s ease, color 0.3s ease;
    }
    .level-cell .level-price {
      display: block;
      font-weight: 600;
    }
    .level-cell .level-delta {
      display: block;
      font-size: 0.75rem;
      opacity: 0.85;
    }
    .slider-cell {
      min-width: 180px;
    }
    .slider-wrapper {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .slider-value {
      font-size: 0.85rem;
      letter-spacing: 0.04em;
      color: #f8fafc;
      text-shadow: 0 0 6px rgba(59,130,246,0.35);
    }
    .slider-value.buy {
      color: #fecaca;
      text-shadow: 0 0 8px rgba(248,113,113,0.45);
    }
    .slider-value.sell {
      color: #bbf7d0;
      text-shadow: 0 0 8px rgba(34,197,94,0.45);
    }
    .slider-input {
      width: 90px;
      padding: 6px 10px;
      border-radius: 8px;
      border: 1px solid rgba(148, 163, 184, 0.25);
      background: rgba(15, 23, 42, 0.6);
      color: #f8fafc;
      font-size: 0.95rem;
      font-variant-numeric: tabular-nums;
      text-align: right;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .slider-input.buy {
      border-color: rgba(248, 113, 113, 0.35);
      box-shadow: inset 0 0 8px rgba(248, 113, 113, 0.15);
    }
    .slider-input.sell {
      border-color: rgba(34, 197, 94, 0.35);
      box-shadow: inset 0 0 8px rgba(34, 197, 94, 0.15);
    }
    .slider-input:focus {
      outline: none;
      border-color: rgba(96, 165, 250, 0.65);
      box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.35);
    }
    .slider-input::-webkit-outer-spin-button,
    .slider-input::-webkit-inner-spin-button {
      opacity: 0.6;
    }
    .slider-status {
      font-size: 0.7rem;
      color: #94a3b8;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .chart-cell {
      min-width: 160px;
      padding: 0 12px;
    }
    .chart-wrapper {
      width: 100%;
      height: 60px;
    }
    .chart-svg {
      width: 100%;
      height: 100%;
      display: block;
    }
    .chart-line {
      fill: none;
      stroke-width: 1.6;
      vector-effect: non-scaling-stroke;
      opacity: 0.9;
    }
    .chart-line.price {
      stroke: #f8fafc;
      opacity: 1;
      stroke-width: 2;
    }
    .chart-line.buy {
      stroke: #fca5a5;
      stroke-dasharray: 4 2;
    }
    .chart-line.sell {
      stroke: #86efac;
      stroke-dasharray: 4 2;
    }
    .chart-band {
      fill: rgba(148, 163, 184, 0.12);
    }
    .chart-marker {
      fill: #f8fafc;
      stroke: rgba(15, 23, 42, 0.6);
      stroke-width: 1.2;
    }
    .velocity-cell {
      border-radius: 8px;
      padding: 8px 12px;
      text-align: right;
      font-variant-numeric: tabular-nums;
      display: flex;
      flex-direction: column;
      gap: 4px;
      align-items: flex-end;
      transition: background-color 0.3s ease, color 0.3s ease, box-shadow 0.3s ease;
    }
    .velocity-cell .velocity-main {
      display: flex;
      align-items: baseline;
      gap: 6px;
      font-weight: 600;
      font-size: 0.95rem;
    }
    .velocity-cell .velocity-arrow {
      font-size: 1.1rem;
      line-height: 1;
      letter-spacing: -0.02em;
    }
    .velocity-cell .velocity-status {
      font-size: 0.68rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      opacity: 0.8;
    }
    .velocity-cell.positive {
      box-shadow: inset 0 0 0 1px rgba(34, 197, 94, 0.45);
    }
    .velocity-cell.negative {
      box-shadow: inset 0 0 0 1px rgba(248, 113, 113, 0.45);
    }
    .velocity-cell.neutral {
      box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.35);
      color: #cbd5f5;
      background: rgba(148, 163, 184, 0.18);
    }
    .velocity-cell.active {
      box-shadow: inset 0 0 0 1px rgba(248, 250, 252, 0.35), 0 8px 16px rgba(15, 23, 42, 0.35);
    }
    .velocity-cell.dim {
      opacity: 0.75;
    }
    .ladder-wrapper {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px 12px;
      margin-top: 8px;
      font-size: 0.72rem;
    }
    .ladder-meta {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px 12px;
      margin-top: 8px;
      font-size: 0.72rem;
    }
    .ladder-next {
      padding: 6px 8px;
      border-radius: 6px;
      background: rgba(30, 41, 59, 0.65);
      border: 1px solid rgba(148, 163, 184, 0.2);
      display: flex;
      flex-direction: column;
      gap: 2px;
      font-variant-numeric: tabular-nums;
    }
    .ladder-next.buy {
      background: rgba(248, 113, 113, 0.16);
      border-color: rgba(248, 113, 113, 0.28);
      color: #fee2e2;
    }
    .ladder-next.sell {
      background: rgba(34, 197, 94, 0.16);
      border-color: rgba(34, 197, 94, 0.28);
      color: #dcfce7;
    }
    .ladder-next .label {
      text-transform: uppercase;
      font-size: 0.62rem;
      letter-spacing: 0.08em;
      color: #94a3b8;
    }
    .ladder-next.buy .label {
      color: rgba(254, 226, 226, 0.85);
    }
    .ladder-next.sell .label {
      color: rgba(220, 252, 231, 0.85);
    }
    .ladder-next .value {
      font-weight: 600;
      color: #e2e8f0;
    }
    .ladder-column {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .ladder-column .ladder-title {
      text-transform: uppercase;
      font-size: 0.62rem;
      letter-spacing: 0.08em;
      color: #94a3b8;
    }
    .ladder-rungs {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .ladder-empty {
      font-size: 0.65rem;
      color: #64748b;
      padding: 4px 0;
    }
    .ladder-rung {
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 6px;
      align-items: baseline;
      padding: 4px 6px;
      border-radius: 6px;
      background: rgba(30, 41, 59, 0.65);
      border: 1px solid rgba(148, 163, 184, 0.16);
      color: #e2e8f0;
      font-variant-numeric: tabular-nums;
    }
    .ladder-rung.buy {
      background: rgba(248, 113, 113, 0.18);
      border-color: rgba(248, 113, 113, 0.28);
      color: #fee2e2;
    }
    .ladder-rung.sell {
      background: rgba(34, 197, 94, 0.14);
      border-color: rgba(34, 197, 94, 0.24);
      color: #dcfce7;
    }
    .ladder-rung.active {
      box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.45), 0 6px 14px rgba(15, 23, 42, 0.35);
      transform: translateY(-1px);
    }
    .ladder-rung .rung-index {
      font-weight: 600;
      letter-spacing: 0.04em;
      opacity: 0.8;
    }
    .ladder-rung .rung-price {
      font-weight: 600;
    }
    .ladder-rung .rung-delta {
      font-size: 0.65rem;
      color: #cbd5f5;
      justify-self: end;
    }
    .ladder-alert {
      margin-top: 8px;
      padding: 6px 10px;
      border-radius: 6px;
      background: rgba(248, 113, 113, 0.18);
      border: 1px solid rgba(248, 113, 113, 0.35);
      color: #fecaca;
      font-size: 0.68rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .ladder-alert .label {
      font-weight: 700;
    }
    .chart-cell.ladder-overlap {
      box-shadow: inset 0 0 0 2px rgba(248, 113, 113, 0.25);
      border-radius: 10px;
    }
    .placeholder {
      padding: 32px;
      text-align: center;
      color: #94a3b8;
      font-size: 1rem;
    }
  </style>
</head>
<body>
  <h1>Dronebot Entry Dashboard</h1>
  <div class=\"updated\" id=\"updated\">Waiting for snapshot…</div>
  <div class=\"summary\" id=\"summary\">No symbols loaded yet.</div>
  <div class=\"constants hidden\" id=\"constants\"></div>
  <div id=\"table-container\"></div>
  <template id=\"table-template\">
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Last</th>
          <th>Reference</th>
          <th>Next Buy</th>
          <th>Next Sell</th>
          <th>Price · Ladders</th>
          <th>Buy %</th>
          <th>Sell %</th>
          <th>VWV Z</th>
          <th>Velocity</th>
          <th>Layers</th>
          <th>Position</th>
          <th>Avg Cost</th>
          <th>Clip $</th>
          <th>Unrealized</th>
          <th>Signals</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </template>
  <script>
    const tableContainer = document.getElementById('table-container');
    const updatedLabel = document.getElementById('updated');
    const summaryLabel = document.getElementById('summary');
    const constantsPanel = document.getElementById('constants');
    const template = document.getElementById('table-template');

    function formatNumber(value, fractionDigits = 2) {
      if (value === null || value === undefined) {
        return '—';
      }
      const num = Number(value);
      if (!Number.isFinite(num)) {
        return '—';
      }
      return num.toLocaleString(undefined, {
        minimumFractionDigits: fractionDigits,
        maximumFractionDigits: fractionDigits,
      });
    }

    function toNumber(value, fallback = 0) {
      const num = Number(value);
      return Number.isFinite(num) ? num : fallback;
    }

    const chartState = new Map();
    const CHART_MAX_POINTS = 160;
    const CHART_WIDTH = 160;
    const CHART_HEIGHT = 60;

    function ensureChartState(symbol) {
      if (!chartState.has(symbol)) {
        chartState.set(symbol, {
          points: [],
          lastBuy: null,
          lastSell: null,
          svg: null,
        });
      }
      return chartState.get(symbol);
    }

    function recordChartPoint(symbol) {
      const key = symbol.symbol;
      if (!key || key === '—') {
        return;
      }
      const state = ensureChartState(key);
      const now = Date.now();
      const price = Number(symbol.last);
      const buyLevel = Number(symbol.next_buy_level);
      const sellLevel = Number(symbol.next_sell_level);

      const point = {
        timestamp: now,
        price: Number.isFinite(price) ? price : null,
        buy: null,
        sell: null,
      };

      if (Number.isFinite(buyLevel)) {
        state.lastBuy = buyLevel;
        point.buy = buyLevel;
      } else if (typeof state.lastBuy === 'number') {
        point.buy = state.lastBuy;
      }

      if (Number.isFinite(sellLevel)) {
        state.lastSell = sellLevel;
        point.sell = sellLevel;
      } else if (typeof state.lastSell === 'number') {
        point.sell = state.lastSell;
      }

      if (point.price === null && point.buy === null && point.sell === null) {
        return;
      }

      state.points.push(point);
      if (state.points.length > CHART_MAX_POINTS) {
        state.points.splice(0, state.points.length - CHART_MAX_POINTS);
      }
    }

    function renderChart(symbol) {
      const state = chartState.get(symbol);
      if (!state || !state.svg) {
        return;
      }
      const svg = state.svg;
      const points = state.points;
      if (!points.length) {
        svg.innerHTML = '';
        return;
      }

      let minValue = Number.POSITIVE_INFINITY;
      let maxValue = Number.NEGATIVE_INFINITY;
      for (const point of points) {
        for (const key of ['price', 'buy', 'sell']) {
          const value = point[key];
          if (typeof value === 'number' && Number.isFinite(value)) {
            if (value < minValue) minValue = value;
            if (value > maxValue) maxValue = value;
          }
        }
      }

      if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
        svg.innerHTML = '';
        return;
      }

      if (minValue === maxValue) {
        const delta = Math.max(0.5, Math.abs(minValue) * 0.005);
        minValue -= delta;
        maxValue += delta;
      }

      const span = Math.max(1, maxValue - minValue);
      const startTs = points[0].timestamp;
      const endTs = points[points.length - 1].timestamp;
      const tsSpan = Math.max(1, endTs - startTs);

      const buildPath = (key) => {
        let d = '';
        let penDown = false;
        points.forEach((point) => {
          const value = point[key];
          if (typeof value === 'number' && Number.isFinite(value)) {
            const x = ((point.timestamp - startTs) / tsSpan) * CHART_WIDTH;
            const y = CHART_HEIGHT - ((value - minValue) / span) * CHART_HEIGHT;
            if (!penDown) {
              d += `M${x.toFixed(2)} ${y.toFixed(2)}`;
              penDown = true;
            } else {
              d += ` L${x.toFixed(2)} ${y.toFixed(2)}`;
            }
          } else {
            penDown = false;
          }
        });
        return d;
      };

      const pricePath = buildPath('price');
      const buyPath = buildPath('buy');
      const sellPath = buildPath('sell');

      svg.innerHTML = '';

      const band = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      band.setAttribute('class', 'chart-band');
      band.setAttribute('x', '0');
      band.setAttribute('y', '0');
      band.setAttribute('width', String(CHART_WIDTH));
      band.setAttribute('height', String(CHART_HEIGHT));
      svg.appendChild(band);

      const appendPath = (pathData, cls) => {
        if (!pathData) {
          return;
        }
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', pathData);
        path.setAttribute('class', `chart-line ${cls}`);
        svg.appendChild(path);
      };

      appendPath(buyPath, 'buy');
      appendPath(sellPath, 'sell');
      appendPath(pricePath, 'price');

      const lastPoint = points[points.length - 1];
      if (lastPoint && typeof lastPoint.price === 'number' && Number.isFinite(lastPoint.price)) {
        const x = CHART_WIDTH;
        const y = CHART_HEIGHT - ((lastPoint.price - minValue) / span) * CHART_HEIGHT;
        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        marker.setAttribute('class', 'chart-marker');
        marker.setAttribute('cx', x.toFixed(2));
        marker.setAttribute('cy', y.toFixed(2));
        marker.setAttribute('r', '2.6');
        svg.appendChild(marker);
      }
    }

    function formatLayers(active, target, sellHit) {
      const layersActive = toNumber(active, 0);
      const layersTarget = toNumber(target, 0);
      const sells = toNumber(sellHit, 0);
      return `${layersActive}/${layersTarget} ↑${sells}`;
    }

    function createNumericCell(value, fractionDigits = 2) {
      const td = document.createElement('td');
      td.textContent = formatNumber(value, fractionDigits);
      td.classList.add('numeric');
      return td;
    }

    function createVelocityCell(symbol) {
      const td = document.createElement('td');
      td.classList.add('velocity-cell');

      const main = document.createElement('div');
      main.classList.add('velocity-main');

      const arrowSpan = document.createElement('span');
      arrowSpan.classList.add('velocity-arrow');

      const valueSpan = document.createElement('span');
      valueSpan.classList.add('velocity-value');

      main.appendChild(arrowSpan);
      main.appendChild(valueSpan);
      td.appendChild(main);

      const statusSpan = document.createElement('div');
      statusSpan.classList.add('velocity-status');
      td.appendChild(statusSpan);

      const bpsRaw = Number(symbol.velocity_bps);
      const hasBps = Number.isFinite(bpsRaw);
      const velocityActive = Boolean(symbol.velocity_active);
      const velocityReady = Boolean(symbol.velocity_ready);

      let direction = 'neutral';
      if (hasBps) {
        if (bpsRaw > 0.01) direction = 'positive';
        else if (bpsRaw < -0.01) direction = 'negative';
      }

      const arrowChar = direction === 'positive' ? '>' : direction === 'negative' ? '<' : '·';
      arrowSpan.textContent = arrowChar;
      valueSpan.textContent = hasBps ? `${Math.abs(bpsRaw).toFixed(1)} bps` : '—';

      if (velocityActive) {
        statusSpan.textContent = 'Velocity Triggered';
        td.classList.add('active');
      } else if (velocityReady) {
        statusSpan.textContent = 'Velocity Primed';
      } else if (hasBps) {
        statusSpan.textContent = 'Velocity Watching';
        td.classList.add('dim');
      } else {
        statusSpan.textContent = 'Velocity Offline';
        td.classList.add('dim');
      }

      const magnitude = hasBps ? Math.min(1, Math.abs(bpsRaw) / 25) : 0;
      let alpha = 0.2 + magnitude * 0.55;
      if (velocityActive) {
        alpha = Math.min(0.95, alpha + 0.25);
      } else if (velocityReady) {
        alpha = Math.min(0.9, alpha + 0.1);
      }

      if (direction === 'positive') {
        td.classList.add('positive');
        const background = `rgba(34, 197, 94, ${alpha.toFixed(3)})`;
        td.style.backgroundColor = background;
        td.style.color = alpha > 0.55 ? '#022c22' : '#dcfce7';
      } else if (direction === 'negative') {
        td.classList.add('negative');
        const background = `rgba(248, 113, 113, ${alpha.toFixed(3)})`;
        td.style.backgroundColor = background;
        td.style.color = alpha > 0.55 ? '#450a0a' : '#fee2e2';
      } else {
        td.classList.add('neutral');
      }

      if (!hasBps) {
        arrowSpan.style.opacity = '0.6';
        valueSpan.style.opacity = '0.8';
      }

      return td;
    }

    function formatDelta(level, last) {
      const levelNum = Number(level);
      const lastNum = Number(last);
      if (!Number.isFinite(levelNum) || !Number.isFinite(lastNum) || lastNum === 0) {
        return '';
      }
      const pct = ((levelNum - lastNum) / lastNum) * 100;
      const sign = pct > 0 ? '+' : '';
      return `${sign}${pct.toFixed(2)}%`;
    }

    function applyLevelStyling(td, type, index, count) {
      if (!(td instanceof HTMLElement)) {
        return;
      }
      if (typeof index !== 'number' || !Number.isFinite(index)) {
        return;
      }
      if (typeof count !== 'number' || !Number.isFinite(count) || count <= 0) {
        return;
      }
      const safeCount = Math.max(1, count);
      let ratio;
      if (type === 'buy') {
        ratio = 1 - Math.min(1, Math.max(0, index / safeCount));
      } else {
        ratio = Math.min(1, Math.max(0, (index + 1) / safeCount));
      }
      const baseAlpha = 0.16 + 0.36 * ratio;
      if (type === 'buy') {
        td.style.backgroundColor = `rgba(248, 113, 113, ${baseAlpha.toFixed(3)})`;
        td.style.color = ratio > 0.55 ? '#450a0a' : '#fee2e2';
      } else {
        td.style.backgroundColor = `rgba(34, 197, 94, ${baseAlpha.toFixed(3)})`;
        td.style.color = ratio > 0.55 ? '#022c22' : '#dcfce7';
      }
    }

    function createLevelCell(symbol, type) {
      const td = document.createElement('td');
      td.classList.add('numeric', 'level-cell');
      td.classList.add(type === 'buy' ? 'buy-level' : 'sell-level');

      const levelValue = type === 'buy' ? symbol.next_buy_level : symbol.next_sell_level;
      if (levelValue === null || levelValue === undefined) {
        td.textContent = '—';
        return td;
      }

      const levelNum = Number(levelValue);
      const lastNum = Number(symbol.last);
      if (!Number.isFinite(levelNum)) {
        td.textContent = '—';
        return td;
      }

      const priceDiv = document.createElement('div');
      priceDiv.classList.add('level-price');
      priceDiv.textContent = formatNumber(levelNum, 2);
      td.appendChild(priceDiv);

      const deltaText = formatDelta(levelNum, lastNum);
      if (deltaText) {
        const deltaDiv = document.createElement('div');
        deltaDiv.classList.add('level-delta');
        deltaDiv.textContent = deltaText;
        td.appendChild(deltaDiv);
      }

      const indexRaw = type === 'buy' ? symbol.next_buy_index : symbol.next_sell_index;
      const countRaw = type === 'buy' ? symbol.buy_level_count : symbol.sell_level_count;
      const index = typeof indexRaw === 'number' && Number.isFinite(indexRaw) ? indexRaw : null;
      const count = typeof countRaw === 'number' && Number.isFinite(countRaw) ? countRaw : null;

      if (index !== null) {
        const rung = index + 1;
        td.title = count ? `Rung ${rung} / ${count}` : `Rung ${rung}`;
      }

      applyLevelStyling(td, type, index, count);
      return td;
    }

    const sliderState = new Map();
    const sliderTimers = new Map();
    const sliderRanges = {
      buy: { min: 0.25, max: 8, step: 0.05 },
      sell: { min: 0.25, max: 8, step: 0.05 },
    };

    function ensureSliderState(symbol, defaults) {
      let state = sliderState.get(symbol);
      if (!state) {
        state = { ...defaults, dom: {} };
        sliderState.set(symbol, state);
        return state;
      }
      if (!Number.isFinite(state.buy_pct)) {
        state.buy_pct = defaults.buy_pct;
      }
      if (!Number.isFinite(state.sell_pct)) {
        state.sell_pct = defaults.sell_pct;
      }
      return state;
    }

    async function pushOverride(symbol) {
      const state = sliderState.get(symbol);
      if (!state) {
        return;
      }
      const payload = { symbol };
      if (Number.isFinite(state.buy_pct)) {
        payload.buy_pct = Number(state.buy_pct);
      }
      if (Number.isFinite(state.sell_pct)) {
        payload.sell_pct = Number(state.sell_pct);
      }
      if (payload.buy_pct === undefined && payload.sell_pct === undefined) {
        state.pending = false;
        return;
      }

      try {
        const res = await fetch('adjust', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const responseData = await res.json().catch(() => ({}));
        const hasOverride = Boolean(
          responseData && responseData.overrides && Object.keys(responseData.overrides).length
        );
        state.pending = false;
        state.lastSync = Date.now();
        state.overrideActive = hasOverride;
        if (state.dom) {
          for (const dom of Object.values(state.dom)) {
            if (dom && dom.status) {
              dom.status.textContent = hasOverride ? 'Override' : 'Default';
            }
          }
        }
      } catch (err) {
        console.error('override update failed', err);
        state.pending = false;
        state.lastError = Date.now();
        if (state.dom) {
          for (const dom of Object.values(state.dom)) {
            if (dom && dom.status) {
              dom.status.textContent = 'Error';
            }
          }
        }
      }
    }

    function queueOverride(symbol) {
      const state = sliderState.get(symbol);
      if (!state) {
        return;
      }
      state.pending = true;
      if (state.dom) {
        for (const dom of Object.values(state.dom)) {
          if (dom && dom.status) {
            dom.status.textContent = 'Saving…';
          }
        }
      }
      if (sliderTimers.has(symbol)) {
        window.clearTimeout(sliderTimers.get(symbol));
      }
      sliderTimers.set(symbol, window.setTimeout(() => {
        sliderTimers.delete(symbol);
        pushOverride(symbol);
      }, 280));
    }

    function createSliderCell(symbol, type) {
      const td = document.createElement('td');
      td.classList.add('slider-cell');
      const symbolName = typeof symbol.symbol === 'string' ? symbol.symbol : '';
      if (!symbolName || symbolName === '—') {
        td.textContent = '—';
        return td;
      }

      const defaults = {
        buy_pct: toNumber(symbol.input_buy_pct ?? symbol.base_buy_pct ?? symbol.buy_pct, 2),
        sell_pct: toNumber(symbol.input_sell_pct ?? symbol.base_sell_pct ?? symbol.sell_pct, 1.5),
      };
      const state = ensureSliderState(symbolName, defaults);
      if (!state.pending) {
        if (Number.isFinite(defaults.buy_pct)) {
          state.buy_pct = defaults.buy_pct;
        }
        if (Number.isFinite(defaults.sell_pct)) {
          state.sell_pct = defaults.sell_pct;
        }
      }

      const wrapper = document.createElement('div');
      wrapper.classList.add('slider-wrapper');

      const label = document.createElement('div');
      label.classList.add('slider-value', type);

      const slider = document.createElement('input');
      slider.type = 'number';
      slider.inputMode = 'decimal';
      slider.classList.add('slider-input', type);
      const rangeCfg = sliderRanges[type];
      slider.min = String(rangeCfg.min);
      slider.max = String(rangeCfg.max);
      slider.step = String(rangeCfg.step);

      let value = type === 'buy' ? state.buy_pct : state.sell_pct;
      if (!Number.isFinite(value)) {
        value = type === 'buy' ? defaults.buy_pct : defaults.sell_pct;
      }
      value = Math.min(Number(slider.max), Math.max(Number(slider.min), Number(value)));
      if (type === 'buy') {
        state.buy_pct = value;
      } else {
        state.sell_pct = value;
      }

      slider.value = Number(value).toFixed(2);
      label.textContent = `${Number(value).toFixed(2)}%`;
      const applySliderValue = () => {
        if (!slider) {
          return;
        }
        const nextValue = Number(slider.value);
        if (!Number.isFinite(nextValue)) {
          return;
        }
        const clamped = Math.min(Number(slider.max), Math.max(Number(slider.min), nextValue));
        if (clamped !== nextValue) {
          slider.value = clamped.toFixed(2);
        }
        if (type === 'buy') {
          state.buy_pct = clamped;
        } else {
          state.sell_pct = clamped;
        }
        label.textContent = `${clamped.toFixed(2)}%`;
        queueOverride(symbolName);
      };

      slider.addEventListener('input', applySliderValue);
      slider.addEventListener('change', applySliderValue);
      slider.addEventListener('blur', applySliderValue);

      const status = document.createElement('div');
      status.classList.add('slider-status');
      const hasOverride = Boolean(
        (symbol.override_active !== undefined ? symbol.override_active : false)
        || state.overrideActive
      );
      state.overrideActive = hasOverride;
      if (state.pending) {
        status.textContent = 'Saving…';
      } else if (state.lastError && (!state.lastSync || state.lastError > state.lastSync)) {
        status.textContent = 'Error';
      } else if (hasOverride) {
        status.textContent = 'Override';
      } else {
        status.textContent = 'Default';
      }

      wrapper.appendChild(label);
      wrapper.appendChild(slider);
      wrapper.appendChild(status);
      td.appendChild(wrapper);

      state.dom = state.dom || {};
      state.dom[type] = { slider, status, label };
      return td;
    }

    function getLadderLevels(symbol, type) {
      const key = type === 'buy' ? 'buy_ladder_levels' : 'sell_ladder_levels';
      const raw = symbol[key];
      if (!Array.isArray(raw)) {
        return [];
      }
      return raw
        .map((value, index) => {
          if (value === null || value === undefined) {
            return null;
          }
          const num = Number(value);
          if (!Number.isFinite(num)) {
            return null;
          }
          return { index, value: num };
        })
        .filter(Boolean);
    }

    function getNextIndex(symbol, type) {
      const raw = type === 'buy' ? symbol.next_buy_index : symbol.next_sell_index;
      if (typeof raw === 'number' && Number.isFinite(raw)) {
        return Math.max(0, Math.floor(raw));
      }
      return null;
    }

    function createLadderSummary(symbol, type, nextIndex, lastPrice) {
      const box = document.createElement('div');
      box.classList.add('ladder-next', type);

      const label = document.createElement('span');
      label.classList.add('label');
      label.textContent = type === 'buy' ? 'Next Buy' : 'Next Sell';
      box.appendChild(label);

      const value = document.createElement('span');
      value.classList.add('value');

      const levelValueRaw = type === 'buy' ? symbol.next_buy_level : symbol.next_sell_level;
      const levelValue = Number(levelValueRaw);
      const rungIndex = typeof nextIndex === 'number' && Number.isFinite(nextIndex) ? nextIndex + 1 : null;
      const lastNum = Number(lastPrice);

      if (Number.isFinite(levelValue)) {
        const rungPart = rungIndex ? `L${rungIndex} · ` : '';
        const deltaText = Number.isFinite(lastNum) ? formatDelta(levelValue, lastNum) : '';
        value.textContent = `${rungPart}${formatNumber(levelValue, 2)}${deltaText ? ` (${deltaText})` : ''}`;
      } else {
        value.textContent = '—';
      }

      box.appendChild(value);
      return box;
    }

    function detectLadderOverlap(buyLevels, sellLevels) {
      if (!Array.isArray(buyLevels) || !buyLevels.length) {
        return null;
      }
      if (!Array.isArray(sellLevels) || !sellLevels.length) {
        return null;
      }

      let highestBuy = null;
      for (const rung of buyLevels) {
        if (!highestBuy || rung.value > highestBuy.value) {
          highestBuy = rung;
        }
      }

      let lowestSell = null;
      for (const rung of sellLevels) {
        if (!lowestSell || rung.value < lowestSell.value) {
          lowestSell = rung;
        }
      }

      if (highestBuy && lowestSell && highestBuy.value >= lowestSell.value) {
        return { buy: highestBuy, sell: lowestSell };
      }

      return null;
    }

    function createLadderColumn(symbol, type, context = {}) {
      const column = document.createElement('div');
      column.classList.add('ladder-column', type);

      const title = document.createElement('div');
      title.classList.add('ladder-title');
      title.textContent = type === 'buy' ? 'Buy ladder' : 'Sell ladder';
      column.appendChild(title);

      const levels = Array.isArray(context.levels) ? context.levels : getLadderLevels(symbol, type);
      const rungs = document.createElement('div');
      rungs.classList.add('ladder-rungs');
      const nextIndex = typeof context.nextIndex === 'number' && Number.isFinite(context.nextIndex)
        ? Math.max(0, Math.floor(context.nextIndex))
        : getNextIndex(symbol, type);
      const lastPrice = typeof context.lastPrice === 'number' && Number.isFinite(context.lastPrice)
        ? context.lastPrice
        : Number(symbol.last);

      if (!levels.length) {
        const placeholder = document.createElement('div');
        placeholder.classList.add('ladder-empty');
        placeholder.textContent = 'No levels';
        rungs.appendChild(placeholder);
        column.appendChild(rungs);
        return column;
      }

      for (const { index, value } of levels) {
        const rung = document.createElement('div');
        rung.classList.add('ladder-rung', type);
        if (nextIndex !== null && index === nextIndex) {
          rung.classList.add('active');
        }

        const indexSpan = document.createElement('span');
        indexSpan.classList.add('rung-index');
        indexSpan.textContent = `L${index + 1}`;
        rung.appendChild(indexSpan);

        const priceSpan = document.createElement('span');
        priceSpan.classList.add('rung-price');
        priceSpan.textContent = formatNumber(value, 2);
        rung.appendChild(priceSpan);

        if (Number.isFinite(lastPrice)) {
          const deltaText = formatDelta(value, lastPrice);
          if (deltaText) {
            const deltaSpan = document.createElement('span');
            deltaSpan.classList.add('rung-delta');
            deltaSpan.textContent = deltaText;
            rung.appendChild(deltaSpan);
          }
        }

        rungs.appendChild(rung);
      }

      column.appendChild(rungs);
      return column;
    }

    function createChartCell(symbol) {
      const td = document.createElement('td');
      td.classList.add('chart-cell');
      const wrapper = document.createElement('div');
      wrapper.classList.add('chart-wrapper');
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.classList.add('chart-svg');
      svg.setAttribute('viewBox', `0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`);
      svg.setAttribute('preserveAspectRatio', 'none');
      wrapper.appendChild(svg);
      td.appendChild(wrapper);

      const lastPrice = Number(symbol.last);
      const buyLevels = getLadderLevels(symbol, 'buy');
      const sellLevels = getLadderLevels(symbol, 'sell');
      const nextBuyIndex = getNextIndex(symbol, 'buy');
      const nextSellIndex = getNextIndex(symbol, 'sell');

      const meta = document.createElement('div');
      meta.classList.add('ladder-meta');
      meta.appendChild(createLadderSummary(symbol, 'buy', nextBuyIndex, lastPrice));
      meta.appendChild(createLadderSummary(symbol, 'sell', nextSellIndex, lastPrice));
      td.appendChild(meta);

      const ladders = document.createElement('div');
      ladders.classList.add('ladder-wrapper');
      ladders.appendChild(createLadderColumn(symbol, 'buy', {
        levels: buyLevels,
        nextIndex: nextBuyIndex,
        lastPrice,
      }));
      ladders.appendChild(createLadderColumn(symbol, 'sell', {
        levels: sellLevels,
        nextIndex: nextSellIndex,
        lastPrice,
      }));
      td.appendChild(ladders);

      const overlap = detectLadderOverlap(buyLevels, sellLevels);
      if (overlap) {
        td.classList.add('ladder-overlap');
        const alert = document.createElement('div');
        alert.classList.add('ladder-alert');
        const label = document.createElement('span');
        label.classList.add('label');
        label.textContent = 'Overlap';
        const text = document.createElement('span');
        text.textContent = `Buy L${overlap.buy.index + 1} (${formatNumber(overlap.buy.value, 2)}) ≥ Sell L${overlap.sell.index + 1} (${formatNumber(overlap.sell.value, 2)})`;
        alert.appendChild(label);
        alert.appendChild(text);
        td.appendChild(alert);
      }

      if (symbol.symbol && symbol.symbol !== '—') {
        const state = ensureChartState(symbol.symbol);
        state.svg = svg;
        renderChart(symbol.symbol);
      }

      return td;
    }

    function renderConstants(constants) {
      if (!constantsPanel) {
        return;
      }
      let entries = [];
      if (Array.isArray(constants)) {
        entries = constants
          .map((item) => (item && typeof item === 'object' ? item : null))
          .filter((item) => item && item.label && item.value !== undefined && item.value !== null)
          .map((item) => ({ label: item.label, value: item.value }));
      } else if (constants && typeof constants === 'object') {
        entries = Object.entries(constants)
          .filter(([, value]) => value !== undefined && value !== null)
          .map(([label, value]) => ({ label, value }));
      }

      if (!entries.length) {
        constantsPanel.classList.add('hidden');
        constantsPanel.innerHTML = '';
        return;
      }

      constantsPanel.classList.remove('hidden');
      constantsPanel.innerHTML = '';
      for (const entry of entries) {
        const chip = document.createElement('div');
        chip.classList.add('constant-chip');
        const labelSpan = document.createElement('span');
        labelSpan.classList.add('label');
        labelSpan.textContent = entry.label;
        const valueSpan = document.createElement('span');
        valueSpan.classList.add('value');
        valueSpan.textContent = typeof entry.value === 'number' && Number.isFinite(entry.value)
          ? formatNumber(entry.value, entry.value >= 10 ? 0 : 2)
          : String(entry.value);
        chip.appendChild(labelSpan);
        chip.appendChild(valueSpan);
        constantsPanel.appendChild(chip);
      }
    }

    function buildRow(symbol) {
      const tr = document.createElement('tr');

      const buyReady = Boolean(symbol.buy_ready);
      const sellReady = Boolean(symbol.sell_ready);
      const layersGapValue = Number(symbol.buy_layers_gap);
      const hasLayerGap = Number.isFinite(layersGapValue) && layersGapValue > 0;
      const lookingToEnter = Object.prototype.hasOwnProperty.call(symbol, 'looking_to_enter')
        ? Boolean(symbol.looking_to_enter)
        : (buyReady || hasLayerGap);
      const lookingToExit = Object.prototype.hasOwnProperty.call(symbol, 'looking_to_exit')
        ? Boolean(symbol.looking_to_exit)
        : sellReady;

      if (lookingToEnter) tr.classList.add('buy-interest');
      if (lookingToExit) tr.classList.add('sell-interest');
      if (buyReady) tr.classList.add('buy-ready-row');
      if (sellReady) tr.classList.add('sell-ready-row');

      const symbolTd = document.createElement('td');
      symbolTd.classList.add('symbol-cell');
      const symbolText = typeof symbol.symbol === 'string' ? symbol.symbol : '—';
      if (sellReady) {
        symbolTd.classList.add('symbol-sell');
      } else if (lookingToEnter) {
        symbolTd.classList.add('symbol-buy');
      }

      if (sellReady || buyReady || lookingToEnter) {
        const dot = document.createElement('span');
        dot.classList.add('signal-dot');
        if (sellReady) {
          dot.classList.add('sell');
        } else if (!buyReady && lookingToEnter) {
          dot.classList.add('scout');
        }
        symbolTd.appendChild(dot);
      }

      const symbolLabel = document.createElement('span');
      symbolLabel.textContent = symbolText;
      symbolTd.appendChild(symbolLabel);
      tr.appendChild(symbolTd);

      tr.appendChild(createNumericCell(symbol.last, 2));
      tr.appendChild(createNumericCell(symbol.reference, 2));
      tr.appendChild(createLevelCell(symbol, 'buy'));
      tr.appendChild(createLevelCell(symbol, 'sell'));
      tr.appendChild(createChartCell(symbol));
      tr.appendChild(createSliderCell(symbol, 'buy'));
      tr.appendChild(createSliderCell(symbol, 'sell'));
      tr.appendChild(createNumericCell(symbol.vwv_z, 2));
      tr.appendChild(createVelocityCell(symbol));

      const layersTd = document.createElement('td');
      layersTd.textContent = formatLayers(symbol.buy_layers_active, symbol.buy_layers_target, symbol.sell_layers_hit);
      layersTd.classList.add('numeric');
      tr.appendChild(layersTd);

      tr.appendChild(createNumericCell(symbol.position, 0));
      tr.appendChild(createNumericCell(symbol.avg_price, 2));
      tr.appendChild(createNumericCell(symbol.clip_usd, 0));
      tr.appendChild(createNumericCell(symbol.unrealized, 2));

      const statusTd = document.createElement('td');
      statusTd.classList.add('status');

      const entryBadge = document.createElement('span');
      entryBadge.classList.add('badge');
      const velocityActive = Boolean(symbol.velocity_active);
      const velocityReady = Boolean(symbol.velocity_ready);

      if (velocityActive) {
        entryBadge.classList.add('entry-true');
        entryBadge.textContent = 'Velocity Triggered';
      } else if (buyReady) {
        entryBadge.classList.add('entry-true');
        entryBadge.textContent = 'Entry Ready';
      } else if (velocityReady) {
        entryBadge.classList.add('entry-false');
        entryBadge.textContent = 'Velocity Primed';
      } else if (lookingToEnter) {
        entryBadge.classList.add('entry-scout');
        entryBadge.textContent = 'Entry Watching';
      } else {
        entryBadge.classList.add('entry-false');
        entryBadge.textContent = 'Entry Cooling';
      }

      if (hasLayerGap && (buyReady || lookingToEnter)) {
        entryBadge.textContent += ` (+${layersGapValue})`;
      }

      statusTd.appendChild(entryBadge);

      if (lookingToEnter && !buyReady) {
        const scoutBadge = document.createElement('span');
        scoutBadge.classList.add('badge', 'entry-scout');
        scoutBadge.textContent = 'Price Ladder';
        statusTd.appendChild(scoutBadge);
      }

      const sellBadge = document.createElement('span');
      sellBadge.classList.add('badge', sellReady ? 'sell-true' : 'sell-false');
      sellBadge.textContent = sellReady ? 'Trim Ready' : 'Trim Waiting';
      statusTd.appendChild(sellBadge);

      tr.appendChild(statusTd);
      return tr;
    }

    function renderSnapshot(snapshot) {
      if (!snapshot || !Array.isArray(snapshot.symbols) || snapshot.symbols.length === 0) {
        updatedLabel.textContent = snapshot && snapshot.updated ? `Updated ${snapshot.updated}` : 'Waiting for snapshot…';
        summaryLabel.textContent = 'No active symbols reported by the bot yet.';
        tableContainer.innerHTML = '<div class="placeholder">No active symbols available yet. Confirm the bot is running in RTH and writing snapshots.</div>';
        renderConstants(snapshot ? snapshot.constants : null);
        document.title = 'Dronebot Entry Dashboard';
        chartState.clear();
        return;
      }

      const updatedText = snapshot.updated ? `Updated ${snapshot.updated}` : 'Snapshot received';
      updatedLabel.textContent = updatedText;
      document.title = `${updatedText} · Dronebot Entry Dashboard`;
      renderConstants(snapshot.constants);

      const fragment = template.content.cloneNode(true);
      const tbody = fragment.querySelector('tbody');

      const rows = snapshot.symbols
        .filter((symbol) => symbol && typeof symbol === 'object')
        .map((symbol) => ({
          ...symbol,
          symbol: typeof symbol.symbol === 'string' ? symbol.symbol : '—',
        }));

      rows.sort((a, b) => a.symbol.localeCompare(b.symbol));
      for (const symbol of rows) {
        recordChartPoint(symbol);
      }
      for (const symbol of rows) {
        tbody.appendChild(buildRow(symbol));
      }

      const stats = rows.reduce((acc, symbol) => {
        acc.total += 1;
        if (symbol.buy_ready) acc.entryReady += 1;
        if (symbol.sell_ready) acc.trimReady += 1;
        if (symbol.velocity_active) acc.velocityActive += 1;
        else if (symbol.velocity_ready) acc.velocityPrimed += 1;
        if (symbol.looking_to_enter) acc.buyWatching += 1;
        return acc;
      }, { total: 0, entryReady: 0, trimReady: 0, velocityActive: 0, velocityPrimed: 0, buyWatching: 0 });

      const watchingOnly = Math.max(0, stats.buyWatching - stats.entryReady);
      const watchingText = watchingOnly > 0 ? ` (+${watchingOnly} watching)` : '';
      summaryLabel.textContent = `${stats.total} symbol${stats.total === 1 ? '' : 's'} · ${stats.entryReady} entry-ready${watchingText} · ${stats.trimReady} trim-ready · ${stats.velocityActive} velocity-active (${stats.velocityPrimed} primed)`;

      tableContainer.innerHTML = '';
      tableContainer.appendChild(fragment);

      const activeSymbols = new Set(
        rows
          .map((item) => (typeof item.symbol === 'string' && item.symbol !== '—' ? item.symbol : null))
          .filter(Boolean),
      );
      for (const key of Array.from(sliderState.keys())) {
        if (!activeSymbols.has(key)) {
          sliderState.delete(key);
        }
      }
      for (const key of Array.from(sliderTimers.keys())) {
        if (!activeSymbols.has(key)) {
          window.clearTimeout(sliderTimers.get(key));
          sliderTimers.delete(key);
        }
      }
      for (const key of Array.from(chartState.keys())) {
        if (!activeSymbols.has(key)) {
          chartState.delete(key);
        }
      }
    }

    async function pollSnapshot() {
      try {
        const res = await fetch('snapshot.json', { cache: 'no-store' });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        renderSnapshot(data);
      } catch (err) {
        const message = err && err.message ? err.message : 'Unknown error';
        summaryLabel.textContent = 'Snapshot fetch failed.';
        tableContainer.innerHTML = '<div class="placeholder">Unable to load the latest snapshot. The server will keep retrying automatically.</div>';
        updatedLabel.textContent = `Snapshot unavailable (${message}). Retrying…`;
        renderConstants(null);
        console.error('snapshot fetch error', err);
      } finally {
        window.setTimeout(pollSnapshot, 900);
      }
    }

    pollSnapshot();
  </script>
</body>
</html>
"""


def load_snapshot(path: Path) -> dict:
    global _LAST_SNAPSHOT_NOTICE
    try:
        with path.open('r', encoding='utf-8') as f:
            payload = json.load(f)
    except FileNotFoundError:
        notice = ('missing', str(path))
        if notice != _LAST_SNAPSHOT_NOTICE:
            print(f'Waiting for snapshot file at {path}…')
            _LAST_SNAPSHOT_NOTICE = notice
        return {'updated': None, 'symbols': []}
    except json.JSONDecodeError as exc:
        notice = ('decode', str(path))
        if notice != _LAST_SNAPSHOT_NOTICE:
            print(f'Snapshot file {path} is not valid JSON yet ({exc}). Serving placeholder…')
            _LAST_SNAPSHOT_NOTICE = notice
        return {'updated': None, 'symbols': []}
    else:
        if _LAST_SNAPSHOT_NOTICE != (None, None):
            _LAST_SNAPSHOT_NOTICE = (None, None)
            print(f'Snapshot at {path} loaded successfully.')
        return payload


class DashboardHandler(BaseHTTPRequestHandler):
    snapshot_path: Path = _default_snapshot_path()
    overrides_path: Path = _default_overrides_path()

    def _send_response(self, status: int, content: bytes, content_type: str = 'text/html; charset=utf-8') -> None:
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802 (matching BaseHTTPRequestHandler)
        if self.path in ('/', '/index.html'):
            self._send_response(200, DASHBOARD_HTML.encode('utf-8'))
            return
        if self.path == '/snapshot.json':
            payload = load_snapshot(self.snapshot_path)
            body = json.dumps(payload).encode('utf-8')
            self._send_response(200, body, 'application/json; charset=utf-8')
            return
        if self.path == '/healthz':
            self._send_response(200, b'OK', 'text/plain; charset=utf-8')
            return

        self.send_error(404, 'Not Found')

    def do_POST(self) -> None:  # noqa: N802
        if self.path == '/adjust':
            length = int(self.headers.get('Content-Length', '0') or 0)
            try:
                payload = self.rfile.read(length).decode('utf-8') if length > 0 else ''
            except Exception:
                self.send_error(400, 'Unable to read request body')
                return

            try:
                data: Dict[str, Any] = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                self.send_error(400, 'Invalid JSON payload')
                return

            symbol_raw = data.get('symbol')
            if not isinstance(symbol_raw, str) or not symbol_raw.strip():
                self.send_error(400, 'Symbol is required')
                return
            symbol = symbol_raw.strip().upper()

            buy_val = data.get('buy_pct')
            sell_val = data.get('sell_pct')
            buy_pct = None
            sell_pct = None
            try:
                if buy_val is not None:
                    buy_pct = max(0.05, float(buy_val))
            except (TypeError, ValueError):
                self.send_error(400, 'buy_pct must be numeric')
                return
            try:
                if sell_val is not None:
                    sell_pct = max(0.05, float(sell_val))
            except (TypeError, ValueError):
                self.send_error(400, 'sell_pct must be numeric')
                return

            try:
                overrides = update_symbol_override(symbol, buy_pct, sell_pct, self.overrides_path)
            except Exception as exc:
                self.send_error(500, f'Unable to persist override: {exc}')
                return

            body = json.dumps({'symbol': symbol, 'overrides': overrides}).encode('utf-8')
            self._send_response(200, body, 'application/json; charset=utf-8')
            return

        self.send_error(404, 'Not Found')

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - signature from base class
        # Silence default logging to keep terminal clean.
        return


def main() -> None:
    default_snapshot = _default_snapshot_path()
    default_overrides = _default_overrides_path()
    parser = argparse.ArgumentParser(description='Serve a color dashboard for Dronebot entry conditions.')
    parser.add_argument('--host', default='127.0.0.1', help='Bind address (default: 127.0.0.1).')
    parser.add_argument('--port', type=int, default=8765, help='Port to serve on (default: 8765).')
    parser.add_argument('--snapshot', default=str(default_snapshot), help='Path to the snapshot JSON written by dronebot.')
    parser.add_argument('--overrides', default=str(default_overrides), help='Path to the dashboard override JSON file (default: alongside snapshot).')
    args = parser.parse_args()

    DashboardHandler.snapshot_path = _format_snapshot_path(args.snapshot)
    DashboardHandler.overrides_path = _format_snapshot_path(args.overrides)
    global DASHBOARD_OVERRIDES_PATH
    DASHBOARD_OVERRIDES_PATH = DashboardHandler.overrides_path
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    server.daemon_threads = True
    print(
        "Serving dashboard on http://{host}:{port} (snapshot: {snap}, overrides: {over})".format(
            host=args.host,
            port=args.port,
            snap=DashboardHandler.snapshot_path,
            over=DashboardHandler.overrides_path,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopping dashboard server…')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
