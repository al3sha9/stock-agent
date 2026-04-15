# 📈 Stock Monitoring Agent

> **An autonomous, AI-driven financial research system** that monitors stock prices, identifies technical buy signals, conducts SEC filing analysis, performs DCF valuation, and delivers professional investment reports — directly to your Telegram.

---

## 🧠 What Is This?

The **Stock Monitoring Agent** is a self-contained backend service that acts as your personal, always-on equity analyst. You configure a stock watchlist, set your target prices, and the system handles everything else — from real-time price monitoring to generating AI-powered investment reports and delivering them directly to your phone.

It is **not a trading bot** — it does not execute trades. Instead, it is a **research and alerting system** that combines quantitative financial data, technical analysis, and qualitative SEC filing context to provide structured investment recommendations.

---

## 🏗️ How It Works — The Full Pipeline

The system operates as a continuous loop with five distinct phases:

```
Price Monitoring → Trigger Detection → AI Research Agent → Valuation → Report & Notify
```

### Phase 1: Price Monitoring (WatcherEngine)
Every **5 minutes**, the `WatcherEngine` polls real-time price data for every stock on your watchlist using `yfinance`. For each ticker, it fetches:
- The current market price
- 30 days of price history to calculate technical indicators

### Phase 2: Technical Analysis & Trigger Detection
Before deciding whether to launch a full AI research run, the Watcher calculates two technical indicators on the fly:

| Indicator | Window | Purpose |
|---|---|---|
| **Simple Moving Average (SMA)** | 20-day | Identifies the short-term price trend |
| **Relative Strength Index (RSI)** | 14-day | Identifies overbought/oversold momentum |

A trigger fires under **two conditions**:
1. **Target Price Hit**: The current price drops to or below your configured target.
2. **"Strong Dip" Signal**: RSI drops below **30** (oversold) AND the price is more than **5% below the SMA20**. This detects potential buying opportunities even if the target price hasn't been reached.

A **60-minute cooldown** prevents duplicate alerts for the same ticker.

### Phase 3: AI Research (LangGraph Analyst Agent)
When a trigger fires, a stateful **LangGraph** pipeline is launched asynchronously. It runs through five nodes in sequence:

```
fetch_financials → calculate_dcf → generate_report → save_results → notify_user
```

#### `fetch_financials`
- Pulls Income Statement, Cash Flow, and Shares Outstanding from `yfinance`
- Fetches the most recent **10-K or 10-Q SEC filing** to extract the *Management's Discussion and Analysis (MD&A)* section
- SEC data uses **Financial Modeling Prep (FMP)** as the primary source, with an automatic fallback to the official **SEC EDGAR API** if FMP returns a 403 error
- All SEC.gov requests include a mandatory `User-Agent` header per SEC fair access policy

#### `calculate_dcf`
- Calculates the **per-share intrinsic value** using a simplified DCF:
  ```
  Intrinsic Value = (Free Cash Flow × 15) / Shares Outstanding
  ```
- Aborts with `DATA_INCOMPLETE` if shares outstanding or FCF is zero/missing

#### `generate_report`
- Invokes **Google Gemini 2.5 Flash** with a structured prompt containing:
  - Current price vs. intrinsic value
  - Shares outstanding (shown as `14.68B`, `250M`, etc.)
  - Technical indicators (RSI, SMA20) for momentum context
  - Up to 8,000 characters of SEC MD&A text for qualitative context
- Gemini is instructed to produce a 4-sentence recommendation (BUY / HOLD / SELL)

#### `save_results`
- Persists the `intrinsic_value` and `recommendation` to the Supabase database against the trigger event record

#### `notify_user`
- Sends the formatted investment report to your Telegram chat

### Phase 4: Telegram Delivery

Every report is sent as a clean, scannable Telegram message:

```
🎯 Ticker: $AAPL

💰 Current Price: $190.00
💎 Intrinsic Value: $100.91
📢 Recommendation: SELL (Overvalued)

📝 Analysis:
Apple trades at a significant premium to its intrinsic value of $100.91 based
on 14.68B shares. The RSI of 28.5 confirms a short-term oversold condition,
but the fundamental overvaluation remains the dominant factor...
```

---

## 🤖 Interactive Telegram Bot Commands

The Telegram bot isn't just for receiving reports — it's a full control interface. You can manage your watchlist and trigger on-demand analysis without touching the server.

| Command | Description |
|---|---|
| `/start` | Display the command menu |
| `/add AAPL 150` | Add AAPL to watchlist with a $150 target price |
| `/remove AAPL` | Remove AAPL from watchlist |
| `/list` | Show all watched stocks and their targets |
| `/status AAPL` | Trigger an immediate AI analysis for AAPL right now |

> **Security**: All commands are restricted to your configured `TELEGRAM_CHAT_ID`. Any other user who messages the bot will be silently ignored.

The bot uses **polling mode**, running inside the FastAPI application's async event loop alongside the price watcher and REST API — no separate process needed.

