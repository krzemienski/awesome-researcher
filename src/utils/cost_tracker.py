from typing import Dict, Optional, Any
import logging
import json
import os

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
    },
    # GPT-3.5 Turbo pricing (fallback)
    "gpt-3.5-turbo": {
        "input": 0.0005,
        "output": 0.0015
    }
}

# Default pricing for unknown models (set to GPT-3.5 rates)
DEFAULT_PRICING = {
    "input": 0.0005,
    "output": 0.0015
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
        self.total_tokens = 0
        self.model_usage: Dict[str, Dict[str, Any]] = {}

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
        if model in MODEL_PRICING:
            pricing = MODEL_PRICING[model]
        else:
            pricing = DEFAULT_PRICING
            self.logger.warning(f"Unknown model {model}, using default pricing")

        # Calculate cost
        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        total_cost = input_cost + output_cost

        # Update trackers
        self.total_cost_usd += total_cost
        self.total_tokens += input_tokens + output_tokens

        if model not in self.token_counts:
            self.token_counts[model] = 0
            self.cost_by_model[model] = 0.0

        self.token_counts[model] += input_tokens + output_tokens
        self.cost_by_model[model] += total_cost

        # Update model-specific usage
        if model not in self.model_usage:
            self.model_usage[model] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0
            }

        self.model_usage[model]["input_tokens"] += input_tokens
        self.model_usage[model]["output_tokens"] += output_tokens
        self.model_usage[model]["cost"] += total_cost

        # Log the usage
        self.logger.info(
            f"API call cost: ${total_cost:.6f} | Total: ${self.total_cost_usd:.6f} / ${self.cost_ceiling:.2f}",
            extra={"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens}
        )

        return total_cost

    def get_cost_for_tokens(self, model: str, total_tokens: int) -> float:
        """Calculate the cost for tokens without adding to the total.

        Args:
            model: Model name
            total_tokens: Total number of tokens

        Returns:
            Estimated cost in USD
        """
        # Get pricing for this model (assuming 50/50 split between input/output)
        if model in MODEL_PRICING:
            pricing = MODEL_PRICING[model]
        else:
            pricing = DEFAULT_PRICING

        # Calculate cost (approximation assuming 50/50 split)
        input_tokens = total_tokens // 2
        output_tokens = total_tokens - input_tokens
        input_cost = (input_tokens / 1000.0) * pricing["input"]
        output_cost = (output_tokens / 1000.0) * pricing["output"]
        total_cost = input_cost + output_cost

        return total_cost

    def would_exceed_ceiling(self, model: str, estimated_tokens: int) -> bool:
        """Check if a proposed API call would exceed the cost ceiling.

        Args:
            model: The model to be used
            estimated_tokens: Estimated total tokens for the call

        Returns:
            True if the call would likely exceed the ceiling, False otherwise
        """
        # Get pricing for this model (assuming 50/50 split between input/output)
        if model in MODEL_PRICING:
            pricing = MODEL_PRICING[model]
        else:
            pricing = DEFAULT_PRICING

        # Calculate estimated cost (approximation assuming 50/50 split)
        input_tokens = estimated_tokens // 2
        output_tokens = estimated_tokens - input_tokens
        input_cost = (input_tokens / 1000.0) * pricing["input"]
        output_cost = (output_tokens / 1000.0) * pricing["output"]
        estimated_cost = input_cost + output_cost

        # Check if this would exceed the ceiling
        return (self.total_cost_usd + estimated_cost) >= self.cost_ceiling

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
            "cost_by_model": self.cost_by_model,
            "total_tokens": self.total_tokens,
            "models": self.model_usage
        }

    def save_cost_report(self, output_dir: str) -> str:
        """Save the cost report to a JSON file.

        Args:
            output_dir: Directory to save the report in

        Returns:
            Path to the saved JSON file
        """
        output_path = os.path.join(output_dir, "cost_summary.json")
        report = self.generate_cost_report()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved cost report to {output_path}")
        return output_path


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
