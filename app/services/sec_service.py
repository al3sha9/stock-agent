import httpx
import re
import json
from bs4 import BeautifulSoup
from loguru import logger
from typing import Optional, List, Dict
from cachetools import TTLCache
from app.core.config import get_settings

settings = get_settings()

class SECService:
    """
    Service for fetching and parsing SEC filings using FMP API (Primary) 
    and SEC EDGAR (Fallback).
    """
    
    FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
    SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
    SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
    SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no_no_dashes}/{primary_doc}"
    
    # Required as per SEC fair access policy
    DEFAULT_USER_AGENT = f"StockAgent/1.0 ({settings.CONTACT_EMAIL or 'info@example.com'})"

    # TTL Caches: 24 hours (86400 seconds)
    # Stores Ticker->URL mapping and URL->HTML Text mapping
    url_cache = TTLCache(maxsize=500, ttl=86400)
    text_cache = TTLCache(maxsize=500, ttl=86400)

    @classmethod
    async def _get_cik_from_ticker(cls, ticker: str) -> Optional[str]:
        """
        Maps a ticker symbol to its 10-digit zero-padded CIK using internal SEC mapping.
        """
        headers = {"User-Agent": cls.DEFAULT_USER_AGENT}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(cls.SEC_TICKERS_URL, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # data is a dict of indices mapping to {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
                ticker_upper = ticker.upper()
                for entry in data.values():
                    if entry.get("ticker") == ticker_upper:
                        return str(entry["cik_str"]).zfill(10)
        except Exception as e:
            logger.error(f"Error mapping ticker {ticker} to CIK: {e}")
        return None

    @classmethod
    async def _get_filing_url_from_edgar(cls, cik: str, filing_type: str) -> Optional[str]:
        """
        Queries the official SEC EDGAR API for the latest filing link.
        """
        headers = {"User-Agent": cls.DEFAULT_USER_AGENT}
        url = cls.SEC_SUBMISSIONS_URL.format(cik=cik)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                recent_filings = data.get("filings", {}).get("recent", {})
                if not recent_filings:
                    return None

                # Search for the latest matching form type
                forms = recent_filings.get("form", [])
                for i, form in enumerate(forms):
                    if form == filing_type:
                        acc_no = recent_filings["accessionNumber"][i]
                        acc_no_no_dashes = acc_no.replace("-", "")
                        primary_doc = recent_filings["primaryDocument"][i]
                        
                        # Build the download URL
                        # Note: We remove the leading zeros for the CIK in the Archives path
                        short_cik = cik.lstrip('0')
                        return cls.SEC_ARCHIVES_URL.format(
                            cik=short_cik,
                            acc_no_no_dashes=acc_no_no_dashes,
                            primary_doc=primary_doc
                        )
        except Exception as e:
            logger.error(f"Error finding EDGAR filing for CIK {cik}: {e}")
        return None

    @classmethod
    async def get_sec_filing_manually(cls, ticker: str, filing_type: str = "10-K") -> Optional[str]:
        """
        Fallback logic to retrieve filing link directly from SEC.gov.
        Includes a 24-hour cache layer to prevent spamming EDGAR.
        """
        cache_key = f"{ticker}_{filing_type}"
        try:
            if cache_key in cls.url_cache:
                logger.info(f"Cache HIT for {ticker} ({filing_type}) URL.")
                return cls.url_cache[cache_key]
        except Exception as e:
            logger.warning(f"url_cache error: {e}")

        logger.info(f"Attempting manual SEC EDGAR lookup for {ticker} ({filing_type})...")
        cik = await cls._get_cik_from_ticker(ticker)
        if not cik:
            return None
            
        url = await cls._get_filing_url_from_edgar(cik, filing_type)
        if url:
            try:
                cls.url_cache[cache_key] = url
            except Exception as e:
                logger.warning(f"url_cache set error: {e}")
                
        return url

    @classmethod
    async def get_latest_filing_url(cls, ticker: str, filing_type: str = "10-K") -> Optional[str]:
        """
        Retrieves the URL of the most recent SEC filing. 
        Falls back to EDGAR if FMP fails (e.g. 403 Forbidden).
        """
        if settings.FMP_API_KEY:
            fmp_url = f"{cls.FMP_BASE_URL}/sec_filings/{ticker}?type={filing_type}&page=0&apikey={settings.FMP_API_KEY}"
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(fmp_url)
                    response.raise_for_status()
                    filings = response.json()
                    
                    if filings and len(filings) > 0:
                        return filings[0].get("finalLink")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    logger.warning(f"FMP tier limit reached (403) for {ticker}. Falling back to SEC EDGAR.")
                else:
                    logger.error(f"FMP API error: {e}")
            except Exception as e:
                logger.error(f"Unexpected FMP error: {e}")

        # Fallback to SEC EDGAR
        return await cls.get_sec_filing_manually(ticker, filing_type)

    @classmethod
    async def fetch_filing_text(cls, url: str) -> str:
        """
        Downloads a filing and attempts to extract the MD&A section.
        Caches the text output for 24 hours.
        """
        try:
            if url in cls.text_cache:
                logger.info("Cache HIT for SEC filing text.")
                return cls.text_cache[url]
        except Exception as e:
            logger.warning(f"text_cache error: {e}")

        # Always include User-Agent for SEC.gov domains
        headers = {"User-Agent": cls.DEFAULT_USER_AGENT}
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                html_content = response.text
                
            soup = BeautifulSoup(html_content, 'html.parser')
            for script_or_style in soup(["script", "style"]):
                script_or_style.decompose()

            text = soup.get_text(separator=' ', strip=True)
            
            # Refined MD&A patterns for EDGAR HTML
            mda_patterns = [
                r"Item\s+7\.\s+Management['’]s\s+Discussion\s+and\s+Analysis",
                r"Item\s+2\.\s+Management['’]s\s+Discussion\s+and\s+Analysis"
            ]
            
            start_idx = -1
            for pattern in mda_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    start_idx = match.start()
                    break
            
            if start_idx == -1:
                logger.warning(f"Could not find MD&A markers in filing: {url}")
                return text[:5000] + "... [Truncated: MD&A markers not found]"

            end_patterns = [
                r"Item\s+8\.\s+Financial\s+Statements",
                r"Item\s+3\.\s+Quantitative\s+and\s+Qualitative"
            ]
            
            end_idx = -1
            for pattern in end_patterns:
                match = re.search(pattern, text[start_idx:], re.IGNORECASE)
                if match:
                    end_idx = start_idx + match.start()
                    break
            
            if end_idx == -1:
                return text[start_idx:start_idx + 8000] + "... [Truncated]"
            
            extracted = text[start_idx:end_idx].strip()
            if len(extracted) > 10000:
                extracted = extracted[:10000] + "... [Truncated]"
                
            # Store in cache
            try:
                cls.text_cache[url] = extracted
            except Exception as e:
                logger.warning(f"text_cache set error: {e}")
                
            return extracted

        except Exception as e:
            logger.error(f"Error parsing filing at {url}: {e}")
            return f"Error extracting filing content: {str(e)}"

# Global instance
sec_service = SECService()
