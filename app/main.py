from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from app.core.config import get_settings
from app.core.logger import setup_logging
from app.api.router import api_router
from app.services.watcher import watcher_engine
from app.services.notifier import notifier

settings = get_settings()

# Initialize Scheduler
scheduler = AsyncIOScheduler()
# Track whether the Telegram polling was actually started
_is_bot_running = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle application startup and shutdown events.
    - Setup logging
    - Start scheduler
    - Database engine cleanup
    - Start Telegram Bot polling
    """
    global _is_bot_running

    # Startup
    setup_logging()
    logger.info(f"Starting {settings.PROJECT_NAME}...")
    
    # 1. Start Telegram Bot polling (non-blocking)
    try:
        if notifier.ptb_app:
            await notifier.ptb_app.initialize()
            await notifier.ptb_app.start()
            await notifier.ptb_app.updater.start_polling()
            _is_bot_running = True
            logger.info("Telegram interactive bot polling started.")
    except Exception as e:
        _is_bot_running = False
        logger.error(f"Failed to start Telegram interactive bot: {e}")
        logger.warning("Application will continue without interactive Telegram support.")
    
    # 2. Start Scheduler
    scheduler.start()
    logger.info("Background scheduler started.")
    
    # 3. Add Watcher Job (Run every 5 minutes)
    scheduler.add_job(
        watcher_engine.run_cycle,
        "interval",
        minutes=5,
        id="watcher_job",
        replace_existing=True
    )
    logger.info("Watcher job scheduled (every 5 minutes).")
    
    yield
    
    # Shutdown
    # 1. Telegram Bot Shutdown (only if it actually started)
    if _is_bot_running and notifier.ptb_app:
        try:
            await notifier.ptb_app.updater.stop()
            await notifier.ptb_app.stop()
            await notifier.ptb_app.shutdown()
            logger.info("Telegram interactive bot shut down.")
        except Exception as e:
            logger.error(f"Error during Telegram bot shutdown: {e}")

    # 2. Scheduler Shutdown
    scheduler.shutdown()
    logger.info("Background scheduler shut down.")
    logger.info(f"Shutting down {settings.PROJECT_NAME}...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    lifespan=lifespan,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Global Exception Handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "message": str(exc)},
    )

@app.get("/", tags=["root"])
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "docs": "/docs",
        "api_v1": settings.API_V1_STR
    }

@app.get("/health", tags=["system"])
async def health_check():
    """
    Health check endpoint for production load balancers and orchestrators.
    """
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable: DB connection failed")
