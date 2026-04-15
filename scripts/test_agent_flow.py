import asyncio
import sys
import os
from loguru import logger
from datetime import datetime, timezone

# Add parent directory to path to allow importing app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal
from app.db import crud
from app.services.analyst_agent import analyst_graph
from app.schemas.stock import WatchlistCreate
from sqlalchemy import text

async def run_test():
    logger.info("Starting Full Analyst Agent Flow Test with Technical Analysis Context...")
    
    try:
        async with AsyncSessionLocal() as db:
            # 0. Connection Check
            logger.info("Step 0: Verifying Database Connection...")
            try:
                await db.execute(text("SELECT 1"))
                logger.info("Database connection verified.")
            except Exception as e:
                logger.critical(f"DATABASE CONNECTION FAILED: {e}")
                return

            # 1. Setup - Ensure a test ticker exists
            ticker = "AAPL"
            logger.info(f"Step 1: Preparing test ticker {ticker}")
            item = await crud.get_watchlist_item_by_ticker(db, ticker)
            if not item:
                item = await crud.create_watchlist_item(
                    db, 
                    WatchlistCreate(ticker=ticker, target_price=250.0, drop_trigger=15.0)
                )
                logger.info(f"Created new watchlist item for {ticker}")
            
            # 2. Mock a Trigger Event with Technical context
            logger.info("Step 2: Mocking a TriggerEvent with Technical Data")
            current_price = 190.0
            rsi = 28.5  # Mocking an oversold condition
            sma20 = 210.0 # Mocking a dip below SMA
            
            event = await crud.log_trigger_event(db, item.id, current_price)
            logger.info(f"Log recorded: Event ID {event.id}")

            # 3. Invoke Analyst Agent
            logger.info("Step 3: Invoking Analyst Agent (LangGraph)")
            
            initial_state = {
                "ticker": ticker,
                "current_price": current_price,
                "trigger_event_id": event.id,
                "rsi": rsi,
                "sma20": sma20,
                "messages": []
            }
            
            async for chunk in analyst_graph.astream(initial_state, stream_mode="updates"):
                for node_name, output in chunk.items():
                    logger.info(f"--- Node '{node_name}' Completed ---")
                    if output:
                        for key, value in output.items():
                            if key == "filing_context":
                                logger.info(f"  {key}: {str(value)[:100]}...")
                            elif key != "messages":
                                logger.info(f"  {key}: {value}")
                    else:
                        logger.info("  (Node returned no data)")
                
            # 4. Final Verification
            logger.info("Step 4: Verifying DB Persistence")
            async with AsyncSessionLocal() as verification_db:
                updated_events = await crud.get_trigger_events(verification_db)
                test_event = next((e for e in updated_events if e.id == event.id), None)
                
                if test_event and test_event.recommendation:
                    logger.success("TEST PASSED: Analysis findings saved to database.")
                    logger.info(f"Final Recommendation: {test_event.recommendation}")
                else:
                    logger.error("TEST FAILED: Findings were not saved correctly.")
                
    except Exception as e:
        logger.exception(f"An unexpected error occurred during the test: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except KeyboardInterrupt:
        logger.warning("Test manually interrupted.")
    except Exception as e:
        if "Event loop is closed" not in str(e):
            logger.error(f"Fatal test error: {e}")
        sys.exit(1)
