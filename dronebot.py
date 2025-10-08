# dronebot.py — LIVE ONLY (3 sliders + blended reference + VWV) with crash-proof loop & reconnect
from __future__ import annotations
import os, csv, math, time, traceback
import datetime as dt
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
from ib_insync import IB, Stock, Contract, LimitOrder, BarData, Ticker

# ---------- Time / Sessions ----------
TZ = dt.timezone(dt.timedelta(hours=-4))  # US/Eastern (simplified)
AM_START = dt.time(9,30); AM_END = dt.time(11,0)
PM_START = dt.time(14,0); PM_END = dt.time(16,0)

# ---------- IB ----------
HOST = os.getenv('IB_HOST', '127.0.0.1')
PORT = int(os.getenv('IB_PORT', '7497'))
CLIENT_ID = int(os.getenv('IB_CID', '21'))

# ---------- Files ----------
FILLS_CSV = 'fills_live.csv'
PNL_CSV   = 'pnl_summary_live.csv'
TARGETS_TXT = 'targets.txt'
ERR_LOG   = 'bot_errors.log'

# ---------- Exec & Risk ----------
SPREAD_LIMIT_RISKY = 180.0  # bps
SPREAD_LIMIT_SAFE  = 80.0
HARD_STOP_PCT = float(os.getenv('HARD_STOP_PCT', '5.0'))
TRAIL_PCT = float(os.getenv('TRAIL_PCT', '2.5'))
MIN_TRIM_UPNL_PCT = 0.3
LOOP_SLEEP_SEC = float(os.getenv('LOOP_SLEEP_SEC', '0.9'))

# ---------- Sizing ----------
CLASS_ALLOC = {'risky': 0.6, 'safe': 0.4}
DEFAULT_EQUITY_CAP = float(os.getenv('LIVE_EQUITY', '150000'))

# --- Ladder & clip tuning ---
BUY_LADDER_MULTS  = [0.5, 1.0, 1.5]   # multipliers on buy% to show L1/L2/L3 below ref
SELL_LADDER_MULTS = [0.5, 1.0, 1.5]   # multipliers on sell% to show U1/U2/U3 above ref

# Dynamic clip controls (per trade $ sizing), still overridable per-symbol via targets.txt clip=...
SHOTS_PER_TICKER   = int(os.getenv('SHOTS_PER_TICKER', '12'))
RISKY_CLIP_MULT    = float(os.getenv('RISKY_CLIP_MULT', '1.15'))
SAFE_CLIP_MULT     = float(os.getenv('SAFE_CLIP_MULT',  '0.85'))
CLIP_PRICE_REF     = float(os.getenv('CLIP_PRICE_REF',  '50'))  # lower-priced names get bigger clip
MIN_CLIP_USD       = float(os.getenv('MIN_CLIP_USD',    '100'))
MAX_CLIP_USD       = float(os.getenv('MAX_CLIP_USD',   '6000'))

# ---------- Utils ----------
def now_eastern() -> dt.datetime:
    return dt.datetime.now(TZ)

def log(msg: str):
    print(f"[{now_eastern().strftime('%H:%M:%S')}] {msg}", flush=True)

