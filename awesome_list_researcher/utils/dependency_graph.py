"""
Dependency Graph implementation for tracking code relationships.

This module provides tools to analyze and visualize code dependencies.
"""

import os
import logging
import networkx as nx
import matplotlib.pyplot as plt
from typing import Dict, List, Set, Optional, Tuple, Any

logger = logging.getLogger(__name__)

class DependencyGraph:
    """
    Dependency Graph for analyzing code structure and relationships.

    This class builds a graph of module dependencies to help understand
    the codebase structure.
    """

    def __init__(self, root_path: str = "awesome_list_researcher"):
        """
        Initialize the dependency graph.

        Args:
            root_path: Root directory to analyze
        """
        self.root_path = root_path
        self.graph = nx.DiGraph()
        self.module_paths: Dict[str, str] = {}

    def build_graph(self) -> nx.DiGraph:
        """
        Build the dependency graph by analyzing Python files.

        Returns:
            The constructed directed graph
        """
        logger.info(f"Building dependency graph from {self.root_path}")

        # First pass: collect all module paths
        self._collect_module_paths()

        # Second pass: analyze imports and build the graph
        for module_name, module_path in self.module_paths.items():
            imports = self._extract_imports(module_path)

            # Add the module as a node if not already present
            if not self.graph.has_node(module_name):
                self.graph.add_node(module_name)

            # Add edges for each import
            for imported_module in imports:
                # Check if the imported module is in our codebase
                for known_module in self.module_paths:
                    # Handle both direct imports and from ... import
                    if imported_module == known_module or imported_module.startswith(f"{known_module}."):
                        if not self.graph.has_node(known_module):
                            self.graph.add_node(known_module)
                        self.graph.add_edge(module_name, known_module)

        logger.info(f"Dependency graph built with {self.graph.number_of_nodes()} nodes and {self.graph.number_of_edges()} edges")
        return self.graph

    def _collect_module_paths(self):
        """Collect all Python module paths in the codebase."""
        for root, _, files in os.walk(self.root_path):
            for file in files:
                if not file.endswith(".py"):
                    continue

                # Skip __pycache__ directories
                if "__pycache__" in root:
                    continue

                file_path = os.path.join(root, file)

                # Convert file path to module name
                rel_path = os.path.relpath(file_path, start=os.path.dirname(self.root_path))
                module_name = os.path.splitext(rel_path.replace(os.path.sep, "."))[0]

                # Skip __init__.py files for directory modules
                if module_name.endswith(".__init__"):
                    module_name = module_name[:-9]

                self.module_paths[module_name] = file_path

    def _extract_imports(self, file_path: str) -> List[str]:
        """
        Extract imports from a Python file.

        Args:
            file_path: Path to the Python file

        Returns:
            List of imported modules
        """
        imports = []
        try:
            with open(file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("import ") or line.startswith("from "):
                        # Basic import extraction
                        if line.startswith("import "):
                            modules = line[7:].split(",")
                            for module in modules:
                                module = module.split(" as ")[0].strip()
                                imports.append(module)
                        else:
                            parts = line.split(" import ")
                            if len(parts) > 1:
                                module = parts[0][5:].strip()
                                imports.append(module)
        except Exception as e:
            logger.error(f"Failed to extract imports from {file_path}: {e}")

        return imports

    def get_dependencies(self, module_name: str) -> List[str]:
        """
        Get all dependencies of a module.

        Args:
            module_name: Name of the module

        Returns:
            List of modules that this module depends on
        """
        if not self.graph.has_node(module_name):
            return []

        return list(self.graph.successors(module_name))

    def get_dependents(self, module_name: str) -> List[str]:
        """
        Get all modules that depend on this module.

        Args:
            module_name: Name of the module

        Returns:
            List of modules that depend on this module
        """
        if not self.graph.has_node(module_name):
            return []

        return list(self.graph.predecessors(module_name))

    def identify_cycles(self) -> List[List[str]]:
        """
        Identify circular dependencies in the graph.

        Returns:
            List of cycles (each cycle is a list of module names)
        """
        try:
            cycles = list(nx.simple_cycles(self.graph))
            return cycles
        except Exception as e:
            logger.error(f"Failed to identify cycles: {e}")
            return []

    def visualize(self, output_path: str = "docs/dependency_graph.png"):
        """
        Generate a visualization of the dependency graph.

        Args:
            output_path: Path to save the visualization
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            plt.figure(figsize=(12, 10))

            # Use spring layout for better visualization
            pos = nx.spring_layout(self.graph, k=0.15, iterations=20)

            nx.draw(
                self.graph,
                pos,
                with_labels=True,
                node_color="skyblue",
                node_size=1500,
                font_size=8,
                font_weight="bold",
                arrows=True,
                arrowsize=15,
            )

            plt.title("Code Dependency Graph")
            plt.tight_layout()
            plt.savefig(output_path)
            plt.close()

            logger.info(f"Dependency graph visualization saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to visualize dependency graph: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the graph to a dictionary representation.

        Returns:
            Dictionary representation of the graph
        """
        result = {
            "nodes": list(self.graph.nodes()),
            "edges": list(self.graph.edges()),
            "module_paths": self.module_paths
        }
        return result

# Factory function to create a dependency graph instance
def create_dependency_graph(root_path: str = "awesome_list_researcher") -> DependencyGraph:
    """
    Create and build a dependency graph for the codebase.

    Args:
        root_path: Root directory to analyze

    Returns:
        Built dependency graph instance
    """
    graph = DependencyGraph(root_path)
    graph.build_graph()
    return graph
