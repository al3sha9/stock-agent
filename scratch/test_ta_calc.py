import yfinance as yf
import pandas as pd
import sys
import os

# Add parent directory to path to allow importing app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.watcher import watcher_engine

async def test_indicators():
    ticker = "AAPL"
    print(f"Fetching data for {ticker}...")
    data = await watcher_engine.fetch_ticker_data(ticker)
    
    if data["success"]:
        print(f"Success!")
        print(f"Price: {data['last_price']:.2f}")
        print(f"RSI: {data['rsi']}")
        print(f"SMA20: {data['sma20']}")
    else:
        print("Failed to fetch data.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_indicators())
