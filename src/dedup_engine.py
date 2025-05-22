import json
import logging
import os
from typing import Dict, List, Set, Tuple, Any, Optional
from urllib.parse import urlparse
import re
from pathlib import Path

import Levenshtein
from sentence_transformers import SentenceTransformer
import numpy as np

from src.utils.cost_tracker import CostTracker
import src.logger as log

class DedupEngine:
    """Four-layer deduplication engine for filtering candidate resources."""

    def __init__(
        self,
        logger: logging.Logger,
        output_dir: str,
        cost_tracker: CostTracker,
        original_urls: Set[str],
        duplicate_threshold: float = 0.3,
        video_categories: Optional[Set[str]] = None,
    ):
        """Initialize the deduplication engine.

        Args:
            logger: Logger instance
            output_dir: Directory to store output files
            cost_tracker: Cost tracker instance
            original_urls: Set of URLs from the original list
            duplicate_threshold: Maximum allowed duplicate ratio (0.0-1.0)
            video_categories: Set of video-specific categories
        """
        self.logger = logger
        self.output_dir = output_dir
        self.cost_tracker = cost_tracker
        self.original_urls = original_urls
        self.duplicate_threshold = duplicate_threshold
        self.video_categories = video_categories or set()
        self.sentence_transformer = None  # Lazy-loaded
        self.cost_timer = log.CostTimer()
        self.run_dir = Path(output_dir).parent

    def deduplicate_resources(self, candidates: List[Dict]) -> List[Dict]:
        """Apply four layers of deduplication to candidate resources.

        Args:
            candidates: List of candidate resources

        Returns:
            List of deduplicated resources

        Raises:
            ValueError: If the duplicate ratio exceeds the threshold
        """
        # Use context manager for structured logging
        with log.log_phase("deduplication", self.run_dir, self.cost_timer):
            self.logger.info(f"Starting deduplication of {len(candidates)} candidate resources")

            # Skip deduplication if there are no candidates
            if not candidates:
                return []

            # Track the different layers of deduplication
            dedup_stats = {
                "candidates": len(candidates),
                "case_filtered": 0,
                "fuzzy_filtered": 0,
                "domain_filtered": 0,
                "semantic_filtered": 0,
                "original_filtered": 0,
                "final": 0,
            }

            # Layer 1: Case-insensitive title comparison
            case_deduped, case_duplicates = self._dedup_by_case(candidates)
            dedup_stats["case_filtered"] = len(case_duplicates)
            self.logger.info(f"Case deduplication removed {len(case_duplicates)} resources")

            # Layer 2: Levenshtein distance for fuzzy matching
            fuzzy_deduped, fuzzy_duplicates = self._dedup_by_levenshtein(case_deduped)
            dedup_stats["fuzzy_filtered"] = len(fuzzy_duplicates)
            self.logger.info(f"Fuzzy deduplication removed {len(fuzzy_duplicates)} resources")

            # Layer 3: Canonical URL matching and hostname + title matching
            domain_deduped, domain_duplicates = self._dedup_by_domain_and_title(fuzzy_deduped)
            dedup_stats["domain_filtered"] = len(domain_duplicates)
            self.logger.info(f"Domain deduplication removed {len(domain_duplicates)} resources")

            # Check for original resources
            original_deduped, original_filtered = self._filter_original_urls(domain_deduped)
            dedup_stats["original_filtered"] = len(original_filtered)
            self.logger.info(f"Original URL filtering removed {len(original_filtered)} resources")

            # Layer 4: Semantic similarity
            semantic_deduped, semantic_duplicates = self._dedup_by_semantic(original_deduped)
            dedup_stats["semantic_filtered"] = len(semantic_duplicates)
            self.logger.info(f"Semantic deduplication removed {len(semantic_duplicates)} resources")

            # Final deduplicated resources
            dedup_stats["final"] = len(semantic_deduped)

            # Calculate duplicate ratio
            duplicate_ratio = (dedup_stats["candidates"] - dedup_stats["final"]) / max(1, dedup_stats["candidates"])
            self.logger.info(f"Duplicate ratio: {duplicate_ratio:.2f} ({dedup_stats['final']}/{dedup_stats['candidates']} resources kept)")

            # Check if duplicate ratio exceeds threshold
            if duplicate_ratio > self.duplicate_threshold:
                self.logger.warning(
                    f"Duplicate ratio ({duplicate_ratio:.2f}) exceeds threshold ({self.duplicate_threshold}). "
                    f"This may indicate low-quality search results or insufficient differentiation in queries."
                )
                # Note: We don't raise an exception here as in the spec to allow processing to continue

            # Log deduplication results
            log._LOGGER.info(json.dumps({
                "phase": "deduplication_complete",
                "dedup_stats": dedup_stats,
                "duplicate_ratio": duplicate_ratio,
                "threshold": self.duplicate_threshold,
                "exceeded_threshold": duplicate_ratio > self.duplicate_threshold
            }))

            # Save deduplication stats
            self._save_dedup_stats(dedup_stats)

            # Save the deduplicated resources
            self._save_deduplicated_resources(semantic_deduped)

            return semantic_deduped

    def _dedup_by_case(self, resources: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Deduplicate resources by case-insensitive title comparison.

        Args:
            resources: List of resources

        Returns:
            Tuple of (deduplicated resources, filtered duplicates)
        """
        seen_titles = set()
        deduplicated = []
        duplicates = []

        for resource in resources:
            title = resource.get("name", "").lower()

            if title in seen_titles:
                duplicates.append(resource)
            else:
                seen_titles.add(title)
                deduplicated.append(resource)

        return deduplicated, duplicates

    def _dedup_by_levenshtein(self, resources: List[Dict], threshold: int = 2) -> Tuple[List[Dict], List[Dict]]:
        """Deduplicate resources by Levenshtein distance.

        Args:
            resources: List of resources
            threshold: Maximum Levenshtein distance to consider as duplicate

        Returns:
            Tuple of (deduplicated resources, filtered duplicates)
        """
        deduplicated = []
        duplicates = []
        reference_titles = []

        for resource in resources:
            title = resource.get("name", "")
            category = resource.get("category", "")
            is_duplicate = False

            # Use lower threshold for video categories
            local_threshold = threshold
            if category in self.video_categories:
                # For video categories, we're more strict about duplicates
                local_threshold = 1

            for ref_title in reference_titles:
                distance = Levenshtein.distance(title.lower(), ref_title.lower())

                if distance <= local_threshold:
                    is_duplicate = True
                    break

            if is_duplicate:
                duplicates.append(resource)
            else:
                reference_titles.append(title)
                deduplicated.append(resource)

        return deduplicated, duplicates

    def _dedup_by_domain_and_title(self, resources: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Deduplicate resources by canonical URL and hostname + title matching.

        Args:
            resources: List of resources

        Returns:
            Tuple of (deduplicated resources, filtered duplicates)
        """
        seen_canonical_urls = set()
        seen_hostname_titles = set()
        deduplicated = []
        duplicates = []

        for resource in resources:
            url = resource.get("url", "")
            title = resource.get("name", "").lower()
            canonical_url = self._get_canonical_url(url)

            # Extract hostname for (hostname, title) matching
            hostname = self._get_hostname(url)
            hostname_title_key = f"{hostname}:{title}"

            if canonical_url in seen_canonical_urls or hostname_title_key in seen_hostname_titles:
                duplicates.append(resource)
            else:
                seen_canonical_urls.add(canonical_url)
                seen_hostname_titles.add(hostname_title_key)
                deduplicated.append(resource)

        return deduplicated, duplicates

    def _filter_original_urls(self, resources: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Filter resources that already exist in the original list.

        Args:
            resources: List of resources

        Returns:
            Tuple of (filtered resources, original resources)
        """
        filtered = []
        original = []

        for resource in resources:
            url = resource.get("url", "")

            if url in self.original_urls:
                original.append(resource)
            else:
                # Also check canonical URLs
                canonical_url = self._get_canonical_url(url)
                original_canonicals = {self._get_canonical_url(o_url) for o_url in self.original_urls}

                if canonical_url in original_canonicals:
                    original.append(resource)
                else:
                    filtered.append(resource)

        return filtered, original

    def _dedup_by_semantic(self, resources: List[Dict], threshold: float = 0.85) -> Tuple[List[Dict], List[Dict]]:
        """Deduplicate resources by semantic similarity.

        Args:
            resources: List of resources
            threshold: Similarity threshold (0.0-1.0) to consider as duplicate

        Returns:
            Tuple of (deduplicated resources, filtered duplicates)
        """
        if not resources:
            return [], []

        # Lazy-load the sentence transformer model
        if self.sentence_transformer is None:
            self.logger.info("Loading sentence transformer model")
            self.sentence_transformer = SentenceTransformer("all-MiniLM-L6-v2")

        # Extract text from resources
        texts = []
        categories = []
        for resource in resources:
            title = resource.get("name", "")
            description = resource.get("description", "")
            category = resource.get("category", "")
            text = f"{title} {description}".strip()
            texts.append(text)
            categories.append(category)

        # Generate embeddings
        embeddings = self.sentence_transformer.encode(texts, show_progress_bar=False)

        # Normalize embeddings
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        # Use a more efficient approach to find duplicates
        deduplicated = []
        duplicates = []
        deduplicated_embeddings = []
        deduplicated_categories = []

        # Process resources in order, checking each against previously selected unique resources
        for i, (resource, embedding, category) in enumerate(zip(resources, embeddings, categories)):
            is_duplicate = False

            # Adjust threshold based on category
            local_threshold = threshold
            if category in self.video_categories:
                local_threshold = 0.88  # Higher threshold (less strict) for video categories

            # Compare only with previously selected unique resources
            for j, (unique_embedding, unique_category) in enumerate(zip(deduplicated_embeddings, deduplicated_categories)):
                # Compute cosine similarity
                similarity = np.dot(embedding, unique_embedding)

                # Only consider it a duplicate if similarity is high and either:
                # 1. Categories match, or
                # 2. One of the categories is video-related (for cross-category deduplication)
                if similarity >= local_threshold and (
                    category == unique_category or
                    category in self.video_categories or
                    unique_category in self.video_categories
                ):
                    is_duplicate = True
                    break

            if is_duplicate:
                duplicates.append(resource)
            else:
                deduplicated.append(resource)
                deduplicated_embeddings.append(embedding)
                deduplicated_categories.append(category)

        return deduplicated, duplicates

    def _get_canonical_url(self, url: str) -> str:
        """Get the canonical representation of a URL.

        Args:
            url: URL to canonicalize

        Returns:
            Canonical URL
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove 'www.' prefix
            if domain.startswith("www."):
                domain = domain[4:]

            # Normalize path
            path = parsed.path.rstrip("/").lower()

            # Return domain + path as canonical representation
            return f"{domain}{path}"

        except Exception:
            # If parsing fails, return the original URL
            return url.lower()

    def _get_hostname(self, url: str) -> str:
        """Extract the hostname from a URL.

        Args:
            url: URL to extract hostname from

        Returns:
            Hostname
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove 'www.' prefix
            if domain.startswith("www."):
                domain = domain[4:]

            return domain

        except Exception:
            # If parsing fails, return empty string
            return ""

    def _save_dedup_stats(self, stats: Dict) -> str:
        """Save deduplication statistics to a JSON file.

        Args:
            stats: Deduplication statistics

        Returns:
            Path to the saved JSON file
        """
        output_path = os.path.join(self.output_dir, "dedup_stats.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved deduplication statistics to {output_path}")
        return output_path

    def _save_deduplicated_resources(self, resources: List[Dict]) -> str:
        """Save deduplicated resources to a JSON file.

        Args:
            resources: Deduplicated resources

        Returns:
            Path to the saved JSON file
        """
        output_path = os.path.join(self.output_dir, "new_links.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(resources, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved {len(resources)} deduplicated resources to {output_path}")
        return output_path
