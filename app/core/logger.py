import sys
from loguru import logger

def setup_logging() -> None:
    """
    Configure loguru for structured, professional logging.
    Removes default handler and adds a formatted stdout handler.
    """
    # Remove default handler
    logger.remove()
    
    # Add professional format handler
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )
    
    # Optional: Log to file if needed later
    # logger.add("logs/app.log", rotation="500 MB", level="DEBUG")

    logger.info("Logging initialized.")
