import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

class CustomFormatter(logging.Formatter):
    """Custom formatter that includes ISO 8601 timestamps and structured data."""

    def format(self, record: logging.LogRecord) -> str:
        iso_time = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()

        # Extract additional fields if present
        extras = {}
        for key, value in record.__dict__.items():
            # Safe way to check for non-standard attributes
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                          'filename', 'module', 'exc_info', 'exc_text', 'lineno',
                          'funcName', 'created', 'asctime', 'msecs', 'relativeCreated',
                          'thread', 'threadName', 'processName', 'process']:
                extras[key] = value

        # Format the message
        if record.levelno == logging.INFO and extras:
            # For info logs with extras, use a structured format
            base_message = super().format(record)
            log_data = {
                "timestamp": iso_time,
                "level": record.levelname,
                "message": base_message,
                **extras
            }
            # Special handling for prompt and completion to avoid nested JSON issues
            if 'prompt' in log_data and isinstance(log_data['prompt'], str):
                try:
                    log_data['prompt'] = json.loads(log_data['prompt'])
                except json.JSONDecodeError:
                    pass

            return json.dumps(log_data)
        else:
            # For other logs, use a more human-readable format
            return f"{iso_time} | {record.levelname:<8} | {super().format(record)}"


def setup_logger(output_dir: str) -> logging.Logger:
    """Setup a logger with the required configuration.

    Args:
        output_dir: Directory to store log files

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("awesome-researcher")
    logger.setLevel(logging.INFO)

    # Clear any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)

    # Create file handler
    os.makedirs(output_dir, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(output_dir, "agent.log"))
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(CustomFormatter())
    logger.addHandler(file_handler)

    return logger


def log_api_call(
    logger: logging.Logger,
    agent: str,
    event: str,
    model: str,
    tokens: int,
    cost_usd: float,
    prompt: Any,
    completion: str,
) -> None:
    """Log an API call with all required fields.

    Args:
        logger: Logger instance
        agent: Name of the agent making the call
        event: Event type (tool_start, tool_finish, etc.)
        model: Model used for the call
        tokens: Number of tokens used
        cost_usd: Cost in USD
        prompt: Prompt sent to the API
        completion: Response from the API
    """
    logger.info(
        f"{event}",
        extra={
            "agent": agent,
            "event": event,
            "model": model,
            "tokens": tokens,
            "cost_usd": cost_usd,
            "prompt": json.dumps(prompt) if not isinstance(prompt, str) else prompt,
            "completion": completion
        }
    )
