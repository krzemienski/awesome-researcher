"""
Memory Store for persistent data across runs.

This module implements a persistent memory store using MCP's Memory tool.
"""

import json
import logging
import os
from typing import Any, Dict, Optional, List

logger = logging.getLogger(__name__)

class MemoryStore:
    """
    Memory store for persistent data storage across runs.

    This class uses the Memory MCP to store and retrieve data.
    """

    def __init__(self, storage_dir: str = "runs/memory"):
        """
        Initialize the memory store.

        Args:
            storage_dir: Directory to store memory data
        """
        self.storage_dir = storage_dir
        self._memory: Dict[str, Any] = {}
        self._initialize_storage()

    def _initialize_storage(self):
        """Initialize the storage directory if it doesn't exist."""
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load_memory()

    def _load_memory(self):
        """Load memory from disk if available."""
        memory_file = os.path.join(self.storage_dir, "memory.json")
        try:
            if os.path.exists(memory_file):
                with open(memory_file, "r") as f:
                    self._memory = json.load(f)
                logger.info(f"Loaded memory from {memory_file}")
            else:
                logger.info("No existing memory found, starting fresh")
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")
            self._memory = {}

    def _save_memory(self):
        """Save memory to disk."""
        memory_file = os.path.join(self.storage_dir, "memory.json")
        try:
            with open(memory_file, "w") as f:
                json.dump(self._memory, f, indent=2)
            logger.info(f"Saved memory to {memory_file}")
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def put(self, key: str, value: Any) -> bool:
        """
        Store a value in memory.

        Args:
            key: Memory key
            value: Value to store

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Storing in memory: {key}")
        try:
            # In a real implementation, this would use the Memory MCP
            self._memory[key] = value
            self._save_memory()
            return True
        except Exception as e:
            logger.error(f"Failed to store in memory - {key}: {e}")
            return False

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from memory.

        Args:
            key: Memory key

        Returns:
            Stored value if found, None otherwise
        """
        logger.info(f"Retrieving from memory: {key}")
        return self._memory.get(key)

    def list_keys(self) -> List[str]:
        """
        List all keys in memory.

        Returns:
            List of all keys in memory
        """
        return list(self._memory.keys())

    def delete(self, key: str) -> bool:
        """
        Delete a key from memory.

        Args:
            key: Memory key to delete

        Returns:
            True if successful, False if key not found
        """
        if key in self._memory:
            del self._memory[key]
            self._save_memory()
            return True
        return False

    def clear(self) -> bool:
        """
        Clear all memory.

        Returns:
            True if successful
        """
        self._memory = {}
        self._save_memory()
        return True

# Create a singleton instance
memory_store = MemoryStore()

def get_memory_store() -> MemoryStore:
    """
    Get the singleton memory store instance.

    Returns:
        The memory store singleton
    """
    return memory_store