---

## 🔧 Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Web Framework** | FastAPI | REST API + async lifecycle management |
| **AI Agent** | LangGraph | Stateful multi-step research pipeline |
| **LLM** | Google Gemini 2.5 Flash | Report generation & analysis |
| **Database** | Supabase (PostgreSQL) | Persistent watchlist & event storage |
| **ORM** | SQLAlchemy 2.0 (Async) | Async database access |
| **DB Driver** | asyncpg | High-performance async PostgreSQL driver |
| **Scheduler** | APScheduler | Background 5-minute price monitoring loop |
| **Market Data** | yfinance | Real-time prices, financials, share data |
| **SEC Data** | FMP API + SEC EDGAR | 10-K/10-Q filing retrieval |
| **Telegram** | python-telegram-bot | Interactive bot + investment reports |
| **Proxy** | Cloudflare Workers (optional) | Route Telegram API through reverse proxy |
| **Logging** | Loguru | Structured, colored log output |

---

## 🗄️ Data Models

### `Watchlist`
| Field | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `ticker` | String | Stock symbol (e.g., `AAPL`) |
| `target_price` | Float | Price level that triggers analysis |
| `drop_trigger` | Float | Drop-from-close threshold |
| `is_active` | Boolean | Whether monitoring is active |

### `TriggerEvent`
| Field | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `watchlist_id` | UUID | Foreign key to Watchlist |
| `price_at_trigger` | Float | Market price when trigger fired |
| `intrinsic_value` | Float | DCF valuation result (per share) |
| `recommendation` | Text | Gemini's full analysis output |
| `timestamp` | DateTime | When the trigger occurred |

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and fill in all required fields:

```env
# Supabase
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-supabase-anon-key
DATABASE_URL=postgresql://postgres:password@your-project.pooler.supabase.com:6543/postgres

# API
PROJECT_NAME="Stock Monitoring Agent"
API_V1_STR="/api/v1"

# AI
GOOGLE_API_KEY=your-google-ai-studio-key

# SEC Data
FMP_API_KEY=your-fmp-api-key

# Telegram
TELEGRAM_BOT_TOKEN=your-bot-token-from-botfather
TELEGRAM_CHAT_ID=your-numeric-telegram-id

# Optional: Cloudflare reverse proxy (leave empty to use default Telegram API)
TELEGRAM_BASE_URL=https://your-worker.workers.dev/bot
```

> [!IMPORTANT]
> Use the **Supavisor Transaction Mode** connection string (port `6543`), not the direct connection. The app disables prepared statement caching for full compatibility with Supabase's connection pooler.

> [!TIP]
> To get your `TELEGRAM_CHAT_ID`, message [@userinfobot](https://t.me/userinfobot) on Telegram.

---

## 🚀 Setup & Running

### Prerequisites
- Python 3.12+
- A [Supabase](https://supabase.com) project
- A [Google AI Studio](https://aistudio.google.com) API key
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- (Optional) An [FMP](https://financialmodelingprep.com/) API key for SEC filing data

### 1. Clone & Install
```bash
git clone https://github.com/al3sha9/stock-agent.git
cd stock-agent
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Initialize Database
Run the table creation SQL in your Supabase SQL Editor. The schema is defined in `app/db/models.py`.

### 4. Run the App
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO | Telegram interactive bot polling started.
INFO | Background scheduler started.
INFO | Watcher job scheduled (every 5 minutes).
INFO | Application startup complete.
```

### 5. Verify the Pipeline
Run the end-to-end test script to confirm your database, AI, and Telegram connections are all working:
```bash
python scripts/test_agent_flow.py
```

---

## 📡 REST API

The API is available at `http://localhost:8000/api/v1`. Interactive docs are at `http://localhost:8000/docs`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/watchlist` | Get all watchlist items |
| `POST` | `/watchlist` | Add a new stock to the watchlist |
| `DELETE` | `/watchlist/{ticker}` | Remove a stock from the watchlist |
| `GET` | `/events` | Get all trigger event history |

---

## 📁 Project Structure

```
stocks/
├── app/
│   ├── api/              # FastAPI route handlers
│   ├── core/
│   │   ├── config.py     # Pydantic settings (reads from .env)
│   │   └── logger.py     # Loguru setup
│   ├── db/
│   │   ├── models.py     # SQLAlchemy ORM models
│   │   ├── crud.py       # Database CRUD operations
│   │   └── session.py    # Async engine & session factory
│   └── services/
│       ├── analyst_agent.py  # LangGraph AI research pipeline
│       ├── watcher.py        # Price monitoring & trigger logic
│       ├── sec_service.py    # SEC filing fetcher & MD&A extractor
│       └── notifier.py       # Telegram bot & report delivery
├── scripts/
│   └── test_agent_flow.py    # End-to-end integration test
├── .env.example
├── requirements.txt
└── README.md
```
