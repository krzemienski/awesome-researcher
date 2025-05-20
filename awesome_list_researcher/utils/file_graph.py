"""
File Graph implementation for file relationship analysis.

This module provides tools to analyze file dependencies and relationships.
"""

import os
import logging
import json
from typing import Dict, List, Set, Any, Optional

logger = logging.getLogger(__name__)

class FileGraph:
    """
    File Graph for analyzing file relationship structure.

    This class builds a graph of file relationships and dependencies.
    """

    def __init__(self, root_path: str = "."):
        """
        Initialize the file graph.

        Args:
            root_path: Root directory to analyze
        """
        self.root_path = root_path
        self.files: Dict[str, Dict[str, Any]] = {}
        self.file_extensions: Set[str] = set()
        self.total_size = 0
        self.total_files = 0

    def build_graph(self) -> Dict[str, Any]:
        """
        Build the file graph by analyzing the file structure.

        Returns:
            Dictionary containing the file graph data
        """
        logger.info(f"Building file graph from {self.root_path}")

        # Reset data
        self.files = {}
        self.file_extensions = set()
        self.total_size = 0
        self.total_files = 0

        # Walk the directory tree
        for root, dirs, files in os.walk(self.root_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for file in files:
                # Skip hidden files
                if file.startswith("."):
                    continue

                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.root_path)

                # Skip directories in .gitignore (simplified approach)
                if "__pycache__" in rel_path or "venv" in rel_path or "env" in rel_path:
                    continue

                try:
                    file_stat = os.stat(file_path)
                    file_size = file_stat.st_size
                    file_mtime = file_stat.st_mtime

                    # Extract file extension
                    _, ext = os.path.splitext(file)
                    ext = ext.lower()
                    if ext:
                        self.file_extensions.add(ext[1:])  # Remove the leading dot

                    # Update file information
                    self.files[rel_path] = {
                        "path": rel_path,
                        "size": file_size,
                        "modified": file_mtime,
                        "ext": ext[1:] if ext else "",
                        "dir": os.path.dirname(rel_path) or "."
                    }

                    # Update totals
                    self.total_size += file_size
                    self.total_files += 1

                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")

        logger.info(f"File graph built with {self.total_files} files, total size: {self.total_size} bytes")
        return self.to_dict()

    def get_files_by_extension(self, ext: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all files with a specific extension.

        Args:
            ext: File extension to filter by (without the leading dot)

        Returns:
            Dictionary of files with the specified extension
        """
        result = {}
        for path, file_info in self.files.items():
            if file_info["ext"] == ext:
                result[path] = file_info
        return result

    def get_files_by_directory(self, directory: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all files in a specific directory.

        Args:
            directory: Directory path (relative to root_path)

        Returns:
            Dictionary of files in the specified directory
        """
        result = {}
        for path, file_info in self.files.items():
            if file_info["dir"] == directory or path.startswith(f"{directory}/"):
                result[path] = file_info
        return result

    def get_largest_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the largest files in the codebase.

        Args:
            limit: Maximum number of files to return

        Returns:
            List of file information dictionaries, sorted by size (largest first)
        """
        sorted_files = sorted(self.files.values(), key=lambda x: x["size"], reverse=True)
        return sorted_files[:limit]

    def get_extension_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics about file extensions.

        Returns:
            Dictionary with extension stats
        """
        stats = {}

        for ext in self.file_extensions:
            ext_files = self.get_files_by_extension(ext)

            # Calculate total size for this extension
            ext_size = sum(file_info["size"] for file_info in ext_files.values())

            stats[ext] = {
                "count": len(ext_files),
                "total_size": ext_size,
                "percentage": (len(ext_files) / self.total_files * 100) if self.total_files > 0 else 0
            }

        return stats

    def get_directory_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics about directories.

        Returns:
            Dictionary with directory stats
        """
        stats = {}

        # Get all unique directories
        directories = set(file_info["dir"] for file_info in self.files.values())

        for directory in directories:
            dir_files = self.get_files_by_directory(directory)

            # Calculate total size for this directory
            dir_size = sum(file_info["size"] for file_info in dir_files.values())

            stats[directory] = {
                "count": len(dir_files),
                "total_size": dir_size,
                "percentage": (len(dir_files) / self.total_files * 100) if self.total_files > 0 else 0
            }

        return stats

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the file graph to a dictionary representation.

        Returns:
            Dictionary representation of the file graph
        """
        return {
            "files": self.files,
            "extensions": list(self.file_extensions),
            "extension_stats": self.get_extension_stats(),
            "directory_stats": self.get_directory_stats(),
            "total_files": self.total_files,
            "total_size": self.total_size,
            "largest_files": self.get_largest_files()
        }

    def save_to_file(self, output_path: str = "docs/file_graph.json"):
        """
        Save the file graph to a JSON file.

        Args:
            output_path: Path to save the file graph
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)

            logger.info(f"File graph saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save file graph: {e}")

# Factory function to create a file graph instance
def create_file_graph(root_path: str = ".") -> FileGraph:
    """
    Create and build a file graph for the codebase.

    Args:
        root_path: Root directory to analyze

    Returns:
        Built file graph instance
    """
    graph = FileGraph(root_path)
    graph.build_graph()
    return graph
