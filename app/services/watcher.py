import asyncio
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone, timedelta
from loguru import logger
from typing import Dict, Any, List, Optional

from app.db.session import AsyncSessionLocal
from app.db.crud import get_active_watchlist, get_last_trigger_event, log_trigger_event
from app.services.analyst_agent import analyst_graph

background_tasks = set()

def handle_task_result(task: asyncio.Task):
    """Callback to handle cleanup and unhandled errors in background tasks."""
    background_tasks.discard(task)
    if not task.cancelled():
        exc = task.exception()
        if exc:
            try:
                raise exc
            except Exception:
                logger.exception("Unhandled exception in background agent task")

class WatcherEngine:
    """
    Engine for monitoring stock prices and triggering alerts.
    Now includes Technical Analysis (SMA/RSI) and "Strong Dip" triggers.
    """

    @staticmethod
    def calculate_indicators(df: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate 20-day SMA and 14-day RSI.
        """
        if len(df) < 14:
            return {"rsi": 50.0, "sma20": df["Close"].mean() if not df.empty else 0.0}

        # 1. Calculate 20-day SMA
        sma20 = df["Close"].rolling(window=20).mean().iloc[-1]
        if pd.isna(sma20):
            sma20 = df["Close"].mean()

        # 2. Calculate 14-day RSI
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        if pd.isna(current_rsi):
            current_rsi = 50.0

        return {
            "rsi": round(float(current_rsi), 2),
            "sma20": round(float(sma20), 2)
        }

    async def fetch_ticker_data(self, ticker_symbol: str) -> Dict[str, Any]:
        """
        Fetch current price and 30-day history for technical indicators.
        """
        def _get_data():
            ticker = yf.Ticker(ticker_symbol)
            # Fetch 1 month of history for SMA/RSI calculation
            history = ticker.history(period="1mo")
            
            if history.empty:
                return {"success": False}
                
            last_price = history["Close"].iloc[-1]
            prev_close = history["Close"].iloc[-2] if len(history) > 1 else last_price
            
            indicators = self.calculate_indicators(history)
            
            return {
                "last_price": last_price,
                "previous_close": prev_close,
                "rsi": indicators["rsi"],
                "sma20": indicators["sma20"],
                "success": True
            }

        try:
            data = await asyncio.to_thread(_get_data)
            return data
        except Exception as e:
            logger.error(f"Error fetching data for {ticker_symbol}: {e}")
            return {"success": False}

    async def run_cycle(self):
        """
        Runs a single cycle of the watcher engine with technical analysis triggers.
        """
        logger.info("Watcher cycle started.")
        tasks_to_trigger = []
        
        async with AsyncSessionLocal() as db:
            try:
                active_items = await get_active_watchlist(db)
            except Exception as e:
                logger.error(f"Failed to fetch watchlist from database: {e}")
                return
            
            if not active_items:
                logger.info("No active stocks in watchlist.")
                return

            for item in active_items:
                try:
                    # 1. Fetch latest data + indicators
                    data = await self.fetch_ticker_data(item.ticker)
                    if not data.get("success"):
                        continue

                    current_price = data["last_price"]
                    prev_close = data["previous_close"]
                    rsi = data["rsi"]
                    sma20 = data["sma20"]

                    # 2. Check Triggers
                    # A) Target Price Hit
                    price_hit = current_price <= item.target_price
                    # B) "Strong Dip" (RSI < 30 and Price < 95% of SMA20)
                    strong_dip_hit = (rsi < 30) and (current_price < (sma20 * 0.95))
                    
                    if price_hit or strong_dip_hit:
                        reason = "Target Hit" if price_hit else f"Strong Dip (RSI:{rsi})"
                        logger.warning(f"THRESHOLD HIT | {item.ticker} | Price: {current_price:.2f} | Reason: {reason}")

                        # 3. Cooldown Check
                        last_event = await get_last_trigger_event(db, item.id)
                        if last_event:
                            now = datetime.now(timezone.utc)
                            last_event_ts = last_event.timestamp
                            if last_event_ts.tzinfo is None:
                                last_event_ts = last_event_ts.replace(tzinfo=timezone.utc)
                            
                            diff = now - last_event_ts
                            if diff < timedelta(minutes=60):
                                logger.info(f"Cooldown active for {item.ticker}. Skipping log.")
                                continue

                        # 4. Log Event
                        event = await log_trigger_event(db, item.id, current_price)
                        logger.success(f"Log recorded for {item.ticker}")

                        # 5. Collect payload to trigger Analyst Agent outside DB session
                        tasks_to_trigger.append({
                            "ticker": item.ticker,
                            "current_price": current_price,
                            "trigger_event_id": event.id,
                            "telegram_chat_id": item.telegram_chat_id,
                            "rsi": rsi,
                            "sma20": sma20,
                            "messages": []
                        })

                except Exception as e:
                    logger.error(f"Unexpected error processing {item.ticker}: {e}")
                    continue

        # 6. Trigger Agent tasks outside DB session
        for state_payload in tasks_to_trigger:
            task = asyncio.create_task(analyst_graph.ainvoke(state_payload))
            background_tasks.add(task)
            task.add_done_callback(handle_task_result)
            logger.info(f"Analyst Agent triggered for {state_payload['ticker']} with TA context.")

        logger.info("Watcher cycle completed.")

# Global instance
watcher_engine = WatcherEngine()
