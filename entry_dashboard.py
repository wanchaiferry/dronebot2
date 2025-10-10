"""Lightweight HTTP dashboard for monitoring dronebot entry conditions."""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Tuple


_LAST_SNAPSHOT_NOTICE: Tuple[str | None, str | None] = (None, None)


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
      const ratio = Math.min(1, Math.max(0, (index + 1) / count));
      const baseAlpha = 0.12 + 0.32 * ratio;
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
      tr.appendChild(createNumericCell(symbol.vwv_z, 2));
      tr.appendChild(createNumericCell(symbol.velocity_bps, 1));

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
      entryBadge.classList.add('badge', buyReady ? 'entry-true' : 'entry-false');
      if (buyReady) {
        entryBadge.textContent = `Entry Ready${hasLayerGap ? ` (+${layersGapValue})` : ''}`;
      } else if (lookingToEnter) {
        entryBadge.textContent = `Entry Watching${hasLayerGap ? ` (+${layersGapValue})` : ''}`;
      } else {
        entryBadge.textContent = 'Entry Waiting';
      }
      statusTd.appendChild(entryBadge);

      if (lookingToEnter && !buyReady) {
        const scoutBadge = document.createElement('span');
        scoutBadge.classList.add('badge', 'entry-scout');
        scoutBadge.textContent = 'Price Ladder';
        statusTd.appendChild(scoutBadge);
      }

      const velocityBadge = document.createElement('span');
      const velocityActive = Boolean(symbol.velocity_active);
      const velocityReady = Boolean(symbol.velocity_ready);
      velocityBadge.classList.add('badge', (velocityActive || velocityReady) ? 'velocity-true' : 'velocity-false');
      velocityBadge.textContent = velocityActive ? 'Velocity Active' : (velocityReady ? 'Velocity Ready' : 'Velocity Cooldown');
      statusTd.appendChild(velocityBadge);

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
        window.setTimeout(pollSnapshot, 1500);
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

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - signature from base class
        # Silence default logging to keep terminal clean.
        return


def main() -> None:
    default_snapshot = _default_snapshot_path()
    parser = argparse.ArgumentParser(description='Serve a color dashboard for Dronebot entry conditions.')
    parser.add_argument('--host', default='127.0.0.1', help='Bind address (default: 127.0.0.1).')
    parser.add_argument('--port', type=int, default=8765, help='Port to serve on (default: 8765).')
    parser.add_argument('--snapshot', default=str(default_snapshot), help='Path to the snapshot JSON written by dronebot.')
    args = parser.parse_args()

    DashboardHandler.snapshot_path = _format_snapshot_path(args.snapshot)
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    server.daemon_threads = True
    print(f"Serving dashboard on http://{args.host}:{args.port} (snapshot: {DashboardHandler.snapshot_path})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopping dashboard server…')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
