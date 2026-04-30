"""Read and search operations for the knowledge repository."""

from __future__ import annotations

from typing import Any

from .search import SearchCriteria
from ..utils.logging import get_logger

logger = get_logger(__name__)


class KnowledgeRepositorySearchMixin:
    """Search-oriented repository operations."""

    # ------------------------------------------------------------------
    # Primary search methods
    # ------------------------------------------------------------------

    def search_problem_statements(self, criteria: SearchCriteria) -> list[dict[str, Any]]:
        """
        Structured search for ProblemStatements.
        Traverses: Domain -> PS -> Phase -> SubPhase -> Content
        Returns flat list of PS dicts (no relevance_score key).
        """
        try:
            query = self.query_builder.build_search_query(criteria)
            logger.debug(
                "Structured search: domains=%s keywords=%s phases=%s limit=%s",
                criteria.domains, criteria.keywords, criteria.phases, criteria.limit,
            )
            results = self.connection.execute_query(query)
            ps_list = [row["problem_statement"] for row in results if "problem_statement" in row]
            logger.info("Structured search returned %d problem statements", len(ps_list))
            return ps_list
        except Exception as exc:
            logger.error("Structured PS search failed: %s", exc)
            raise RuntimeError(f"PS search failed: {exc}") from exc

    def search_problems(self, criteria: SearchCriteria) -> list[dict[str, Any]]:
        """Backward-compatible alias for search_problem_statements."""
        return self.search_problem_statements(criteria)

    def fulltext_search(self, search_text: str, limit: int = 50) -> list[dict[str, Any]]:
        """
        Relevance-ranked full-text search across ps_text_index + content_text_index.

        Returns list of dicts shaped as:
            {"problem_statement": {...ps fields...}, "relevance_score": float}
        so it is consistent with advanced_search output and processor unwrapping.
        """
        try:
            query = self.query_builder.build_fulltext_search_query(search_text, limit)
            results = self.connection.execute_query(query)
            logger.info(
                "Full-text search %r → %d results (limit=%d)",
                search_text, len(results), limit,
            )
            return results
        except Exception as exc:
            logger.error("Full-text search failed [query=%r]: %s", search_text, exc)
            raise RuntimeError(f"Full-text search failed: {exc}") from exc

    def advanced_search(
        self,
        search_text: str,
        criteria: SearchCriteria | None = None,
    ) -> list[dict[str, Any]]:
        """
        Relevance-scored search with optional structured filters.

        Returns list of dicts shaped as:
            {"problem_statement": {...ps fields...}, "relevance_score": float}

        The processor unwraps these rows; fulltext_search now returns the same shape
        so either path produces consistent data for downstream helpers.
        """
        criteria = criteria or SearchCriteria(limit=50)
        try:
            query = self.query_builder.build_advanced_search_query(search_text, criteria)
            results = self.connection.execute_query(query)
            logger.info(
                "Advanced search %r → %d results (domains=%s phases=%s limit=%d)",
                search_text, len(results),
                criteria.domains, criteria.phases, criteria.limit,
            )
            return results
        except Exception as exc:
            logger.error(
                "Advanced search failed [query=%r domains=%s phases=%s]: %s",
                search_text, criteria.domains, criteria.phases, exc,
            )
            raise RuntimeError(f"Advanced search failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Detail / overview queries
    # ------------------------------------------------------------------

    def get_ps_details(self, ps_id: str) -> dict[str, Any] | None:
        """Retrieve full PS graph: domains, all phases, subphases, and content."""
        try:
            query = self.query_builder.build_get_ps_details_query()
            results = self.connection.execute_query(query, {"ps_id": ps_id})
            if results:
                return results[0]["ps_details"]
            logger.warning("PS %r not found", ps_id)
            return None
        except Exception as exc:
            logger.error("Failed to get PS details for %r: %s", ps_id, exc)
            raise RuntimeError(f"Failed to get PS details: {exc}") from exc

    def get_domain_ps_list(self, domain_name: str) -> list[dict[str, Any]]:
        """List all ProblemStatements under a domain."""
        try:
            query = self.query_builder.build_get_domain_ps_list_query()
            results = self.connection.execute_query(query, {"domain_name": domain_name})
            return [row["problem_statement"] for row in results if "problem_statement" in row]
        except Exception as exc:
            logger.error("Domain PS list failed for %r: %s", domain_name, exc)
            raise RuntimeError(f"Domain PS list failed: {exc}") from exc

    def get_all_domains_overview(self) -> list[dict[str, Any]]:
        """Overview of all domains with PS counts."""
        try:
            query = self.query_builder.build_get_all_domains_with_ps_query()
            return self.connection.execute_query(query)
        except Exception as exc:
            logger.error("Domains overview failed: %s", exc)
            raise RuntimeError(f"Domains overview failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_statistics(self) -> dict[str, Any]:
        """Return knowledge-base statistics."""
        try:
            stats: dict[str, Any] = {}
            for node_type in ["ProblemStatement", "Phase", "SubPhase", "Content", "Domain"]:
                result = self.connection.execute_query(
                    f"MATCH (n:{node_type}) RETURN count(n) AS count"
                )
                stats[f"{node_type.lower()}_count"] = result[0]["count"] if result else 0

            rel_result = self.connection.execute_query(
                "MATCH ()-[r]->() RETURN count(r) AS relationship_count"
            )
            stats["relationship_count"] = (
                rel_result[0]["relationship_count"] if rel_result else 0
            )

            domain_result = self.connection.execute_query(
                """
                MATCH (d:Domain)
                OPTIONAL MATCH (d)-[:HAS_PS]->(ps:ProblemStatement)
                RETURN d.name AS domain, count(DISTINCT ps) AS ps_count
                ORDER BY d.name
                """
            )
            stats["domain_breakdown"] = {
                row["domain"]: row["ps_count"] for row in domain_result
            }

            logger.debug("Statistics computed: %s", stats)
            return stats
        except Exception as exc:
            logger.error("Failed to get statistics: %s", exc)
            raise RuntimeError(f"Failed to get statistics: {exc}") from exc
