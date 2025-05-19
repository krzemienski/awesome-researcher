"""
Logging utilities for structured logging with ISO 8601 timestamps.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that formats logs as JSON with ISO 8601 timestamps.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string."""
        iso_time = datetime.utcnow().isoformat() + 'Z'

        log_data = {
            'timestamp': iso_time,
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
            'line': record.lineno,
        }

        # Add extra fields if present
        if hasattr(record, 'tokens'):
            log_data['tokens'] = record.tokens
        if hasattr(record, 'cost_usd'):
            log_data['cost_usd'] = record.cost_usd
        if hasattr(record, 'event'):
            log_data['event'] = record.event
        if hasattr(record, 'model'):
            log_data['model'] = record.model

        # Add any additional custom fields from record.__dict__
        for key, value in record.__dict__.items():
            if key not in ['args', 'exc_info', 'exc_text', 'stack_info', 'lineno',
                          'funcName', 'created', 'msecs', 'relativeCreated',
                          'levelname', 'levelno', 'pathname', 'filename',
                          'module', 'name', 'thread', 'threadName', 'processName',
                          'process', 'message', 'msg', 'tokens', 'cost_usd', 'event', 'model']:
                if not key.startswith('_'):
                    log_data[key] = value

        return json.dumps(log_data)


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO
) -> logging.Logger:
    """
    Set up and configure a logger with the structured formatter.

    Args:
        name: Name of the logger
        log_file: Path to the log file (optional)
        level: Log level

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers if any
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create formatter
    formatter = StructuredFormatter()

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Create file handler if log_file is provided
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def log_openai_usage(
    logger: logging.Logger,
    event: str,
    model: str,
    tokens: int,
    cost_usd: float,
    **kwargs: Any
) -> None:
    """
    Log OpenAI API usage with tokens and cost.

    Args:
        logger: Logger instance
        event: Event description
        model: OpenAI model name
        tokens: Number of tokens used
        cost_usd: Cost in USD
        **kwargs: Additional fields to log
    """
    extra = {
        'event': event,
        'model': model,
        'tokens': tokens,
        'cost_usd': cost_usd,
        **kwargs
    }

    # Create a LogRecord with extra fields
    logger.info(f"{event}: {tokens} tokens, ${cost_usd:.6f}", extra=extra)
