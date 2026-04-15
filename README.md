# Stock Monitoring Agent

A professional, AI-driven stock monitoring system built with FastAPI, LangGraph, and Google Gemini 2.5 Flash.

## Core Features
- **Watcher Engine**: Background polling of stock prices via `yfinance`.
- **Analyst Agent**: Stateful LangGraph agent that performs financial analysis and valuation.
- **REST API**: Manage your watchlist and view trigger history.
- **Supabase Integration**: Robust persistence layer with connection pooling support.

## Prerequisites
- **Python 3.12+** (Mandatory for modern async patterns and dependency compatibility).
- **Supabase Project** (Postgres DB + Service Role Key).
- **Google AI SDK Key** (for Gemini 2.5 Flash).

## Setup instructions

1. **Clone and Setup environment**:
   ```bash
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and fill in your credentials.
   
   > [!IMPORTANT]
   > For the `DATABASE_URL`, use the **Transaction Mode** connection string (typically port 6543) provided by Supabase.

3. **Initialize Database**:
   Run the SQL provided in the project documentation (or check `app/db/models.py`) in your Supabase SQL Editor.

## Verification
Run the standalone test script to verify your setup:
```bash
python scripts/test_agent_flow.py
```

## Running the App
```bash
uvicorn app.main:app --reload
```
# stock-agent
