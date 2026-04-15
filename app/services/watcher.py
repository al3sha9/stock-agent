import asyncio
import yfinance as yf
from datetime import datetime, timezone, timedelta
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List

from app.db.session import AsyncSessionLocal
from app.db.crud import get_active_watchlist, get_last_trigger_event, log_trigger_event
from app.services.analyst_agent import analyst_graph

class WatcherEngine:
    """
    Engine for monitoring stock prices and triggering alerts.
    """

    @staticmethod
    async def fetch_ticker_data(ticker_symbol: str) -> Dict[str, Any]:
        """
        Fetch current price and previous close from yfinance.
        Runs in a separate thread to avoid blocking the event loop.
        """
        def _get_data():
            ticker = yf.Ticker(ticker_symbol)
            # Fetching 'fast_info' for efficient attribute access
            info = ticker.fast_info
            return {
                "last_price": info.last_price,
                "previous_close": info.previous_close,
            }

        try:
            # Wrap all yfinance property access in a thread to be 100% safe
            data = await asyncio.to_thread(_get_data)
            return {
                **data,
                "success": True
            }
        except Exception as e:
            logger.error(f"Error fetching data for {ticker_symbol}: {e}")
            return {"success": False}

    async def run_cycle(self):
        """
        Runs a single cycle of the watcher engine.
        """
        logger.info("Watcher cycle started.")
        
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
                    # 1. Fetch latest data
                    data = await self.fetch_ticker_data(item.ticker)
                    if not data["success"]:
                        continue

                    current_price = data["last_price"]
                    prev_close = data["previous_close"]
                    drop_from_close = prev_close - current_price

                    # 2. Check Triggers
                    price_hit = current_price <= item.target_price
                    drop_hit = drop_from_close >= item.drop_trigger

                    if price_hit or drop_hit:
                        reason = "Target Hit" if price_hit else f"Drop Hit ({drop_from_close:.2f})"
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

                        # 5. Trigger Analyst Agent (LangGraph)
                        asyncio.create_task(analyst_graph.ainvoke({
                            "ticker": item.ticker,
                            "current_price": current_price,
                            "trigger_event_id": event.id,
                            "messages": []
                        }))
                        logger.info(f"Analyst Agent triggered for {item.ticker}")

                except Exception as e:
                    logger.error(f"Unexpected error processing {item.ticker}: {e}")
                    continue

        logger.info("Watcher cycle completed.")

# Global instance
watcher_engine = WatcherEngine()
