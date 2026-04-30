"""
Query builder for Neo4j database operations.
Provides structured query construction for knowledge base operations.
"""

from __future__ import annotations
from typing import Optional

from .search import SearchCriteria
from ..utils.logging import get_logger

logger = get_logger(__name__)


class QueryBuilder:
    """Builds Cypher queries for knowledge base operations."""

    def __init__(self):
        self.logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Lucene helpers
    # ------------------------------------------------------------------

    def _build_lucene_query(self, search_text: str) -> str:
        """
        Convert plain-text keywords into a Lucene OR+fuzzy query string.
        Every term gets a fuzzy (~) suffix so near-matches score positively.
        """
        terms = [t.strip() for t in search_text.split() if t.strip()]
        if not terms:
            return search_text
        return " OR ".join(f"{t}~" for t in terms)

    @staticmethod
    def _safe_lucene(lucene_query: str) -> str:
        """Escape double-quotes so the query can be embedded in a Cypher string literal."""
        return lucene_query.replace('"', '\\"')

    # ------------------------------------------------------------------
    # Main structured search (no full-text index)
    # ------------------------------------------------------------------

    def build_search_query(self, criteria: SearchCriteria) -> str:
        """
        Build a structured Cypher search against ProblemStatement nodes.
        Traverses: Domain -> PS -> Phase -> SubPhase -> Content

        No full-text index used; filters applied via WHERE on property values.
        """
        query_parts = []

        query_parts.append("""
            MATCH (ps:ProblemStatement)
            OPTIONAL MATCH (ps)-[:BELONGS_TO]->(d:Domain)
            OPTIONAL MATCH (ps)-[:HAS_PHASE]->(ph:Phase)
            OPTIONAL MATCH (ph)-[:HAS_SUBPHASE]->(sp:SubPhase)
            OPTIONAL MATCH (sp)-[:HAS_CONTENT]->(c:Content)
        """)

        where_conditions = []

        if criteria.domains:
            domain_list = [f"'{d}'" for d in criteria.domains]
            where_conditions.append(f"d.name IN [{', '.join(domain_list)}]")

        if criteria.phases:
            phase_list = [f"'{p}'" for p in criteria.phases]
            where_conditions.append(f"ph.code IN [{', '.join(phase_list)}]")

        if criteria.part_numbers:
            part_conditions = []
            for part in criteria.part_numbers:
                part_conditions.append(f"ps.part_number =~ '(?i).*{part}.*'")
                part_conditions.append(f"c.text =~ '(?i).*{part}.*'")
            where_conditions.append(f"({' OR '.join(part_conditions)})")

        if criteria.keywords:
            keyword_conditions = []
            for keyword in criteria.keywords:
                if criteria.fuzzy_match:
                    keyword_conditions.extend([
                        f"ps.text =~ '(?i).*{keyword}.*'",
                        f"ps.title =~ '(?i).*{keyword}.*'",
                        f"ps.summary =~ '(?i).*{keyword}.*'",
                        f"any(kw IN coalesce(ps.keywords_extracted, []) WHERE kw =~ '(?i).*{keyword}.*')",
                        f"any(tag IN coalesce(ps.domain_tags, []) WHERE tag =~ '(?i).*{keyword}.*')",
                        f"c.text =~ '(?i).*{keyword}.*'",
                        f"c.summary =~ '(?i).*{keyword}.*'",
                        f"c.root_cause =~ '(?i).*{keyword}.*'",
                        f"c.corrective_action =~ '(?i).*{keyword}.*'",
                    ])
                else:
                    keyword_conditions.extend([
                        f"ps.text CONTAINS '{keyword}'",
                        f"ps.title CONTAINS '{keyword}'",
                        f"ps.summary CONTAINS '{keyword}'",
                        f"c.text CONTAINS '{keyword}'",
                        f"c.summary CONTAINS '{keyword}'",
                        f"c.root_cause CONTAINS '{keyword}'",
                        f"c.corrective_action CONTAINS '{keyword}'",
                    ])
            if keyword_conditions:
                where_conditions.append(f"({' OR '.join(keyword_conditions)})")

        if criteria.date_from:
            where_conditions.append(f"ps.created_at >= datetime('{criteria.date_from}')")
        if criteria.date_to:
            where_conditions.append(f"ps.created_at <= datetime('{criteria.date_to}')")

        if criteria.severity_min is not None:
            where_conditions.append(f"c.severity >= {criteria.severity_min}")

        if criteria.category:
            where_conditions.append(f"c.category =~ '(?i){criteria.category}'")

        if where_conditions:
            query_parts.append(f"WHERE {' AND '.join(where_conditions)}")

        query_parts.append("""
            WITH ps,
                 collect(DISTINCT d.name) AS domains,
                 collect(DISTINCT {
                     code: ph.code, label: ph.label
                 }) AS phases,
                 collect(DISTINCT {
                     id: c.id,
                     text: c.text,
                     summary: c.summary,
                     keywords: c.keywords,
                     category: c.category,
                     severity: c.severity,
                     root_cause: c.root_cause,
                     corrective_action: c.corrective_action,
                     model: c.model,
                     confidence: c.confidence,
                     sub_phase: sp.name,
                     phase_code: ph.code
                 }) AS contents
            RETURN ps {
                .id,
                .title,
                .text,
                .keywords,
                .ticket_ref,
                .part_number,
                .created_at,
                .summary,
                .keywords_extracted,
                .quality_score,
                .domain_tags,
                .upload_source,
                .ollama_processed,
                domains: domains,
                phases: phases,
                contents: contents
            } AS problem_statement
            ORDER BY ps.created_at DESC
        """)

        if criteria.limit > 0:
            query_parts.append(f"LIMIT {criteria.limit}")

        full_query = "\n".join(query_parts)
        self.logger.debug("Built PS search query with %d conditions", len(where_conditions))
        return full_query

    # ------------------------------------------------------------------
    # Full-text fallback search (scored, no structured filters)
    # ------------------------------------------------------------------

    def build_fulltext_search_query(
        self,
        search_text: str,
        limit: int = 50,
        min_score: float = 0.3,
    ) -> str:
        """
        Relevance-gated full-text search across ProblemStatement and Content indexes.

        Strategy
        --------
        - Lucene OR+fuzzy query ensures every keyword contributes to score.
        - Two sequential CALL{} subqueries collect scored hits into lists,
          avoiding the Cypher UNION ALL column-name restriction.
        - Lists merged with +, UNWINDed, deduplicated by PS id keeping max(score).
        - Hydrates full PS details after deduplication for clean return shape.
        """
        lucene_query = self._build_lucene_query(search_text)
        safe_q = self._safe_lucene(lucene_query)
        candidate_limit = max(limit * 5, 200)

        return f"""
            // ── Phase 1: scored hits from ProblemStatement index ─────────────
            CALL {{
                CALL db.index.fulltext.queryNodes("ps_text_index", "{safe_q}")
                YIELD node AS ps, score
                WHERE score >= {min_score}
                RETURN ps.id AS ps_id, score * 2.0 AS hit_score
                ORDER BY hit_score DESC
                LIMIT {candidate_limit}
            }}
            WITH collect({{ps_id: ps_id, score: hit_score}}) AS ps_hits

            // ── Phase 2: scored hits from Content index, mapped back to PS ───
            CALL {{
                CALL db.index.fulltext.queryNodes("content_text_index", "{safe_q}")
                YIELD node AS c, score
                WHERE score >= {min_score}
                MATCH (sp:SubPhase)-[:HAS_CONTENT]->(c)
                MATCH (ph:Phase)-[:HAS_SUBPHASE]->(sp)
                MATCH (ps:ProblemStatement)-[:HAS_PHASE]->(ph)
                RETURN ps.id AS ps_id, score AS hit_score
                ORDER BY hit_score DESC
                LIMIT {candidate_limit}
            }}
            WITH ps_hits,
                 collect({{ps_id: ps_id, score: hit_score}}) AS content_hits

            // ── Phase 3: merge, deduplicate, keep best score per PS ──────────
            WITH ps_hits + content_hits AS all_hits
            UNWIND all_hits AS hit
            WITH hit.ps_id AS ps_id, max(hit.score) AS best_score
            WHERE ps_id IS NOT NULL

            // ── Phase 4: hydrate full PS details ─────────────────────────────
            MATCH (ps:ProblemStatement {{id: ps_id}})
            OPTIONAL MATCH (ps)-[:BELONGS_TO]->(d:Domain)
            OPTIONAL MATCH (ps)-[:HAS_PHASE]->(ph:Phase)
            OPTIONAL MATCH (ph)-[:HAS_SUBPHASE]->(sp:SubPhase)
            OPTIONAL MATCH (sp)-[:HAS_CONTENT]->(c:Content)

            WITH ps, best_score,
                 collect(DISTINCT d.name)  AS domains,
                 collect(DISTINCT ph.code) AS phase_codes,
                 collect(DISTINCT {{
                     id: c.id, text: c.text, summary: c.summary,
                     category: c.category, severity: c.severity,
                     root_cause: c.root_cause,
                     corrective_action: c.corrective_action,
                     model: c.model, confidence: c.confidence,
                     sub_phase: sp.name, phase_code: ph.code
                 }}) AS contents

            RETURN ps {{
                .id, .title, .text, .keywords,
                .ticket_ref, .part_number, .created_at,
                .summary, .keywords_extracted, .quality_score,
                .domain_tags, .upload_source, .ollama_processed,
                domains:     domains,
                phase_codes: phase_codes,
                contents:    contents
            }} AS problem_statement,
            best_score AS relevance_score
            ORDER BY best_score DESC
            LIMIT {limit}
        """

    # ------------------------------------------------------------------
    # Advanced scored + structured search (Tier 1)
    # ------------------------------------------------------------------

    def build_advanced_search_query(self, search_text: str, criteria: SearchCriteria) -> str:
        """
        High-impact search combining Lucene full-text scoring with structured filters.

        Key design decisions
        --------------------
        1.  Two sequential CALL{} blocks collect scored PS-id lists into memory —
            avoids the Cypher UNION ALL column-name restriction entirely.
        2.  Lists merged, UNWINDed, deduplicated (max score per PS id).
        3.  Structured filters (domain, phase, severity, date, category) are applied
            AFTER hydration using list-level checks (``any(x IN list WHERE ...)``)
            so an OPTIONAL MATCH that returns NULL never silently drops a valid PS.
        4.  ``candidate_limit`` is generous (limit × 8) so the score gate doesn't
            cut off relevant records before dedup.
        """
        lucene_query = self._build_lucene_query(search_text)
        safe_q = self._safe_lucene(lucene_query)

        limit = max(criteria.limit, 1)
        candidate_limit = max(limit * 8, 200)
        min_score = 0.25  # slightly lower gate so more candidates survive to filter

        # Build post-hydration WHERE predicates that work on collected lists
        post_filters: list[str] = []

        if criteria.domains:
            domain_list = ", ".join(f'"{d}"' for d in criteria.domains)
            # Keep PS only if at least one of its domains matches
            post_filters.append(f"any(dom IN domains WHERE dom IN [{domain_list}])")

        if criteria.phases:
            phase_list = ", ".join(f'"{p}"' for p in criteria.phases)
            post_filters.append(f"any(pc IN phase_codes WHERE pc IN [{phase_list}])")

        if criteria.date_from:
            post_filters.append(f"ps.created_at >= datetime('{criteria.date_from}')")
        if criteria.date_to:
            post_filters.append(f"ps.created_at <= datetime('{criteria.date_to}')")

        # Content-level filters — checked against the collected contents list
        if criteria.severity_min is not None:
            post_filters.append(
                f"any(ct IN contents WHERE ct.severity >= {criteria.severity_min})"
            )
        if criteria.category:
            post_filters.append(
                f"any(ct IN contents WHERE ct.category =~ '(?i){criteria.category}')"
            )

        where_clause = ""
        if post_filters:
            where_clause = "WHERE " + "\n  AND ".join(post_filters)

        return f"""
            // ── Phase 1: scored hits from ProblemStatement index (weight ×2) ─
            CALL {{
                CALL db.index.fulltext.queryNodes("ps_text_index", "{safe_q}")
                YIELD node AS ps, score
                WHERE score >= {min_score}
                RETURN ps.id AS hit_id, score * 2.0 AS hit_score
                ORDER BY hit_score DESC LIMIT {candidate_limit}
            }}
            WITH collect({{id: hit_id, score: hit_score}}) AS ps_hits

            // ── Phase 2: scored hits from Content index, mapped back to PS ───
            CALL {{
                CALL db.index.fulltext.queryNodes("content_text_index", "{safe_q}")
                YIELD node AS c, score
                WHERE score >= {min_score}
                MATCH (sp:SubPhase)-[:HAS_CONTENT]->(c)
                MATCH (ph:Phase)-[:HAS_SUBPHASE]->(sp)
                MATCH (ps:ProblemStatement)-[:HAS_PHASE]->(ph)
                RETURN ps.id AS hit_id, score AS hit_score
                ORDER BY hit_score DESC LIMIT {candidate_limit}
            }}
            WITH ps_hits,
                 collect({{id: hit_id, score: hit_score}}) AS content_hits

            // ── Phase 3: merge & deduplicate by PS id, keep best score ───────
            WITH ps_hits + content_hits AS all_hits
            UNWIND all_hits AS hit
            WITH hit.id AS hit_id, max(hit.score) AS best_score
            WHERE hit_id IS NOT NULL

            // ── Phase 4: hydrate PS + collect domain / phase / content lists ─
            MATCH (ps:ProblemStatement {{id: hit_id}})
            OPTIONAL MATCH (ps)-[:BELONGS_TO]->(d:Domain)
            OPTIONAL MATCH (ps)-[:HAS_PHASE]->(ph:Phase)
            OPTIONAL MATCH (ph)-[:HAS_SUBPHASE]->(sp:SubPhase)
            OPTIONAL MATCH (sp)-[:HAS_CONTENT]->(c:Content)

            WITH ps, best_score,
                 collect(DISTINCT d.name)  AS domains,
                 collect(DISTINCT ph.code) AS phase_codes,
                 collect(DISTINCT {{
                     id: c.id, text: c.text, summary: c.summary,
                     category: c.category, severity: c.severity,
                     root_cause: c.root_cause,
                     corrective_action: c.corrective_action,
                     model: c.model, confidence: c.confidence,
                     sub_phase: sp.name, phase_code: ph.code
                 }}) AS contents

            // ── Phase 5: apply structured filters on collected lists ──────────
            {where_clause}

            RETURN ps {{
                .id, .title, .text, .keywords,
                .ticket_ref, .part_number, .created_at,
                .summary, .keywords_extracted, .quality_score,
                .domain_tags, .upload_source, .ollama_processed,
                domains:     domains,
                phase_codes: phase_codes,
                contents:    contents
            }} AS problem_statement,
            best_score AS relevance_score
            ORDER BY best_score DESC
            LIMIT {limit}
        """

    # ------------------------------------------------------------------
    # Write queries
    # ------------------------------------------------------------------

    def build_ps_creation_query(self) -> str:
        """
        Create a ProblemStatement node and link it to one or more Domains.

        Params: ps_id, title, text, keywords, ticket_ref, part_number,
                domain_names (list), summary, keywords_extracted (list),
                quality_score (float), domain_tags (list),
                upload_source, ollama_processed (bool)
        Returns: ps_id
        """
        return """
            CREATE (ps:ProblemStatement {
                id:                 $ps_id,
                title:              $title,
                text:               $text,
                keywords:           $keywords,
                ticket_ref:         $ticket_ref,
                part_number:        $part_number,
                summary:            $summary,
                keywords_extracted: $keywords_extracted,
                quality_score:      $quality_score,
                domain_tags:        $domain_tags,
                upload_source:      $upload_source,
                ollama_processed:   $ollama_processed,
                created_at:         datetime()
            })
            WITH ps
            UNWIND $domain_names AS domain_name
                MATCH (d:Domain {name: domain_name})
                MERGE (d)-[:HAS_PS]->(ps)
                MERGE (ps)-[:BELONGS_TO]->(d)
            RETURN ps.id AS ps_id
        """

    def build_ps_phase_scaffold_query(self) -> str:
        """
        Scaffold D1-D7 Phase and SubPhase graph for a ProblemStatement.
        Params: ps_id
        """
        return """
            MATCH (ps:ProblemStatement {id: $ps_id})
            WITH ps
            UNWIND [
              {code: "D1", label: "Organise and Plan",
               subs: ["organise", "plan"]},
              {code: "D2", label: "Describe Problem",
               subs: ["problem_statement", "symptoms"]},
              {code: "D3", label: "Containment Plan",
               subs: ["immediate_action", "verification"]},
              {code: "D4", label: "Describe Cause",
               subs: ["root_cause", "contributing_factors"]},
              {code: "D5", label: "Ishikawa and 5 Whys",
               subs: ["ishikawa_analysis", "five_whys"]},
              {code: "D6", label: "Intermediate Action",
               subs: ["corrective_action", "owner", "deadline"]},
              {code: "D7", label: "Preservation of Recurrence",
               subs: ["prevention", "lesson_learned"]}
            ] AS phaseData
            MERGE (ph:Phase {ps_id: $ps_id, code: phaseData.code})
            SET ph.label = phaseData.label
            MERGE (ps)-[:HAS_PHASE]->(ph)
            WITH ps, ph, phaseData
            UNWIND phaseData.subs AS subName
                MERGE (sp:SubPhase {ps_id: $ps_id, phase: ph.code, name: subName})
                MERGE (ph)-[:HAS_SUBPHASE]->(sp)
            RETURN count(sp) AS scaffolded
        """

    def build_content_creation_query(self) -> str:
        """
        Create a Content node under a specific SubPhase of a PS.
        Params: content_id, ps_id, phase_code, sub_phase, text, summary,
                keywords, category, severity, root_cause, corrective_action,
                model, confidence
        Returns: content_id
        """
        return """
            MATCH (sp:SubPhase {ps_id: $ps_id, phase: $phase_code, name: $sub_phase})
            CREATE (c:Content {
                id:                $content_id,
                text:              $text,
                summary:           $summary,
                keywords:          $keywords,
                category:          $category,
                severity:          $severity,
                root_cause:        $root_cause,
                corrective_action: $corrective_action,
                evaluated_by:      "ollama",
                model:             $model,
                confidence:        $confidence,
                created_at:        datetime()
            })
            CREATE (sp)-[:HAS_CONTENT]->(c)
            RETURN c.id AS content_id
        """

    # ------------------------------------------------------------------
    # Retrieval queries
    # ------------------------------------------------------------------

    def build_get_ps_details_query(self) -> str:
        """Retrieve full PS graph: domains, all phases, subphases, content. Params: ps_id"""
        return """
            MATCH (ps:ProblemStatement {id: $ps_id})
            OPTIONAL MATCH (ps)-[:BELONGS_TO]->(d:Domain)
            OPTIONAL MATCH (ps)-[:HAS_PHASE]->(ph:Phase)
            OPTIONAL MATCH (ph)-[:HAS_SUBPHASE]->(sp:SubPhase)
            OPTIONAL MATCH (sp)-[:HAS_CONTENT]->(c:Content)
            WITH ps,
                 collect(DISTINCT d.name) AS domains,
                 collect(DISTINCT {
                     code: ph.code,
                     label: ph.label,
                     sub_phases: []
                 }) AS phases,
                 collect(DISTINCT {
                     phase_code:        ph.code,
                     sub_phase:         sp.name,
                     content_id:        c.id,
                     text:              c.text,
                     summary:           c.summary,
                     keywords:          c.keywords,
                     category:          c.category,
                     severity:          c.severity,
                     root_cause:        c.root_cause,
                     corrective_action: c.corrective_action,
                     model:             c.model,
                     confidence:        c.confidence
                 }) AS contents
            RETURN ps {
                .id, .title, .text, .keywords,
                .ticket_ref, .part_number, .created_at,
                domains:  domains,
                phases:   phases,
                contents: contents
            } AS ps_details
        """

    def build_get_domain_ps_list_query(self) -> str:
        """List all ProblemStatements under a Domain. Params: domain_name"""
        return """
            MATCH (d:Domain {name: $domain_name})-[:HAS_PS]->(ps:ProblemStatement)
            RETURN ps {
                .id, .title, .text, .keywords,
                .ticket_ref, .part_number, .created_at
            } AS problem_statement
            ORDER BY ps.created_at DESC
        """

    def build_get_all_domains_with_ps_query(self) -> str:
        """Overview of all Domains with count of associated PS."""
        return """
            MATCH (d:Domain)
            OPTIONAL MATCH (d)-[:HAS_PS]->(ps:ProblemStatement)
            RETURN d.name AS domain,
                   count(DISTINCT ps) AS ps_count,
                   collect(DISTINCT ps.id) AS ps_ids
            ORDER BY d.name
        """

    # ------------------------------------------------------------------
    # Relationship / utility
    # ------------------------------------------------------------------

    def build_relationship_query(self, from_type: str, to_type: str, relationship: str) -> str:
        """Build query to create a relationship between two nodes by ID."""
        return f"""
            MATCH (a:{from_type} {{id: $from_id}})
            MATCH (b:{to_type} {{id: $to_id}})
            MERGE (a)-[:{relationship}]->(b)
            RETURN a.id AS from_id, b.id AS to_id
        """

    def build_cleanup_query(self, node_type: Optional[str] = None) -> str:
        """Build query to clean up nodes (testing/reset)."""
        if node_type:
            return f"""
                MATCH (n:{node_type})
                DETACH DELETE n
                RETURN count(n) AS deleted_count
            """
        return """
            MATCH (n)
            DETACH DELETE n
            RETURN count(n) AS deleted_count
        """

    # ------------------------------------------------------------------
    # PS metadata update (post-Ollama processing)
    # ------------------------------------------------------------------

    def build_ps_summary_update_query(self) -> str:
        """
        Persist Ollama PS-level extraction results onto a ProblemStatement node.
        Params: ps_id, summary, keywords_extracted (list), quality_score (float),
                domain_tags (list), ollama_processed (bool)
        """
        return """
            MATCH (ps:ProblemStatement {id: $ps_id})
            SET ps.summary            = $summary,
                ps.keywords_extracted = $keywords_extracted,
                ps.quality_score      = $quality_score,
                ps.domain_tags        = $domain_tags,
                ps.ollama_processed   = $ollama_processed,
                ps.updated_at         = datetime()
            RETURN ps.id AS ps_id, ps.summary AS summary
        """

    # ------------------------------------------------------------------
    # Domain aggregated stats
    # ------------------------------------------------------------------

    def build_domain_stats_update_query(self) -> str:
        """
        Re-aggregate and persist stats on a Domain node.
        Params: domain_name
        """
        return """
            MATCH (d:Domain {name: $domain_name})
            OPTIONAL MATCH (d)-[:HAS_PS]->(ps:ProblemStatement)
            WITH d,
                 count(DISTINCT ps)                          AS ps_count,
                 avg(ps.quality_score)                       AS avg_quality,
                 [kw IN reduce(acc = [], p IN collect(DISTINCT ps) |
                     acc + coalesce(p.keywords_extracted, [])
                 ) | kw][0..20]                              AS top_keywords
            SET d.ps_count          = ps_count,
                d.avg_quality_score = round(coalesce(avg_quality, 0.0) * 100) / 100,
                d.top_keywords      = top_keywords,
                d.last_updated      = datetime()
            RETURN d.name AS domain, d.ps_count AS ps_count
        """
