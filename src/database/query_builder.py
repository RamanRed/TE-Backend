"""
Query builder for Neo4j database operations.
Provides structured query construction for knowledge base operations.
"""

from __future__ import annotations

from .search import SearchCriteria
from ..utils.logging import get_logger

logger = get_logger(__name__)


class QueryBuilder:
    """Builds Cypher queries for knowledge base operations."""

    def __init__(self):
        self.logger = get_logger(__name__)

    def build_search_query(self, criteria: SearchCriteria) -> str:
        """
        Build search query against ProblemStatement nodes.
        Traverses: Domain -> PS -> Phase -> SubPhase -> Content

        Args:
            criteria: Search criteria

        Returns:
            Cypher query string
        """
        query_parts = []

        # Base match: PS with its domain and phase details
        query_parts.append("""
            MATCH (ps:ProblemStatement)
            OPTIONAL MATCH (ps)-[:BELONGS_TO]->(d:Domain)
            OPTIONAL MATCH (ps)-[:HAS_PHASE]->(ph:Phase)
            OPTIONAL MATCH (ph)-[:HAS_SUBPHASE]->(sp:SubPhase)
            OPTIONAL MATCH (sp)-[:HAS_CONTENT]->(c:Content)
        """)

        # Build WHERE conditions
        where_conditions = []

        # Domain filter
        if criteria.domains:
            domain_list = [f"'{d}'" for d in criteria.domains]
            where_conditions.append(f"d.name IN [{', '.join(domain_list)}]")

        # Phase code filter (D1-D7)
        if criteria.phases:
            phase_list = [f"'{p}'" for p in criteria.phases]
            where_conditions.append(f"ph.code IN [{', '.join(phase_list)}]")

        # Part number filter
        if criteria.part_numbers:
            part_conditions = []
            for part in criteria.part_numbers:
                part_conditions.append(f"ps.part_number =~ '(?i).*{part}.*'")
                part_conditions.append(f"c.text =~ '(?i).*{part}.*'")
            where_conditions.append(f"({' OR '.join(part_conditions)})")

        # Keyword search (searches PS text, title, summary, extracted keywords, and Content fields)
        if criteria.keywords:
            keyword_conditions = []
            for keyword in criteria.keywords:
                if criteria.fuzzy_match:
                    keyword_conditions.append(f"ps.text =~ '(?i).*{keyword}.*'")
                    keyword_conditions.append(f"ps.title =~ '(?i).*{keyword}.*'")
                    keyword_conditions.append(f"ps.summary =~ '(?i).*{keyword}.*'")
                    keyword_conditions.append(f"any(kw IN coalesce(ps.keywords_extracted, []) WHERE kw =~ '(?i).*{keyword}.*')")
                    keyword_conditions.append(f"any(tag IN coalesce(ps.domain_tags, []) WHERE tag =~ '(?i).*{keyword}.*')")
                    keyword_conditions.append(f"c.text =~ '(?i).*{keyword}.*'")
                    keyword_conditions.append(f"c.summary =~ '(?i).*{keyword}.*'")
                    keyword_conditions.append(f"c.root_cause =~ '(?i).*{keyword}.*'")
                    keyword_conditions.append(f"c.corrective_action =~ '(?i).*{keyword}.*'")
                else:
                    keyword_conditions.append(f"ps.text CONTAINS '{keyword}'")
                    keyword_conditions.append(f"ps.title CONTAINS '{keyword}'")
                    keyword_conditions.append(f"ps.summary CONTAINS '{keyword}'")
                    keyword_conditions.append(f"c.text CONTAINS '{keyword}'")
                    keyword_conditions.append(f"c.summary CONTAINS '{keyword}'")
                    keyword_conditions.append(f"c.root_cause CONTAINS '{keyword}'")
                    keyword_conditions.append(f"c.corrective_action CONTAINS '{keyword}'")
            if keyword_conditions:
                where_conditions.append(f"({' OR '.join(keyword_conditions)})")

        # Date range filter on PS creation date
        if criteria.date_from:
            where_conditions.append(f"ps.created_at >= datetime('{criteria.date_from}')")
        if criteria.date_to:
            where_conditions.append(f"ps.created_at <= datetime('{criteria.date_to}')")

        # Minimum severity filter on Content nodes
        if criteria.severity_min is not None:
            where_conditions.append(f"c.severity >= {criteria.severity_min}")

        # Ishikawa category filter on Content nodes
        if criteria.category:
            where_conditions.append(f"c.category =~ '(?i){criteria.category}'") 

        # Combine WHERE conditions
        if where_conditions:
            query_parts.append(f"WHERE {' AND '.join(where_conditions)}")

        # Return PS with aggregated domain/phase/content info
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
            } as problem_statement
            ORDER BY ps.created_at DESC
        """)

        if criteria.limit > 0:
            query_parts.append(f"LIMIT {criteria.limit}")

        full_query = '\n'.join(query_parts)
        self.logger.debug(f"Built PS search query with {len(where_conditions)} conditions")
        return full_query

    def build_fulltext_search_query(self, search_text: str, limit: int = 50) -> str:
        """
        Full-text search across ProblemStatement and Content indexes.

        Args:
            search_text: Text to search for
            limit: Maximum results to return

        Returns:
            Cypher query for full-text search
        """
        query = f"""
            CALL {{
                CALL db.index.fulltext.queryNodes("ps_text_index", "{search_text}")
                YIELD node, score
                RETURN node.id AS id, node.title AS title, node.text AS text,
                       score, "problem_statement" AS type
                ORDER BY score DESC
                LIMIT {limit}
            }}
            UNION ALL
            CALL {{
                CALL db.index.fulltext.queryNodes("content_text_index", "{search_text}")
                YIELD node, score
                RETURN node.id AS id, node.summary AS title, node.text AS text,
                       score, "content" AS type
                ORDER BY score DESC
                LIMIT {limit}
            }}
            RETURN id, title, text, score, type
            ORDER BY score DESC
            LIMIT {limit}
        """
        self.logger.debug(f"Built full-text search query for: {search_text}")
        return query

    # ------------------------------------------------------------------
    # Problem Statement (PS) creation
    # ------------------------------------------------------------------

    def build_ps_creation_query(self) -> str:
        """
        Create a ProblemStatement node and link it to one or more Domains.

        Params expected:
            ps_id, title, text, keywords, ticket_ref, part_number,
            domain_names (list),
            summary (str, Ollama PS-level summary),
            keywords_extracted (list, Ollama-extracted keywords),
            quality_score (float 0-1, Ollama quality estimate),
            domain_tags (list, Ollama-assigned domain tags),
            upload_source (str, e.g. 'structured_json' | 'manual'),
            ollama_processed (bool)
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
        Scaffold the full D1-D7 Phase and SubPhase graph for a ProblemStatement.

        Params expected: ps_id
        Creates: Phase nodes (D1-D7) and their standard SubPhase nodes,
                 all scoped to this PS.
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

    # ------------------------------------------------------------------
    # Content creation (Ollama-evaluated)
    # ------------------------------------------------------------------

    def build_content_creation_query(self) -> str:
        """
        Create a Content node under a specific SubPhase of a PS.
        Content properties are populated from Ollama evaluation.

        Params expected: content_id, ps_id, phase_code, sub_phase,
                         text, summary, keywords, category, severity,
                         root_cause, corrective_action, model, confidence
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
        """
        Retrieve full PS graph: domains, all phases, subphases, content.

        Params expected: ps_id
        """
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
        """
        List all ProblemStatements under a Domain (Graph 1 view).

        Params expected: domain_name
        """
        return """
            MATCH (d:Domain {name: $domain_name})-[:HAS_PS]->(ps:ProblemStatement)
            RETURN ps {
                .id, .title, .text, .keywords,
                .ticket_ref, .part_number, .created_at
            } AS problem_statement
            ORDER BY ps.created_at DESC
        """

    def build_get_all_domains_with_ps_query(self) -> str:
        """
        Overview of all Domains with count of associated PS (Graph 1 summary).
        """
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

        Params expected:
            ps_id, summary, keywords_extracted (list), quality_score (float),
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
        Computes ps_count, avg_quality_score, top_keywords, last_updated.

        Params expected: domain_name
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
            SET d.ps_count         = ps_count,
                d.avg_quality_score = round(coalesce(avg_quality, 0.0) * 100) / 100,
                d.top_keywords     = top_keywords,
                d.last_updated     = datetime()
            RETURN d.name AS domain, d.ps_count AS ps_count
        """

    # ------------------------------------------------------------------
    # Advanced / scored search
    # ------------------------------------------------------------------

    def build_advanced_search_query(self, search_text: str, criteria: SearchCriteria) -> str:
        """
        High-impact search combining:
          - Full-text index scoring via ps_text_index + content_text_index
          - Domain / phase / severity / date / category filters
          - Deduplication by PS id
          - Returns ranked results with score

        Args:
            search_text:  Free-text query for Lucene full-text index
            criteria:     Additional structured filters

        Returns:
            Cypher query string (no params; all values interpolated)
        """
        # Lucene query: escape special chars and add fuzzy where helpful
        safe_text = search_text.replace('"', '\\"')
        limit = max(criteria.limit, 1)

        domain_filter = ""
        if criteria.domains:
            domain_list = ", ".join(f'"{d}"' for d in criteria.domains)
            domain_filter = f"AND d.name IN [{domain_list}]"

        phase_filter = ""
        if criteria.phases:
            phase_list = ", ".join(f'"{p}"' for p in criteria.phases)
            phase_filter = f"AND ph.code IN [{phase_list}]"

        severity_filter = ""
        if criteria.severity_min is not None:
            severity_filter = f"AND c.severity >= {criteria.severity_min}"

        category_filter = ""
        if criteria.category:
            category_filter = f"AND c.category =~ '(?i){criteria.category}'"

        date_filter = ""
        if criteria.date_from:
            date_filter += f" AND ps.created_at >= datetime('{criteria.date_from}')"
        if criteria.date_to:
            date_filter += f" AND ps.created_at <= datetime('{criteria.date_to}')"

        return f"""
            // ---- Full-text hit on ProblemStatement ----
            CALL {{
                CALL db.index.fulltext.queryNodes("ps_text_index", "{safe_text}")
                YIELD node AS ps, score
                RETURN ps.id AS hit_id, score * 2.0 AS hit_score
                ORDER BY hit_score DESC LIMIT {limit * 2}
            }}
            WITH hit_id, hit_score

            // ---- Full-text hit on Content (maps back to PS) ----
            UNION
            CALL {{
                CALL db.index.fulltext.queryNodes("content_text_index", "{safe_text}")
                YIELD node AS c, score
                MATCH (sp:SubPhase)-[:HAS_CONTENT]->(c)
                MATCH (ph:Phase)-[:HAS_SUBPHASE]->(sp)
                MATCH (ps:ProblemStatement)-[:HAS_PHASE]->(ph)
                RETURN ps.id AS hit_id, score AS hit_score
                ORDER BY hit_score DESC LIMIT {limit * 2}
            }}
            WITH hit_id, max(hit_score) AS best_score

            // ---- Hydrate PS + apply structured filters ----
            MATCH (ps:ProblemStatement {{id: hit_id}})
            OPTIONAL MATCH (ps)-[:BELONGS_TO]->(d:Domain)
            OPTIONAL MATCH (ps)-[:HAS_PHASE]->(ph:Phase)
            OPTIONAL MATCH (ph)-[:HAS_SUBPHASE]->(sp:SubPhase)
            OPTIONAL MATCH (sp)-[:HAS_CONTENT]->(c:Content)
            WHERE 1=1 {domain_filter} {phase_filter} {severity_filter} {category_filter} {date_filter}

            WITH ps, best_score,
                 collect(DISTINCT d.name) AS domains,
                 collect(DISTINCT ph.code) AS phase_codes,
                 collect(DISTINCT {{
                     id: c.id, text: c.text, summary: c.summary,
                     category: c.category, severity: c.severity,
                     root_cause: c.root_cause, corrective_action: c.corrective_action,
                     model: c.model, confidence: c.confidence,
                     sub_phase: sp.name, phase_code: ph.code
                 }}) AS contents
            RETURN ps {{
                .id, .title, .text, .keywords,
                .ticket_ref, .part_number, .created_at,
                .summary, .keywords_extracted, .quality_score,
                .domain_tags, .upload_source, .ollama_processed,
                domains: domains,
                phase_codes: phase_codes,
                contents: contents
            }} AS problem_statement,
            best_score AS relevance_score
            ORDER BY best_score DESC
            LIMIT {limit}
        """


__all__ = ["QueryBuilder", "SearchCriteria"]
