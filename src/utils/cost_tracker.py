from typing import Dict, Optional
import logging

# Token price per 1000 tokens (estimated as of 2025)
MODEL_PRICING = {
    "gpt-4.1": {
        "input": 0.01,  # $0.01 per 1K input tokens
        "output": 0.03,  # $0.03 per 1K output tokens
    },
    "gpt-4o": {
        "input": 0.001,  # $0.001 per 1K input tokens
        "output": 0.002,  # $0.002 per 1K output tokens
    },
    # Default for any model not explicitly listed
    "default": {
        "input": 0.01,  # Conservative estimate
        "output": 0.03,
    }
}


class CostTracker:
    """Tracks token usage and cost across API calls."""

    def __init__(self, cost_ceiling: float, logger: logging.Logger):
        """Initialize the cost tracker.

        Args:
            cost_ceiling: Maximum allowed cost in USD
            logger: Logger instance
        """
        self.cost_ceiling = cost_ceiling
        self.logger = logger
        self.total_cost_usd = 0.0
        self.token_counts: Dict[str, int] = {}
        self.cost_by_model: Dict[str, float] = {}

    def add_usage(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Track token usage and cost for an API call.

        Args:
            model: The model used for the API call
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost of this API call in USD
        """
        # Get pricing for this model or use default
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])

        # Calculate cost
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        total_cost = input_cost + output_cost

        # Update trackers
        self.total_cost_usd += total_cost

        if model not in self.token_counts:
            self.token_counts[model] = 0
            self.cost_by_model[model] = 0.0

        self.token_counts[model] += input_tokens + output_tokens
        self.cost_by_model[model] += total_cost

        # Log the usage
        self.logger.info(
            f"API call cost: ${total_cost:.6f} | Total: ${self.total_cost_usd:.6f} / ${self.cost_ceiling:.2f}",
            extra={"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens}
        )

        return total_cost

    def would_exceed_ceiling(self, model: str, estimated_tokens: int) -> bool:
        """Check if a proposed API call would exceed the cost ceiling.

        Args:
            model: The model to be used
            estimated_tokens: Estimated total tokens for the call

        Returns:
            True if the call would likely exceed the ceiling, False otherwise
        """
        pricing = MODEL_PRICING.get(model, MODEL_PRICING["default"])

        # Assume a conservative 50/50 split between input and output tokens
        est_input_tokens = estimated_tokens / 2
        est_output_tokens = estimated_tokens / 2

        est_cost = ((est_input_tokens / 1000) * pricing["input"]) + ((est_output_tokens / 1000) * pricing["output"])

        return (self.total_cost_usd + est_cost) >= self.cost_ceiling

    def get_price_per_1k_tokens(self, model: str) -> Dict[str, float]:
        """Get the price per 1K tokens for a specific model.

        Args:
            model: The model name

        Returns:
            Dictionary with input and output token pricing
        """
        return MODEL_PRICING.get(model, MODEL_PRICING["default"])

    def generate_cost_report(self) -> Dict:
        """Generate a summary report of costs and token usage.

        Returns:
            Dictionary with cost and token usage data
        """
        return {
            "total_cost_usd": self.total_cost_usd,
            "cost_ceiling": self.cost_ceiling,
            "percentage_used": (self.total_cost_usd / self.cost_ceiling) * 100,
            "token_counts": self.token_counts,
            "cost_by_model": self.cost_by_model
        }


def estimate_tokens_from_string(text: str) -> int:
    """Estimate the number of tokens in a string.

    This is a rough approximation. For exact counts, use the tokenizer.

    Args:
        text: The text to estimate tokens for

    Returns:
        Estimated token count
    """
    # Simple approximation: 1 token ≈ 4 characters
    return len(text) // 4
