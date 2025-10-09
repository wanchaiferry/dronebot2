"""Lightweight HTTP dashboard for monitoring dronebot entry conditions."""
from __future__ import annotations

import argparse
import json
import os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

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
      margin-bottom: 16px;
      font-size: 0.9rem;
      color: #94a3b8;
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
    tbody tr:hover td {
      background-color: rgba(59,130,246,0.12);
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
    .cooldown-true {
      background: linear-gradient(135deg, #fbbf24, #f59e0b);
      color: #451a03;
    }
    .cooldown-false {
      background: rgba(217,119,6,0.25);
      color: #fef3c7;
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
    .status {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .numeric {
      font-variant-numeric: tabular-nums;
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
  <div id=\"table-container\"></div>
  <template id=\"table-template\">
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Last</th>
          <th>Reference</th>
          <th>Average</th>
          <th>VWV Z</th>
          <th>Velocity</th>
          <th>Layers</th>
          <th>Position</th>
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
    const template = document.getElementById('table-template');

    function formatNumber(value, fractionDigits = 2) {
      if (value === null || value === undefined) {
        return '—';
      }
      return Number(value).toFixed(fractionDigits);
    }

    function formatLayers(active, target, sellHit) {
      return `${active}/${target} ↓${sellHit}`;
    }

    function buildRow(symbol) {
      const tr = document.createElement('tr');

      const columns = [
        ['symbol', symbol.symbol],
        ['last', formatNumber(symbol.last, 2)],
        ['reference', formatNumber(symbol.reference, 2)],
        ['avg_price', formatNumber(symbol.avg_price, 2)],
        ['vwv_z', formatNumber(symbol.vwv_z, 2)],
        ['velocity_bps', formatNumber(symbol.velocity_bps, 1)],
        ['layers', formatLayers(symbol.buy_layers_active, symbol.buy_layers_target, symbol.sell_layers_hit)],
        ['position', symbol.position ?? 0],
        ['clip_usd', formatNumber(symbol.clip_usd, 0)],
        ['unrealized', formatNumber(symbol.unrealized, 2)],
      ];

      for (const [, value] of columns) {
        const td = document.createElement('td');
        td.textContent = value;
        td.classList.add('numeric');
        tr.appendChild(td);
      }

      const statusTd = document.createElement('td');
      statusTd.classList.add('status');

      const entryBadge = document.createElement('span');
      entryBadge.classList.add('badge', symbol.buy_ready ? 'entry-true' : 'entry-false');
      entryBadge.textContent = symbol.buy_ready ? 'Entry Ready' : 'Entry Waiting';
      statusTd.appendChild(entryBadge);

      const cooldownBadge = document.createElement('span');
      cooldownBadge.classList.add('badge', symbol.cooldown_ready ? 'cooldown-true' : 'cooldown-false');
      cooldownBadge.textContent = symbol.cooldown_ready ? 'Cooldown Clear' : 'Cooling Down';
      statusTd.appendChild(cooldownBadge);

      const velocityBadge = document.createElement('span');
      velocityBadge.classList.add('badge', symbol.velocity_active || symbol.velocity_ready ? 'velocity-true' : 'velocity-false');
      velocityBadge.textContent = symbol.velocity_active ? 'Velocity Active' : (symbol.velocity_ready ? 'Velocity Ready' : 'Velocity Cooldown');
      statusTd.appendChild(velocityBadge);

      const sellBadge = document.createElement('span');
      sellBadge.classList.add('badge', symbol.sell_ready ? 'sell-true' : 'sell-false');
      sellBadge.textContent = symbol.sell_ready ? 'Trim Ready' : 'Trim Waiting';
      statusTd.appendChild(sellBadge);

      tr.appendChild(statusTd);
      return tr;
    }

    function renderSnapshot(snapshot) {
      if (!snapshot || !Array.isArray(snapshot.symbols) || snapshot.symbols.length === 0) {
        updatedLabel.textContent = snapshot && snapshot.updated ? `Updated ${snapshot.updated}` : 'Waiting for snapshot…';
        tableContainer.innerHTML = '<div class="placeholder">No active symbols available yet. Confirm the bot is running in RTH and writing snapshots.</div>';
        return;
      }

      updatedLabel.textContent = `Updated ${snapshot.updated}`;
      const fragment = template.content.cloneNode(true);
      const tbody = fragment.querySelector('tbody');

      const rows = [...snapshot.symbols];
      rows.sort((a, b) => a.symbol.localeCompare(b.symbol));
      for (const symbol of rows) {
        tbody.appendChild(buildRow(symbol));
      }
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
        updatedLabel.textContent = `Snapshot unavailable (${err.message}). Retrying…`;
      } finally {
        window.setTimeout(pollSnapshot, 1500);
      }
    }

    pollSnapshot();
  </script>
</body>
</html>
"""


def load_snapshot(path: str) -> dict:
    if not os.path.exists(path):
        return {'updated': None, 'symbols': []}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Partial write; serve empty payload to avoid breaking the dashboard.
        return {'updated': None, 'symbols': []}


class DashboardHandler(BaseHTTPRequestHandler):
    snapshot_path: str = 'dashboard_snapshot.json'

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

        self.send_error(404, 'Not Found')

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - signature from base class
        # Silence default logging to keep terminal clean.
        return


def main() -> None:
    parser = argparse.ArgumentParser(description='Serve a color dashboard for Dronebot entry conditions.')
    parser.add_argument('--host', default='127.0.0.1', help='Bind address (default: 127.0.0.1).')
    parser.add_argument('--port', type=int, default=8765, help='Port to serve on (default: 8765).')
    parser.add_argument('--snapshot', default='dashboard_snapshot.json', help='Path to the snapshot JSON written by dronebot.')
    args = parser.parse_args()

    DashboardHandler.snapshot_path = args.snapshot
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Serving dashboard on http://{args.host}:{args.port} (snapshot: {args.snapshot})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopping dashboard server…')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
