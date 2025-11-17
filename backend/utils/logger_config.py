import os

from loguru import logger

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

# Configure loguru
logger.add(
    "logs/app.log",
    rotation="100 MB",  # Rotate log file when it reaches 100 MB
    retention="30 days",  # Keep logs for 30 days
    compression="zip",  # Compress old logs
    backtrace=True,  # Include traceback info for errors
    diagnose=True,  # Show variable values in tracebacks
    level="INFO",  # Log level threshold
)
