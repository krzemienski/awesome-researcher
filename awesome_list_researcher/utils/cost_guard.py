"""
Cost monitoring and limiting for OpenAI API calls.
"""

import logging
from typing import Dict, Optional

from openai.types.completion import Completion
from openai.types.chat import ChatCompletion


class CostGuard:
    """
    Guard for monitoring and limiting API costs.
    """

    # Pricing per 1000 tokens (input/output) for various models
    # These rates may change, so they should be updated as needed
    PRICING = {
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-4-32k": {"input": 0.06, "output": 0.12},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-4.1-mini": {"input": 0.01, "output": 0.03},
        "gpt-4.1": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
        "o3": {"input": 0.01, "output": 0.03},
    }

    def __init__(self, cost_ceiling: float, logger: logging.Logger):
        """
        Initialize the cost guard.

        Args:
            cost_ceiling: Maximum allowed cost in USD
            logger: Logger instance
        """
        self.cost_ceiling = cost_ceiling
        self.logger = logger
        self.total_cost_usd = 0.0
        self.total_tokens = 0

    def _get_rates(self, model: str) -> Dict[str, float]:
        """
        Get the pricing rates for a model.

        Args:
            model: Model name

        Returns:
            Dictionary with input and output rates
        """
        # Normalize model name
        model_base = model.split("-")[0].lower()

        if model in self.PRICING:
            return self.PRICING[model]
        elif model_base == "gpt4" or model_base == "gpt-4":
            return self.PRICING["gpt-4"]
        elif model_base == "gpt3" or model_base == "gpt-3":
            return self.PRICING["gpt-3.5-turbo"]
        else:
            # Default to gpt-3.5-turbo rates if unknown
            self.logger.warning(f"Unknown model: {model}, using default pricing")
            return self.PRICING["gpt-3.5-turbo"]

    def _calculate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """
        Calculate the cost of an API call.

        Args:
            model: Model name
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Number of tokens in the completion

        Returns:
            Cost in USD
        """
        rates = self._get_rates(model)

        input_cost = (prompt_tokens / 1000) * rates["input"]
        output_cost = (completion_tokens / 1000) * rates["output"]

        return input_cost + output_cost

    def update_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """
        Update the total cost with a new API call.

        Args:
            model: Model name
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Number of tokens in the completion

        Returns:
            Cost of the current call in USD
        """
        cost = self._calculate_cost(model, prompt_tokens, completion_tokens)
        self.total_cost_usd += cost
        self.total_tokens += prompt_tokens + completion_tokens

        self.logger.info(
            f"API call: {prompt_tokens} prompt tokens, {completion_tokens} completion tokens, "
            f"${cost:.4f}, total: ${self.total_cost_usd:.4f}"
        )

        return cost

    def update_from_completion(
        self,
        completion: ChatCompletion,
        model: Optional[str] = None
    ) -> float:
        """
        Update the total cost from a completion object.

        Args:
            completion: ChatCompletion or Completion object
            model: Model name (optional, will use completion.model if not provided)

        Returns:
            Cost of the current call in USD
        """
        if model is None:
            model = completion.model

        usage = completion.usage

        return self.update_cost(
            model,
            usage.prompt_tokens,
            usage.completion_tokens
        )

    def would_exceed_ceiling(
        self,
        model: str,
        estimated_prompt_tokens: int,
        estimated_completion_tokens: int
    ) -> bool:
        """
        Check if a potential API call would exceed the cost ceiling.

        Args:
            model: Model name
            estimated_prompt_tokens: Estimated number of tokens in the prompt
            estimated_completion_tokens: Estimated number of tokens in the completion

        Returns:
            True if the call would exceed the ceiling, False otherwise
        """
        estimated_cost = self._calculate_cost(
            model,
            estimated_prompt_tokens,
            estimated_completion_tokens
        )

        return (self.total_cost_usd + estimated_cost) > self.cost_ceiling
