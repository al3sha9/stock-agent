# 📈 Stock Monitoring Agent

> **An autonomous, AI-driven financial research system** that monitors stock prices, identifies technical buy signals, conducts SEC filing analysis, performs DCF valuation, and delivers professional investment reports — directly to your Telegram.

---

## 🧠 What Is This?

The **Stock Monitoring Agent** is a multi-tenant, production-ready backend framework acting as your personal, always-on equity analyst. You configure a stock watchlist, set your target prices, and the system handles everything else — from real-time price monitoring to generating AI-powered investment reports and delivering them directly to your phone.

It is **not a trading bot** — it does not execute trades. Instead, it is a **secure research and alerting tool** combining advanced quantitative DCF modeling, technical momentum signals, and qualitative SEC/News sentiment analysis to yield elite actionable insights.

---

## 🏗️ How It Works — The Full Pipeline

The system operates as a continuous loop with five distinct phases:

```
Price Monitoring → Trigger Detection → AI Research Agent (Fan-Out/Fan-In) → 5Y DCF Valuation → Report & Notify
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

### Phase 3: AI Research (LangGraph Pipeline)
When a trigger fires, a stateful **LangGraph** asynchronous state machine is launched. It features Fan-Out execution to pull parallel context:

```
[START]
   ↘→ fetch_financials (SEC EDGAR) ━━↘
   ↘→ analyze_sentiment (Tavily) ━━━━↘ [WAIT] → estimate_growth → calculate_dcf → generate_report → save_results → notify_user
```

#### `fetch_financials` & `analyze_sentiment` (Parallel Execution)
- **Financial Fetcher**: Pulls Income Statements and cached SEC EDGAR filings (MD&A sections) to ground the AI in raw quantitative figures and corporate strategy.
- **Sentiment Analyzer**: Queries the **Tavily API** natively filtering the last 24-hours for *"why is [TICKER] stock price moving today?"* to grab live headlines protecting against value traps (e.g., lawsuits, earnings downgrades).
- Both requests deduplicate and execute asynchronously.

#### `estimate_growth` & `calculate_dcf`
- Identifies FCF metrics and utilizes **Gemini 2.5 Flash** (via Pydantic `.with_structured_output`) to accurately infer a conservative 5-Year growth horizon based on SEC language constraints (-20% to +50% bounded).
- Calculates the true **Present Value** by discounting a robust 5-year compounding FCF logic base and generating a terminal value through the **Gordon Growth Method** (2% perpetual market cap).

#### `generate_report`
- Fuses all context variables together inside Gemini. It weighs the hard DCF numbers vs short-term Technicals (RSI) vs active market sentiment headlines.
- Gemini is rigidly enforced to "Show Its Work", mandated to append an auditing sentence string validating its FCF/Discount rate choices against the share outstanding parameters.

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

> **Security (RBAC)**: All commands execute through an isolated `@verify_user` decorator. Untrusted users who ping the bot will trigger an auto-register protocol adding their Telegram ID to your database waitlist as `is_active=False` and immediately terminating their connections.

The bot uses **polling mode**, running inside the FastAPI application's async event loop alongside the price watcher and REST API — no separate process needed.

---

## 🔧 Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **API Boundary** | FastAPI | REST API + async lifecycle management, secured by headers. |
| **Orchestrator** | LangGraph | Stateful multi-step research pipeline mapping fan-in/fan-out graph state structures. |
| **Database** | Supabase (PostgreSQL) | Persistent multi-tenant watchlist, RBAC user state, & event storage |
| **Market Data** | yfinance | Real-time prices, financials, share data |
| **Sentiment Context** | Tavily Search SDK | Real-Time Live web probing identifying catalysts |
| **Deployment** | Docker | Production container image powered by `python:3.12-slim` |
| **Logging** | Loguru | Serialize=True mapped output streaming directly to standard cloud JSON outputs. |

---

## 🗄️ Data Models

### `User` (RBAC Control)
| Field | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `telegram_chat_id` | String | Unique endpoint location identifier for Telegram connections |
| `is_active` | Boolean | Gating boolean required to utilize system commands |

### `Watchlist`
| Field | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `telegram_chat_id` | String | Foreign-key scoping allowing dynamic isolated tracking |
| `ticker` | String | Stock symbol (e.g., `AAPL`) |
| `target_price` | Float | Price level that triggers analysis |
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
TAVILY_API_KEY=your-tavily-api-search-key

# SEC Data
FMP_API_KEY=your-fmp-api-key

# API Security
API_KEY=your-super-secret-rest-header-wrapper

# Telegram
TELEGRAM_BOT_TOKEN=your-bot-token-from-botfather

# Optional: Cloudflare reverse proxy (leave empty to use default Telegram API)
TELEGRAM_BASE_URL=https://your-worker.workers.dev/bot
```

> [!IMPORTANT]
> Use the **Supavisor Transaction Mode** connection string (port `6543`), not the direct connection. The app disables prepared statement caching for full compatibility with Supabase's connection pooler.

> [!TIP]
> To get your API Access Chat ID, message [@userinfobot](https://t.me/userinfobot) on Telegram.

---

## 🚀 Setup & Running

### Prerequisites
- Python 3.12+ (or Docker desktop)
- A [Supabase](https://supabase.com) project
- A [Google AI Studio](https://aistudio.google.com) API key
- A [Tavily](https://tavily.com/) Search API key
- A Telegram bot token from [@BotFather](https://tme/BotFather)

### 1. Clone & Configure
```bash
git clone https://github.com/al3sha9/stock-agent.git
cd stock-agent
cp .env.example .env
# Input your keys into the .env file!
```

### 2. Run the App (Docker Native Deployment)
The fastest way to deploy the system safely isolating all processes:
```bash
docker build -t stock-agent-app .
docker run --env-file .env -p 8000:8000 -it stock-agent-app
```
*Your application is now natively health-checked and load balancer ready on `localhost:8000/health`*

### 3. Initialize Admin Access / Telemetry
The bot boots utilizing zero-trust database protections. Once the server is running, execute the bootstrapping script natively to seed your personal chat parameters straight into the mapped active Supabase schemas:

```bash
# If developing locally (bypassing docker):
python scripts/seed_admin.py 
# Then follow the CLI prompts to input your active Chat ID!
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
