"""
Cost guard utilities for tracking and limiting OpenAI API costs.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

# Model prices per 1K tokens (as of 2023)
MODEL_PRICES = {
    # GPT-4 Models
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-4-32k": {"input": 0.06, "output": 0.12},

    # GPT-3.5 Models
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "gpt-3.5-turbo-16k": {"input": 0.001, "output": 0.002},

    # Claude Models (approximations)
    "claude-3-opus": {"input": 0.015, "output": 0.075},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "o3": {"input": 0.015, "output": 0.075},  # Alias for claude-3-opus

    # Default for unknown models
    "gpt-4.1-mini": {"input": 0.0015, "output": 0.006},  # Approximation
}


@dataclass
class CostGuard:
    """
    Tracks and limits OpenAI API costs.
    """
    cost_ceiling: float
    logger: logging.Logger
    total_cost_usd: float = 0.0
    total_tokens: int = 0

    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: Optional[int] = None
    ) -> float:
        """
        Estimate the cost of an API call.

        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens (if None, estimated as input_tokens/2)

        Returns:
            Estimated cost in USD
        """
        model_prices = MODEL_PRICES.get(model.lower(), MODEL_PRICES["gpt-3.5-turbo"])

        if output_tokens is None:
            output_tokens = input_tokens // 2  # Rough estimation

        input_cost = (input_tokens / 1000) * model_prices["input"]
        output_cost = (output_tokens / 1000) * model_prices["output"]

        return input_cost + output_cost

    def would_exceed_ceiling(
        self,
        model: str,
        input_tokens: int,
        output_tokens: Optional[int] = None
    ) -> bool:
        """
        Check if an API call would exceed the cost ceiling.

        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            True if the call would exceed the ceiling
        """
        est_cost = self.estimate_cost(model, input_tokens, output_tokens)
        return (self.total_cost_usd + est_cost) > self.cost_ceiling

    def update_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        event: str
    ) -> None:
        """
        Update usage after an API call.

        Args:
            model: Model name
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            event: Description of the API call
        """
        model_prices = MODEL_PRICES.get(model.lower(), MODEL_PRICES["gpt-3.5-turbo"])

        input_cost = (input_tokens / 1000) * model_prices["input"]
        output_cost = (output_tokens / 1000) * model_prices["output"]

        total_cost = input_cost + output_cost
        total_tokens = input_tokens + output_tokens

        self.total_cost_usd += total_cost
        self.total_tokens += total_tokens

        # Log the usage
        self.logger.info(
            f"{event}: {total_tokens} tokens, ${total_cost:.6f}",
            extra={
                "event": event,
                "model": model,
                "tokens": total_tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": total_cost,
                "accumulated_cost_usd": self.total_cost_usd,
                "accumulated_tokens": self.total_tokens
            }
        )

        # Check if we're nearing the cost ceiling
        if self.total_cost_usd > self.cost_ceiling * 0.8:
            self.logger.warning(
                f"Approaching cost ceiling: ${self.total_cost_usd:.2f} / ${self.cost_ceiling:.2f}",
                extra={"event": "cost_warning", "cost_usd": self.total_cost_usd}
            )

        # Check if we've exceeded the cost ceiling
        if self.total_cost_usd > self.cost_ceiling:
            self.logger.error(
                f"Cost ceiling exceeded: ${self.total_cost_usd:.2f} > ${self.cost_ceiling:.2f}",
                extra={"event": "cost_ceiling_exceeded", "cost_usd": self.total_cost_usd}
            )
