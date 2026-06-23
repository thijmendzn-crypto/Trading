"""
FastAPI backend — serves the dashboard and exposes REST endpoints.
Also runs the signal scanner as a background task.
"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.config import settings
from src.signals.generator import SignalGenerator
from src.intelligence.evaluator import SignalResult
from src.journal.journal import TradeJournal
from src.notifications.telegram import TelegramNotifier
from src.data.providers.binance import BinanceProvider
from src.analysis.market_analyzer import MarketAnalyzer

# In-memory signal store (persists during process lifetime)
_signals: list[dict] = []
_scanner_running = False
_last_scan: Optional[str] = None

journal = TradeJournal(data_dir="./data")
notifier = TelegramNotifier()
provider = BinanceProvider()
analyzer = MarketAnalyzer()


def on_signal(signal: SignalResult):
    """Callback: store approved signals and send Telegram notification."""
    _signals.insert(0, signal.to_dict())
    # Keep last 100 signals in memory
    if len(_signals) > 100:
        _signals.pop()
    asyncio.create_task(notifier.send_signal(signal))


async def scanner_loop():
    """Background scanner — runs every 60 minutes."""
    global _last_scan, _scanner_running
    _scanner_running = True

    generator = SignalGenerator(
        knowledge_dir=str(Path(__file__).parents[3] / "knowledge"),
        on_signal=on_signal,
    )

    while True:
        try:
            logger.info("Running signal scan...")
            await generator.run_scan()
            _last_scan = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            logger.error(f"Scanner error: {e}")
        await asyncio.sleep(60 * 60)  # 60 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background scanner on startup."""
    asyncio.create_task(scanner_loop())
    yield
    await provider.close()


app = FastAPI(title="Trading Intelligence Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (dashboard HTML/JS/CSS)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ─── API Routes ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the dashboard."""
    html_file = Path(__file__).parent.parent / "static" / "index.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text())
    return HTMLResponse(content="<h1>Trading Platform API</h1><p>Dashboard loading...</p>")


@app.get("/api/status")
async def status():
    return {
        "status": "running",
        "scanner_active": _scanner_running,
        "last_scan": _last_scan,
        "symbols": settings.symbol_list,
        "total_signals": len(_signals),
        "environment": settings.environment,
    }


@app.get("/api/signals")
async def get_signals(approved_only: bool = True, limit: int = 20):
    """Return recent signals."""
    filtered = _signals
    if approved_only:
        filtered = [s for s in _signals if s.get("approved")]
    return filtered[:limit]


@app.get("/api/market")
async def get_market():
    """Return current market analysis for all symbols."""
    results = []
    for symbol in settings.symbol_list:
        try:
            data = await provider.fetch_multi_timeframe(symbol, ["1h", "4h"])
            snapshot = analyzer.analyze(symbol, data["1h"], data["4h"])
            snapshot.timeframe = "1h"
            results.append(snapshot.to_dict())
        except Exception as e:
            results.append({"symbol": symbol, "error": str(e)})
    return results


@app.get("/api/market/{symbol}")
async def get_market_symbol(symbol: str):
    """Return current market analysis for a single symbol."""
    symbol = symbol.upper()
    if symbol not in [s.upper() for s in settings.symbol_list]:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not configured")
    try:
        data = await provider.fetch_multi_timeframe(symbol, ["1h", "4h"])
        snapshot = analyzer.analyze(symbol, data["1h"], data["4h"])
        snapshot.timeframe = "1h"
        return snapshot.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/journal/stats")
async def get_journal_stats():
    return journal.get_statistics()


@app.get("/api/journal/trades")
async def get_trades(limit: int = 50):
    trades = journal.get_all_trades()
    return sorted(trades, key=lambda t: t.get("entry_time", ""), reverse=True)[:limit]


@app.post("/api/scan")
async def trigger_scan():
    """Manually trigger a signal scan."""
    generator = SignalGenerator(
        knowledge_dir=str(Path(__file__).parents[3] / "knowledge"),
        on_signal=on_signal,
    )
    approved = await generator.run_scan()
    return {
        "scanned": settings.symbol_list,
        "approved_signals": len(approved),
        "signals": [s.to_dict() for s in approved],
    }
