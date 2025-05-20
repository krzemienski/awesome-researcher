"""
Context Store for managing context data between operations.

This module implements a context store to share data between different
components of the Awesome-List Researcher.
"""

import logging
import json
import os
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class ContextStore:
    """
    Context Store for sharing data between components.

    This class provides a central store for context data that can be
    shared between different components of the application.
    """

    def __init__(self):
        """Initialize the context store."""
        self._context: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> bool:
        """
        Set a value in the context store.

        Args:
            key: Context key
            value: Value to store

        Returns:
            True if successful, False otherwise
        """
        logger.debug(f"Setting context value for key: {key}")
        try:
            self._context[key] = value
            return True
        except Exception as e:
            logger.error(f"Failed to set context value for {key}: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the context store.

        Args:
            key: Context key
            default: Default value to return if key not found

        Returns:
            Stored value if found, default otherwise
        """
        logger.debug(f"Getting context value for key: {key}")
        return self._context.get(key, default)

    def has(self, key: str) -> bool:
        """
        Check if a key exists in the context store.

        Args:
            key: Context key

        Returns:
            True if key exists, False otherwise
        """
        return key in self._context

    def delete(self, key: str) -> bool:
        """
        Delete a key from the context store.

        Args:
            key: Context key to delete

        Returns:
            True if successful, False if key not found
        """
        if key in self._context:
            del self._context[key]
            logger.debug(f"Deleted context key: {key}")
            return True
        return False

    def keys(self) -> List[str]:
        """
        Get all keys in the context store.

        Returns:
            List of all keys in the context store
        """
        return list(self._context.keys())

    def clear(self) -> None:
        """Clear all data from the context store."""
        self._context = {}
        logger.debug("Cleared context store")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the context store to a dictionary.

        Returns:
            Dictionary copy of the context store
        """
        return self._context.copy()

    def load_from_dict(self, data: Dict[str, Any]) -> bool:
        """
        Load context data from a dictionary.

        Args:
            data: Dictionary containing context data

        Returns:
            True if successful, False otherwise
        """
        try:
            self._context.update(data)
            logger.debug(f"Loaded {len(data)} keys into context store")
            return True
        except Exception as e:
            logger.error(f"Failed to load context data: {e}")
            return False

    def save_to_file(self, file_path: str) -> bool:
        """
        Save the context store to a JSON file.

        Args:
            file_path: Path to save the context data

        Returns:
            True if successful, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "w") as f:
                json.dump(self._context, f, indent=2)

            logger.info(f"Saved context store to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save context store: {e}")
            return False

    def load_from_file(self, file_path: str) -> bool:
        """
        Load the context store from a JSON file.

        Args:
            file_path: Path to load the context data from

        Returns:
            True if successful, False otherwise
        """
        try:
            if not os.path.exists(file_path):
                logger.warning(f"Context file not found: {file_path}")
                return False

            with open(file_path, "r") as f:
                data = json.load(f)

            self.load_from_dict(data)
            logger.info(f"Loaded context store from {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load context store: {e}")
            return False

# Create a singleton instance
context_store = ContextStore()

def get_context_store() -> ContextStore:
    """
    Get the singleton context store instance.

    Returns:
        The context store singleton
    """
    return context_store
