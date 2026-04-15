import asyncio
import uuid
from typing import Dict, Any, List, Annotated, Optional
from typing_extensions import TypedDict
import operator
import yfinance as yf
from loguru import logger
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.db import crud
from app.services.sec_service import sec_service
from app.services.notifier import notifier

settings = get_settings()

class AgentState(TypedDict):
    """
    State shared between nodes in the Analyst Agent graph.
    """
    ticker: str
    current_price: float
    trigger_event_id: Optional[uuid.UUID]
    financial_data: Dict[str, Any]
    filing_context: str
    shares_outstanding: int
    intrinsic_value: float
    rsi: Optional[float]
    sma20: Optional[float]
    recommendation: str
    messages: Annotated[List[Any], operator.add]

# --- Nodes ---

async def fetch_financials(state: AgentState) -> Dict[str, Any]:
    """
    Node: Fetches Income Statement, Cash Flow, and Shares Outstanding via yfinance
    AND SEC filings (MD&A) via SEC Service.
    """
    ticker_symbol = state["ticker"]
    logger.info(f"Agent Node [fetch_financials]: Fetching metrics and SEC filings for {ticker_symbol}")
    
    # 1. Fetch YFinance Data
    shares_outstanding = state.get("shares_outstanding", 0)
    try:
        ticker = await asyncio.to_thread(yf.Ticker, ticker_symbol)
        income_stmt = await asyncio.to_thread(lambda: ticker.income_stmt)
        cash_flow = await asyncio.to_thread(lambda: ticker.cash_flow)
        
        # Only fetch info if shares_outstanding is not already set
        if shares_outstanding == 0:
            info = await asyncio.to_thread(lambda: ticker.info)
            shares_outstanding = info.get("sharesOutstanding", 0)
        
        financials = {
            "net_income": float(income_stmt.loc["Net Income"].iloc[0]) if "Net Income" in income_stmt.index else 0,
            "free_cash_flow": float(cash_flow.loc["Free Cash Flow"].iloc[0]) if "Free Cash Flow" in cash_flow.index else 0,
            "total_revenue": float(income_stmt.loc["Total Revenue"].iloc[0]) if "Total Revenue" in income_stmt.index else 0,
        }
    except Exception as e:
        logger.error(f"YFinance Error in fetch_financials: {e}")
        financials = {"error": str(e)}

    # 2. Fetch SEC Filing Context
    filing_ctx = "No SEC filings retrieved."
    try:
        filing_url = await sec_service.get_latest_filing_url(ticker_symbol, "10-K")
        if filing_url:
            logger.info(f"Found latest 10-K at {filing_url}. Extracting MD&A...")
            filing_ctx = await sec_service.fetch_filing_text(filing_url)
        else:
            filing_url = await sec_service.get_latest_filing_url(ticker_symbol, "10-Q")
            if filing_url:
                logger.info(f"Found latest 10-Q at {filing_url}. Extracting MD&A...")
                filing_ctx = await sec_service.fetch_filing_text(filing_url)
    except Exception as e:
        logger.error(f"SEC Service Error in fetch_financials: {e}")
        filing_ctx = f"Error retrieving SEC context: {str(e)}"
        
    return {
        "financial_data": financials,
        "filing_context": filing_ctx,
        "shares_outstanding": shares_outstanding
    }

async def calculate_dcf(state: AgentState) -> Dict[str, Any]:
    """
    Node: Logic node for valuation. Calculates per-share intrinsic value.
    Formula: (FCF * 15) / Shares Outstanding
    """
    fcf = state["financial_data"].get("free_cash_flow", 0)
    shares = state.get("shares_outstanding", 0)
    
    if fcf <= 0 or shares <= 0:
        logger.warning(f"Incomplete data for DCF: FCF={fcf}, Shares={shares}")
        return {"intrinsic_value": 0.0}
    
    intrinsic_val = (fcf * 15) / shares
        
    return {"intrinsic_value": round(intrinsic_val, 2)}