def log_error(msg: str, exc: Exception|None=None):
    line = f"[{now_eastern().isoformat(timespec='seconds')}] {msg}"
    try:
        with open(ERR_LOG, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
            if exc:
                traceback.print_exc(file=f)
    except Exception:
        pass
    # also echo to console
    print(line, flush=True)
    if exc:
        traceback.print_exc()

def ensure_csv(path: str, header: List[str]):
    if not os.path.exists(path):
        with open(path, 'w', newline='') as f:
            csv.writer(f).writerow(header)

def write_fill(side: str, sym: str, qty: int, px: float, tag: str, realized_pnl: float=0.0):
    ensure_csv(FILLS_CSV, ['ts','symbol','side','qty','price','tag','realized_pnl'])
    with open(FILLS_CSV,'a',newline='') as f:
        csv.writer(f).writerow([now_eastern().isoformat(timespec='seconds'), sym, side, qty, round(px,4), tag, round(realized_pnl,2)])

def write_pnl_rows(rows: List[List]):
    ensure_csv(PNL_CSV, ['ts','symbol','pos','avg','last','uPnL','rPnL_to_date'])
    with open(PNL_CSV,'a',newline='') as f:
        w=csv.writer(f)
        for r in rows: w.writerow(r)

# ---------- Config / Targets ----------
def read_targets(path=TARGETS_TXT) -> Dict[str, dict]:
    out={}
    if not os.path.exists(path):
        return out
    with open(path,'r') as f:
        for line in f:
            s=line.strip()
            if not s or s.startswith('#'): continue
            if s.lower().startswith('@config'):
                parts=s.split()[1:]
                for p in parts:
                    if '=' in p:
                        k,v=p.split('=',1); k=k.lower()
                        if k in ('risky','safe'):
                            try: CLASS_ALLOC[k]=float(v)
                            except: pass
                        elif k=='equity':
                            try: globals()['DEFAULT_EQUITY_CAP']=float(v)
                            except: pass
                continue
            parts=s.split(); sym=parts[0].upper()
            rec={'sym':sym,'class':'risky','buy':2.0,'sell':1.5,'clip':None}
            for p in parts[1:]:
                if '=' in p:
                    k,v=p.split('=',1)
                    if k=='class': rec['class']=v
                    elif k=='buy':
                        try: rec['buy']=float(v)
                        except: pass
                    elif k=='sell':
                        try: rec['sell']=float(v)
                        except: pass
                    elif k=='clip':
                        try: rec['clip']=float(v)
                        except: pass
            out[sym]=rec
    return out

# ---------- Historical anchors ----------
def ib_end_dt_us_eastern(ymd_dash: str) -> str:
    d = dt.datetime.strptime(ymd_dash, '%Y-%m-%d')
    return d.strftime('%Y%m%d') + ' 23:59:59 US/Eastern'

def fetch_today_minute_bars(ib: IB, sym: str, ymd: str) -> Tuple[Contract, List[BarData]]:
    c = Stock(sym, 'SMART', 'USD')
    ib.qualifyContracts(c)
    end_dt = ib_end_dt_us_eastern(ymd)
    bars = ib.reqHistoricalData(
        c,
        endDateTime=end_dt,
        durationStr='2 D',
        barSizeSetting='1 min',
        whatToShow='TRADES',
        useRTH=False,
        formatDate=1
    )
    day = dt.datetime.strptime(ymd, '%Y-%m-%d').date()
    bars = [b for b in bars if dt.datetime.fromtimestamp(b.date.timestamp(), TZ).date() == day]
    return c, bars

def anchors_from_bars(bars: List[BarData]) -> dict:
    def tt(b: BarData) -> dt.time:
        return dt.datetime.fromtimestamp(b.date.timestamp(), TZ).time()
    pma = [b.close for b in bars if tt(b) < dt.time(9,30) and b.close]
    ib  = [b.close for b in bars if dt.time(9,30) <= tt(b) < dt.time(10,0) and b.close]
    rth = [b.close for b in bars if tt(b) >= dt.time(9,30) and b.close]
    def mid_span(xs: List[float]):
        if not xs: return (None, None)
        s=sorted(xs); m=s[len(s)//2]; span=(max(s)-min(s)) if len(s)>1 else 0.0
        return (m, span)
    pma_mid,_ = mid_span(pma)
    ib_mid,_  = mid_span(ib)
    rth_mid,_ = mid_span(rth)
    return {'pma_mid':pma_mid,'ib_mid':ib_mid,'rth_mid':rth_mid}

def blended_ref(now: dt.datetime, feats: dict, fallback: float) -> float:
    t = now.time()
    pma_mid=feats.get('pma_mid'); ib_mid=feats.get('ib_mid'); rth_mid=feats.get('rth_mid')
    ref = fallback
    if t < dt.time(10,0):
        ref = ib_mid or pma_mid or rth_mid or fallback
    elif t < dt.time(11,0):
        if ib_mid and rth_mid: ref = 0.5*ib_mid + 0.5*rth_mid
        else: ref = ib_mid or rth_mid or fallback
    else:
        ref = rth_mid or ib_mid or pma_mid or fallback
    return ref or fallback

# ---------- VWV live z-score ----------
class VWVState:
    def __init__(self, window:int=120):
        self.window = window
        self.dv = deque(maxlen=window)   # recent dollar-volume increments
        self.last_total_vol = None

    def update(self, last_price: Optional[float], total_volume: Optional[int]) -> float:
        """
        Feed with ticker.last (or close) and ticker.volume (cumulative day volume).
        Returns current z-score of the latest dollar-volume increment.
        """
        if not last_price or total_volume is None:
            return 0.0

        z = 0.0
        if self.last_total_vol is not None and total_volume > self.last_total_vol:
            dvol = total_volume - self.last_total_vol
            dv = float(last_price) * float(max(0, dvol))
            self.dv.append(dv)

            # Compute z using list() since deque doesn't support slicing
            buf = list(self.dv)
            if len(buf) > 1:
                latest = buf[-1]
                prev = buf[:-1]
                n = len(prev)
                mu = sum(prev) / n
                # sample stddev (n-1)
                if n > 1:
                    var = sum((x - mu) ** 2 for x in prev) / (n - 1)
                    sd = math.sqrt(var)
                    if sd > 1e-9:
                        z = (latest - mu) / sd

        self.last_total_vol = total_volume

        # clamp z mildly
        if z > 6: z = 6.0
        if z < -6: z = -6.0
        return z

# Dynamic clip sizing

def dynamic_clip_usd(sym: str, last_price: float, targets: Dict[str, dict]) -> float:
    """Per-trade USD clip sized by class allocation and inversely by price."""
    klass = targets[sym].get('class','risky')
    class_frac = CLASS_ALLOC.get(klass, 0.5)
    class_budget = DEFAULT_EQUITY_CAP * class_frac
    n_class = sum(1 for r in targets.values() if r.get('class','risky')==klass) or 1
    per_ticker_budget = class_budget / n_class
    base_clip = per_ticker_budget / max(1, SHOTS_PER_TICKER)

    risk_mult = RISKY_CLIP_MULT if klass=='risky' else SAFE_CLIP_MULT
    price_weight = max(0.5, min(2.0, CLIP_PRICE_REF / max(1.0, float(last_price))))

    clip = base_clip * risk_mult * price_weight
    clip = max(MIN_CLIP_USD, min(MAX_CLIP_USD, clip))
    return clip

# ---------- Spread & IOC ----------
def spread_bps(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    if bid and ask and bid>0 and ask>0:
        mid=(bid+ask)/2.0
        return (ask-bid)/mid*10000.0
    return None


def sanitize_price(value: Optional[float]) -> Optional[float]:
    """Return a positive float price or None if the value is unusable."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        fval = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(fval) or fval <= 0:
        return None
    return fval

def place_ioc_buy(ib: IB, c: Contract, qty: int, bid: Optional[float], last: Optional[float]) -> Optional[float]:
    if qty<=0: return None
    lmt = (last or bid or 0.01) * 1.002
    o = LimitOrder('BUY', qty, round(lmt, 4), tif='IOC')
    tr = ib.placeOrder(c, o); ib.sleep(0.25)
    fills = [f for f in ib.fills() if f.execution.orderId == tr.order.orderId]
    if fills:
        return sum(f.execution.avgPrice*f.execution.shares for f in fills)/max(1,sum(f.execution.shares for f in fills))
    return None

def place_ioc_sell(ib: IB, c: Contract, qty: int, ask: Optional[float], last: Optional[float]) -> Optional[float]:
    if qty<=0: return None
    lmt = (last or ask or 0.01) * 0.998
    o = LimitOrder('SELL', qty, round(lmt, 4), tif='IOC')
    tr = ib.placeOrder(c, o); ib.sleep(0.25)
    fills = [f for f in ib.fills() if f.execution.orderId == tr.order.orderId]
    if fills:
        return sum(f.execution.avgPrice*f.execution.shares for f in fills)/max(1,sum(f.execution.shares for f in fills))
    return None

# ---------- Core loop wrapped with resilience ----------
# Extra safety features added:
#  - Position sync from IB every loop (real position & avgCost)
#  - Anti-short guard: if broker shows a negative position, buy-to-cover to zero via IOC
#  - Breakeven trim: if price >= avgCost, optionally trim a fraction even if sell anchor not hit
#  - Strict non-negative position enforcement after every update
BREAKEVEN_TRIM_FRACTION = float(os.getenv('BREAKEVEN_TRIM_FRACTION','0.25'))   # 25% trim at breakeven+
BREAKEVEN_MIN_UPNL_BP  = float(os.getenv('BREAKEVEN_MIN_UPNL_BP','5'))         # 5 bps over avg required


def read_broker_positions(ib: IB) -> Dict[str, Tuple[int,float]]:
    """Return {symbol: (pos, avgCost)} from IBKR."""
    res: Dict[str, Tuple[int,float]] = {}
    try:
        for p in ib.positions():
            try:
                sym = p.contract.symbol.upper()
            except Exception:
                continue
            res[sym] = (int(p.position), float(p.avgCost or 0.0))
    except Exception as e:
        log_error(f"read_broker_positions error: {e}")
    return res


def run_live():
    while True:
        ib = IB()
        try:
            # Connect (retry handled by outer while on failure)
            ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=10)
            log("Connected to IB.")

            # If IB disconnects, print & let outer loop restart
            def on_disconnect():
                log_error("IB disconnected")
                try: ib.disconnect()
                except: pass
            ib.disconnectedEvent += on_disconnect

            # Targets
            targets = read_targets()
            if not targets:
                for sym in "RCAT,DPRO,UMAC,AVAV,KTOS,LPTH,ONDS,EH,SPAI".split(','):
                    targets[sym]={'sym':sym,'class':'risky','buy':2.0,'sell':1.5,'clip':None}
                log("No targets.txt found; using defaults.")

            # Contracts & market data
            contracts={}
            for sym in targets:
                c=Stock(sym,'SMART','USD'); ib.qualifyContracts(c); contracts[sym]=c
                ib.reqMktData(c, '', False, False)
                log(f"Streaming {sym}")

            # Seed anchors (best-effort; errors are logged, not fatal)
            today = now_eastern().date().isoformat()
            feats_map: Dict[str,dict] = {}
            for sym in targets:
                try:
                    _, bars = fetch_today_minute_bars(ib, sym, today)
                    feats_map[sym] = anchors_from_bars(bars)
                except Exception as e:
                    log_error(f"{sym} hist seed failed: {e}")

            # Live state
            pos=defaultdict(int); avg=defaultdict(float); rpnls=defaultdict(float); trail_hi=defaultdict(float)
            vwv: Dict[str,VWVState] = {sym: VWVState(window=120) for sym in targets}

            # Main tick loop
            was_in_session: Optional[bool] = None
            while True:
                # If socket dropped, break to outer reconnect
                if not ib.isConnected():
                    raise RuntimeError("Lost IB connection")
                ib.sleep(LOOP_SLEEP_SEC)

                now = now_eastern()
                tnow = now.time()
                in_session = (AM_START <= tnow < AM_END) or (PM_START <= tnow < PM_END)

                if was_in_session is None or in_session != was_in_session:
                    if in_session:
                        log("Inside trading session window; live logic active.")
                    else:
                        log("Outside trading session window; waiting for next window to trade.")
                    was_in_session = in_session

                # --- SYNC LIVE POSITIONS FROM IB ---
                try:
                    broker_pos = read_broker_positions(ib)
                    for sym, (bpos, bavg) in broker_pos.items():
                        # Anti-short guard: buy to cover any negative broker position
                        if bpos < 0:
                            c = contracts.get(sym)
                            if c is not None:
                                t: Ticker = ib.ticker(c)
                                last=t.last or t.close; bid=t.bid
                                qty = abs(int(bpos))
                                if qty > 0:
                                    px = place_ioc_buy(ib, c, qty, bid, last)
                                    if px:
                                        write_fill('BUY', sym, qty, px, 'anti_short_cover', 0.0)
                                        bpos = 0; bavg = 0.0
                        # Sync our local mirrors to broker's long-only state
                        if bpos <= 0:
                            pos[sym] = 0
                            avg[sym] = 0.0
                        else:
                            pos[sym] = max(0, int(bpos))
                            avg[sym] = float(bavg)
                except Exception as e:
                    log_error(f"position sync error: {e}")

                if not in_session:
                    # idle off-session, but keep running
                    continue

                pnl_rows=[]
                for sym, rec in targets.items():
                    try:
                        c = contracts[sym]
                        t: Optional[Ticker] = ib.ticker(c)
                        if t is None:
                            continue

                        last_candidates = [t.last, t.close]
                        try:
                            last_candidates.append(t.marketPrice())
                        except Exception:
                            pass
                        last = None
                        for cand in last_candidates:
                            last = sanitize_price(cand)
                            if last is not None:
                                break
                        if last is None:
                            continue

                        bid = sanitize_price(t.bid)
                        ask = sanitize_price(t.ask)

                        spr = spread_bps(bid, ask)
                        spr_lim = SPREAD_LIMIT_RISKY if rec.get('class','risky')=='risky' else SPREAD_LIMIT_SAFE
                        if spr is not None and spr>spr_lim:
                            continue

                        fallback_raw = (
                            t.open if (AM_START <= tnow <= dt.time(10, 0) and t.open) else (t.close or last)
                        )
                        fallback = sanitize_price(fallback_raw) or last
                        feats = feats_map.get(sym, {})
                        ref = blended_ref(now, feats, fallback)

                        z = vwv[sym].update(last, t.volume)
                        zc = max(-2.0, min(2.0, z))
                        buy_mult  = max(0.25, 1.0 + 0.25*zc)
                        sell_mult = 1.0 - 0.15*zc

                        buy_pct  = max(0.1, float(rec['buy'])) * buy_mult
                        sell_pct = max(0.1, float(rec['sell'])) * sell_mult

                        # Ladder levels for HUD (and we use the middle level for core triggers)
                        buy_levels  = [ref * (1.0 - (buy_pct * m) / 100.0) for m in BUY_LADDER_MULTS]
                        sell_levels = [ref * (1.0 + (sell_pct * m) / 100.0) for m in SELL_LADDER_MULTS]

                        buy_a  = buy_levels[1]  # L2 (middle)
                        sell_a = sell_levels[1]  # U2 (middle)

                        clip_override = rec.get('clip', None)
                        clip_usd = (
                            float(clip_override)
                            if (clip_override is not None and float(clip_override) > 0)
                            else dynamic_clip_usd(sym, last, targets)
                        )

                        # ENTRY (never create short; pos>=0 is enforced by sync)
                        if last <= buy_a:
                            qty = int(max(0, clip_usd // max(0.01, last)))
                            if qty > 0:
                                px = place_ioc_buy(ib, c, qty, bid, last)
                                if px:
                                    write_fill('BUY', sym, qty, px, 'live_buy', 0.0)
                                    newpos = max(0, pos[sym]) + qty
                                    avg[sym] = (
                                        (avg[sym] * pos[sym] + px * qty) / newpos
                                    ) if pos[sym] > 0 else px
                                    pos[sym] = max(0, newpos)
                                    trail_hi[sym] = max(trail_hi[sym], px)

                        # BREAKEVEN TRIM (optional): if price >= avg, trim a fraction
                        if pos[sym]>0 and avg[sym]>0:
                            upnl_bp = (last/avg[sym]-1.0)*10000.0
                            if upnl_bp >= BREAKEVEN_MIN_UPNL_BP and last >= avg[sym]:
                                qty = max(1, int(pos[sym]*BREAKEVEN_TRIM_FRACTION))
                                px = place_ioc_sell(ib, c, qty, ask, last)
                                if px:
                                    rp = (px-avg[sym])*qty
                                    rpnls[sym]+=rp; write_fill('SELL', sym, qty, px, 'breakeven_trim', rp)
                                    pos[sym] = max(0, pos[sym]-qty)
                                    if pos[sym]==0:
                                        avg[sym]=0.0; trail_hi[sym]=0.0

                        # TRIM on anchor
                        if pos[sym]>0 and last >= sell_a:
                            u = (last-avg[sym])/max(1e-9,avg[sym])*100.0 if avg[sym]>0 else 0.0
                            if u >= MIN_TRIM_UPNL_PCT:
                                qty = max(1, int(pos[sym]*0.5))
                                px = place_ioc_sell(ib, c, qty, ask, last)
                                if px:
                                    rp = (px-avg[sym])*qty
                                    rpnls[sym]+=rp; write_fill('SELL', sym, qty, px, 'live_trim', rp)
                                    pos[sym] = max(0, pos[sym]-qty)
                                    if pos[sym]==0:
                                        avg[sym]=0.0; trail_hi[sym]=0.0

                        # HARD STOP
                        if pos[sym]>0 and avg[sym]>0 and last <= avg[sym]*(1 - HARD_STOP_PCT/100.0):
                            qty=pos[sym]
                            px = place_ioc_sell(ib, c, qty, ask, last)
                            if px:
                                rp = (px-avg[sym])*qty
                                rpnls[sym]+=rp; write_fill('SELL', sym, qty, px, 'live_stop', rp)
                                pos[sym]=0; avg[sym]=0.0; trail_hi[sym]=0.0

                        # TRAIL
                        if pos[sym]>0:
                            trail_hi[sym]=max(trail_hi[sym], last)
                            trail_level = trail_hi[sym]*(1 - TRAIL_PCT/100.0)
                            if last <= trail_level and last>0:
                                qty=pos[sym]
                                px = place_ioc_sell(ib, c, qty, ask, last)
                                if px:
                                    rp = (px-avg[sym])*qty
                                    rpnls[sym]+=rp; write_fill('SELL', sym, qty, px, 'live_trail', rp)
                                    pos[sym]=0; avg[sym]=0.0; trail_hi[sym]=0.0

                        # HUD / logging snapshot
                        u = (last - avg[sym]) * pos[sym] if pos[sym] > 0 and avg[sym] > 0 else 0.0
                        bl = ','.join(f"{x:.2f}" for x in buy_levels)
                        sl = ','.join(f"{x:.2f}" for x in sell_levels)
                        pnl_rows.append([
                            now.isoformat(timespec='seconds'),
                            sym,
                            pos[sym],
                            round(avg[sym], 4),
                            round(last, 4),
                            round(u, 2),
                            round(rpnls[sym], 2),
                        ])
                        log(
                            f"{sym} last={last:.2f} ref={ref:.2f} z={z:.2f} BL=[{bl}] UL=[{sl}] "
                            f"pos={pos[sym]} avg={avg[sym]:.2f} clip=${clip_usd:.0f} uPnL={u:.2f}"
                        )

                    except Exception as e:
                        log_error(f"loop symbol {sym} error: {e}", e)

                if pnl_rows:
                    write_pnl_rows(pnl_rows)

        except Exception as e:
            log_error("top-level error", e)
        finally:
            try: ib.disconnect()
            except: pass
            time.sleep(3)
            log("Reconnecting IB…")

# ---------- Entry ----------
if __name__ == '__main__':
    try:
        run_live()
    except Exception as e:
        log_error("fatal error at entry", e)
        raise
