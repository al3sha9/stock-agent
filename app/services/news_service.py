import asyncio
from loguru import logger
from tavily import AsyncTavilyClient
from app.core.config import get_settings

settings = get_settings()

class TavilyNewsService:
    """
    Service for wrapping the Tavily SDK to fetch structured real-time market news.
    """

    def __init__(self):
        self.api_key = settings.TAVILY_API_KEY
        self.client = AsyncTavilyClient(api_key=self.api_key) if self.api_key else None

    async def get_ticker_news(self, ticker: str) -> str:
        """
        Searches for news from the last 24 hours regarding why the stock price is moving.
        Returns a formatted, raw text block of context.
        """
        if not self.client:
            logger.warning("No TAVILY_API_KEY found. Skipping sentiment analysis.")
            return "No news sentiment retrieved (API key absent)."

        query = f"why is {ticker} stock price moving today?"
        logger.info(f"NewsService: Fetching live sentiment context for {ticker}...")

        try:
            # We specifically look for recent news articles vs general data.
            response = await self.client.search(
                query=query,
                search_depth="basic",
                include_answer=False,
                include_raw_content=False,
                days=1
            )
            
            results = response.get("results", [])
            if not results:
                return "No fresh news catalysts found in the last 24 hours."

            # Format the output context
            context_blocks = []
            for item in results[:5]:  # Top 5 articles
                title = item.get("title", "Unknown Title")
                content = item.get("content", "No content snippet.")
                url = item.get("url", "")
                context_blocks.append(f"- Headline: {title}\n  Summary: {content}")
                
            merged_context = "\n\n".join(context_blocks)
            return merged_context

        except Exception as e:
            logger.error(f"Tavily News Service Error: {e}")
            return f"Error retrieving market news: {str(e)}"

# Global instance
news_service = TavilyNewsService()
