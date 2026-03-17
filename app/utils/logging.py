import structlog
import logging
from app.config import settings


def setup_logging():
    log_level = logging.DEBUG if settings.ENV == "local" else logging.INFO
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer() if settings.ENV != "local"
            else structlog.dev.ConsoleRenderer(),
        ],
    )
