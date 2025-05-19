"""
Logging utilities for the Awesome-List Researcher.
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional


class ISO8601Formatter(logging.Formatter):
    """
    Log formatter that includes ISO 8601 timestamps.
    """
    def formatTime(self, record, datefmt=None):
        """
        Format time in ISO 8601 format.
        """
        return datetime.fromtimestamp(record.created).isoformat()


class APICallLogRecord:
    """
    Log record for API calls with full prompt and completion text.
    """
    def __init__(
        self,
        agent_id: str,
        model: str,
        prompt: str,
        completion: str,
        tokens: int,
        cost_usd: float,
        latency: float
    ):
        """
        Initialize a log record for an API call.

        Args:
            agent_id: ID of the agent making the call
            model: Model used for the call
            prompt: Full prompt text
            completion: Full completion text
            tokens: Total tokens used
            cost_usd: Cost in USD
            latency: Latency in seconds
        """
        self.timestamp = datetime.now().isoformat()
        self.agent_id = agent_id
        self.model = model
        self.prompt = prompt
        self.completion = completion
        self.tokens = tokens
        self.cost_usd = cost_usd
        self.latency = latency

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary.

        Returns:
            Dictionary representation of the log record
        """
        return {
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "model": self.model,
            "tokens": self.tokens,
            "cost_usd": self.cost_usd,
            "latency": self.latency,
            "prompt": self.prompt,
            "completion": self.completion
        }

    def to_json(self, indent: Optional[int] = None) -> str:
        """
        Convert to JSON string.

        Args:
            indent: JSON indentation level

        Returns:
            JSON string representation of the log record
        """
        return json.dumps(self.to_dict(), indent=indent)


def setup_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """
    Set up a logger with ISO 8601 timestamps and console/file handlers.

    Args:
        name: Logger name
        log_file: Path to log file (optional)

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Create ISO 8601 formatter
    formatter = ISO8601Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    )

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Create file handler if log_file is provided
    if log_file:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

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
