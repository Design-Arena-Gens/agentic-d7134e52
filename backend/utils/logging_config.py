"""Structured JSON logging configuration"""
import logging
import sys
from pythonjsonlogger import jsonlogger
from backend.config import settings


def setup_logging():
    """Setup structured JSON logging"""
    log_handler = logging.StreamHandler(sys.stdout)

    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s',
        timestamp=True
    )

    log_handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.addHandler(log_handler)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    # Reduce noise from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
