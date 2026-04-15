import asyncio
import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from loguru import logger
from typing import Optional

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.db import crud
from app.schemas.stock import WatchlistCreate

settings = get_settings()

class TelegramNotifier:
    """
    Service for sending investment reports and handling interactive commands.
    Fully multi-tenant: supports unique watchlists per user chat ID.
    """

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self._ptb_app = None

    @property
    def ptb_app(self):
        if not self._ptb_app and self.bot_token:
            base_url = settings.TELEGRAM_BASE_URL

            builder = (
                ApplicationBuilder()
                .token(self.bot_token)
                .connect_timeout(30)
                .read_timeout(30)
            )

            if base_url:
                # Normalize: strip trailing slash, ensure it ends with /bot
                base_url = base_url.rstrip("/")
                if not base_url.endswith("/bot"):
                    base_url = f"{base_url}/bot"
                # Derive file URL by replacing the trailing /bot with /file/bot
                file_url = base_url[:-4] + "/file/bot"
                builder = builder.base_url(base_url).base_file_url(file_url)
                logger.info(f"Telegram Bot is using Cloudflare Proxy: {base_url}")
            else:
                logger.info("Telegram Bot is using default Telegram API.")

            self._ptb_app = builder.build()
            self._setup_handlers()
        return self._ptb_app

    def _setup_handlers(self):
        """Register command handlers."""
        self._ptb_app.add_handler(CommandHandler("start", self.start_command))
        self._ptb_app.add_handler(CommandHandler("add", self.add_command))
        self._ptb_app.add_handler(CommandHandler("remove", self.remove_command))
        self._ptb_app.add_handler(CommandHandler("list", self.list_command))
        self._ptb_app.add_handler(CommandHandler("status", self.status_command))
        logger.info("Telegram command handlers registered.")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /start."""
        welcome_text = (
            "\U0001f680 *Stock Monitor Agent Active*\n\n"
            "This bot tracks stocks and provides AI analysis.\n"
            "Use the following commands:\n"
            "\u2022 `/add TICKER PRICE` \\- Watch a new stock\n"
            "\u2022 `/remove TICKER` \\- Stop watching a stock\n"
            "\u2022 `/list` \\- See your personal watchlist\n"
            "\u2022 `/status TICKER` \\- Immediate AI analysis"
        )
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2)

    async def add_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /add TICKER PRICE."""
        try:
            if len(context.args) < 2:
                await update.message.reply_text("Usage: `/add AAPL 150`", parse_mode=ParseMode.MARKDOWN_V2)
                return

            ticker_sym = context.args[0].upper()
            target_price = float(context.args[1])

            # Get current price for confirmation
            ticker = yf.Ticker(ticker_sym)
            info = await asyncio.to_thread(lambda: ticker.info)
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")

            if not current_price:
                await update.message.reply_text(f"❌ Could not find market price for {ticker_sym}")
                return

            user_id = str(update.effective_chat.id)

            async with AsyncSessionLocal() as db:
                # Check if already exists for this user
                existing = await crud.get_watchlist_item_by_ticker(db, ticker_sym, user_id)
                if existing:
                    await update.message.reply_text(f"\u2139\ufe0f {ticker_sym} is already on your watchlist\\.")  
                    return

                await crud.create_watchlist_item(
                    db, 
                    WatchlistCreate(
                        ticker=ticker_sym, 
                        target_price=target_price, 
                        drop_trigger=10.0,
                        telegram_chat_id=user_id
                    )
                )

            await update.message.reply_text(
                f"\u2705 Added *{ticker_sym}* to watchlist\\.\n"
                f"\U0001f4b0 Current Price: ${current_price:.2f}\n"
                f"\U0001f3af Target Price: ${target_price:.2f}",
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Error in /add: {e}")
            await update.message.reply_text(f"❌ Error adding stock: {str(e)}")

    async def remove_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /remove TICKER."""
        try:
            if not context.args:
                await update.message.reply_text("Usage: `/remove TICKER`", parse_mode=ParseMode.MARKDOWN_V2)
                return

            ticker_sym = context.args[0].upper()
            user_id = str(update.effective_chat.id)

            async with AsyncSessionLocal() as db:
                success = await crud.remove_watchlist_item(db, ticker_sym, user_id)

            if success:
                await update.message.reply_text(f"\U0001f5d1 Removed *{ticker_sym}* from watchlist\\.", parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(f"\u274c {ticker_sym} was not found on your watchlist\\.")  
        except Exception as e:
            logger.error(f"Error in /remove: {e}")
            await update.message.reply_text(f"❌ Error removing stock: {str(e)}")

    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /list."""
        try:
            user_id = str(update.effective_chat.id)
            async with AsyncSessionLocal() as db:
                watchlist = await crud.get_user_watchlist(db, user_id)

            if not watchlist:
                await update.message.reply_text("Your watchlist is currently empty\\.")  
                return

            lines = ["\U0001f4cb *Current Watchlist:*\n"]
            for item in watchlist:
                price_str = escape_markdown(f"{item.target_price:.2f}", version=2)
                lines.append(f"\u2022 *{item.ticker}* \\- Target: ${price_str}")
            
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in /list: {e}")
            await update.message.reply_text("\u274c Error listing watchlist\\.")  

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler for /status TICKER."""
        try:
            if not context.args:
                await update.message.reply_text("Usage: `/status TICKER`", parse_mode=ParseMode.MARKDOWN_V2)
                return

            ticker_sym = context.args[0].upper()
            await update.message.reply_text(
                f"\U0001f50d Analyzing *{ticker_sym}*\\.\\.\\. This may take 30 seconds\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )

            # Lazy import to avoid circular dependency
            from app.services.analyst_agent import analyst_graph

            # Get current price
            ticker = yf.Ticker(ticker_sym)
            info = await asyncio.to_thread(lambda: ticker.info)
            current_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

            user_id = str(update.effective_chat.id)

            initial_state = {
                "ticker": ticker_sym,
                "current_price": current_price,
                "trigger_event_id": None,
                "telegram_chat_id": user_id,
                "messages": []
            }

            # Graph handles sending the notification itself at the end!
            await analyst_graph.ainvoke(initial_state)
            
        except Exception as e:
            logger.error(f"Error in /status: {e}")
            await update.message.reply_text(f"❌ Analysis failed for {ticker_sym}: {str(e)}")

    async def send_investment_report(
        self, 
        chat_id: str,
        ticker: str, 
        report: str, 
        intrinsic_value: float, 
        current_price: float
    ):
        """
        Sends a formatted investment report to the configured Telegram chat.
        """
        if not self.ptb_app or not chat_id:
            logger.warning("Telegram Bot Token or Chat ID empty. Notification skipped.")
            return

        # Simple Status-based rec
        recommendation = "HOLD"
        if current_price <= intrinsic_value * 0.9:
            recommendation = "BUY (Undervalued)"
        elif current_price >= intrinsic_value * 1.1:
            recommendation = "SELL (Overvalued)"

        safe_ticker = escape_markdown(ticker, version=2)
        safe_rec = escape_markdown(recommendation, version=2)
        safe_report = escape_markdown(report, version=2)
        iv_str = escape_markdown(f"{intrinsic_value:.2f}", version=2)
        cp_str = escape_markdown(f"{current_price:.2f}", version=2)

        message = (
            f"🎯 *Ticker:* ${safe_ticker}\n\n"
            f"💰 *Current Price:* ${cp_str}\n"
            f"💎 *Intrinsic Value:* ${iv_str}\n"
            f"📢 *Recommendation:* {safe_rec}\n\n"
            f"📝 *Analysis:*\n{safe_report}"
        )

        if len(message) > 4090:
            header_len = message.find("Analysis:") + 10
            truncated_analysis = safe_report[:4000 - header_len] + " \\.\\.\\. \\[Truncated\\]"
            message = (
                f"🎯 *Ticker:* ${safe_ticker}\n\n"
                f"💰 *Current Price:* ${cp_str}\n"
                f"💎 *Intrinsic Value:* ${iv_str}\n"
                f"📢 *Recommendation:* {safe_rec}\n\n"
                f"📝 *Analysis:*\n{truncated_analysis}"
            )

        try:
            # We use the internal bot instance from ptb_app
            await self.ptb_app.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            logger.success(f"Telegram investment report sent for {ticker}")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")

# Global instance
notifier = TelegramNotifier()
