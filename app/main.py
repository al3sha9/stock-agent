from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from app.core.config import get_settings
from app.core.logger import setup_logging
from app.api.router import api_router
from app.services.watcher import watcher_engine

settings = get_settings()

# Initialize Scheduler
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle application startup and shutdown events.
    - Setup logging
    - Start scheduler
    - Database engine cleanup (handled by SQLAlchemy async engine automatically, 
      but can be added here if explicit disposal is needed)
    """
    # Startup
    setup_logging()
    logger.info(f"Starting {settings.PROJECT_NAME}...")
    
    # Start Scheduler
    scheduler.start()
    logger.info("Background scheduler started.")
    
    # Add Watcher Job (Run every 5 minutes)
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
    allow_origins=["*"], # Adjust for production
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
