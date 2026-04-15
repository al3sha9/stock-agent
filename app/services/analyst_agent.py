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

settings = get_settings()

class AgentState(TypedDict):
    """
    State shared between nodes in the Analyst Agent graph.
    """
    ticker: str
    current_price: float
    trigger_event_id: Optional[uuid.UUID]
    financial_data: Dict[str, Any]
    intrinsic_value: float
    recommendation: str
    messages: Annotated[List[Any], operator.add]

# --- Nodes ---

async def fetch_financials(state: AgentState) -> Dict[str, Any]:
    """
    Node: Fetches Income Statement and Cash Flow data via yfinance.
    """
    ticker_symbol = state["ticker"]
    logger.info(f"Agent Node [fetch_financials]: Fetching data for {ticker_symbol}")
    
    try:
        ticker = await asyncio.to_thread(yf.Ticker, ticker_symbol)
        income_stmt = await asyncio.to_thread(lambda: ticker.income_stmt)
        cash_flow = await asyncio.to_thread(lambda: ticker.cash_flow)
        
        financials = {
            "net_income": float(income_stmt.loc["Net Income"].iloc[0]) if "Net Income" in income_stmt.index else 0,
            "free_cash_flow": float(cash_flow.loc["Free Cash Flow"].iloc[0]) if "Free Cash Flow" in cash_flow.index else 0,
            "total_revenue": float(income_stmt.loc["Total Revenue"].iloc[0]) if "Total Revenue" in income_stmt.index else 0,
        }
        
        return {"financial_data": financials}
    except Exception as e:
        logger.error(f"Agent Node [fetch_financials] Error: {e}")
        return {"financial_data": {"error": str(e)}}

async def calculate_dcf(state: AgentState) -> Dict[str, Any]:
    """
    Node: Logic node for valuation.
    """
    fcf = state["financial_data"].get("free_cash_flow", 0)
    if fcf <= 0:
        intrinsic_val = 0.0
    else:
        intrinsic_val = (fcf * 15) / 1_000_000_000
        
    return {"intrinsic_value": round(intrinsic_val, 2)}

async def generate_report(state: AgentState) -> Dict[str, Any]:
    """
    Node: LLM node to summarize findings using Gemini 2.5 Flash.
    """
    if not settings.GOOGLE_API_KEY:
        return {"recommendation": "LLM Analysis Unavailable: No API Key."}

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash", 
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=0.1,
        max_retries=3
    )
    
    prompt = f"""
    # ROLE
    You are a Senior Equity Analyst. 
    Analyze the financial health and valuation for: {state['ticker']}
    
    # DATA
    * Current Price: ${state['current_price']}
    * Financials: {state['financial_data']}
    * Intrinsic Value: ${state['intrinsic_value']}
    
    # INSTRUCTIONS
    1. Compare Price vs. Intrinsic Value.
    2. Provide a clear recommendation (BUY, HOLD, or SELL).
    3. Strictly limit your response to 2-3 concise sentences.
    
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
        logger.warning("No trigger_event_id found in state. Skipping DB persistence.")
        return {}

    logger.info(f"Agent Node [save_results]: Saving findings for Event {event_id}")
    
    async with AsyncSessionLocal() as db:
        await crud.update_trigger_event_analysis(
            db, 
            event_id, 
            state["intrinsic_value"], 
            state["recommendation"]
        )
    
    return {}

# --- Graph ---

workflow = StateGraph(AgentState)

workflow.add_node("fetch_financials", fetch_financials)
workflow.add_node("calculate_dcf", calculate_dcf)
workflow.add_node("generate_report", generate_report)
workflow.add_node("save_results", save_results)

workflow.add_edge(START, "fetch_financials")
workflow.add_edge("fetch_financials", "calculate_dcf")
workflow.add_edge("calculate_dcf", "generate_report")
workflow.add_edge("generate_report", "save_results")
workflow.add_edge("save_results", END)

analyst_graph = workflow.compile()