async def generate_report(state: AgentState) -> Dict[str, Any]:
    """
    Node: LLM node to summarize findings using Gemini 2.5 Flash.
    Now incorporates per-share valuation, technical indicators (RSI/SMA), and shares context.
    """
    if not settings.GOOGLE_API_KEY:
        return {"recommendation": "LLM Analysis Unavailable: No API Key."}

    shares = state.get("shares_outstanding", 0)
    if shares <= 0:
        return {"recommendation": f"DATA_INCOMPLETE: Could not retrieve shares outstanding for {state['ticker']}."}

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.1,
        max_retries=3
    )
    
    if shares >= 1_000_000_000:
        share_text = f"{shares / 1_000_000_000:.2f}B"
    elif shares >= 1_000_000:
        share_text = f"{shares / 1_000_000:.2f}M"
    else:
        share_text = f"{shares:,}"

    # Technical Context
    rsi = state.get("rsi")
    sma20 = state.get("sma20")
    tech_context = ""
    if rsi is not None and sma20 is not None:
        tech_context = f"\n* Technical Indicators: RSI(14)={rsi}, 20-day SMA=${sma20}"

    prompt = f"""
    # ROLE
    You are a Senior Equity Analyst. 
    Analyze the financial health, valuation, and technical setup for: {state['ticker']}
    
    # DATA
    * Current Price: ${state['current_price']}
    * Shares Outstanding: {share_text}
    * Financials: {state['financial_data']}{tech_context}
    * Intrinsic Value (Per Share): ${state['intrinsic_value']}
    
    # QUALITATIVE CONTEXT (SEC MD&A)
    {state['filing_context'][:8000]}
    
    # INSTRUCTIONS
    1. Compare Price vs. Intrinsic Value. Mention the share count ({share_text}) used in the valuation.
    2. If technical indicators are provided, mention them to confirm or conflict with the fundamental value (e.g., "The stock is currently oversold with an RSI of {rsi}, confirming a significant short-term dip").
    3. Incorporate qualitative insights from the SEC context regarding management guidance or risks.
    4. Provide a clear recommendation (BUY, HOLD, or SELL).
    5. Strictly limit your response to 4 concise sentences.
    
    # RECOMMENDATION
    """
    
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return {"recommendation": response.content}
    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        return {"recommendation": "Error generating recommendation."}

async def save_results(state: AgentState) -> Dict[str, Any]:
    """
    Node: Persists analysis findings to the database.
    """
    event_id = state.get("trigger_event_id")
    if not event_id:
        return {}
    
    async with AsyncSessionLocal() as db:
        await crud.update_trigger_event_analysis(
            db, 
            event_id, 
            state["intrinsic_value"], 
            state["recommendation"]
        )
    
    return {}

async def notify_user(state: AgentState) -> Dict[str, Any]:
    """
    Node: Sends a notification to Telegram with the investment report.
    """
    logger.info(f"Agent Node [notify_user]: Sending report for {state['ticker']}")
    
    try:
        await notifier.send_investment_report(
            ticker=state["ticker"],
            report=state["recommendation"],
            intrinsic_value=state["intrinsic_value"],
            current_price=state["current_price"]
        )
    except Exception as e:
        logger.error(f"Failed to send Telegram notification in node: {e}")
        
    return {}

# --- Graph ---

workflow = StateGraph(AgentState)

workflow.add_node("fetch_financials", fetch_financials)
workflow.add_node("calculate_dcf", calculate_dcf)
workflow.add_node("generate_report", generate_report)
workflow.add_node("save_results", save_results)
workflow.add_node("notify_user", notify_user)

workflow.add_edge(START, "fetch_financials")
workflow.add_edge("fetch_financials", "calculate_dcf")
workflow.add_edge("calculate_dcf", "generate_report")
workflow.add_edge("generate_report", "save_results")
workflow.add_edge("save_results", "notify_user")
workflow.add_edge("notify_user", END)

analyst_graph = workflow.compile()
