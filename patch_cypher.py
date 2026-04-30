"""
Fix Neo4j Cypher UNION ALL syntax error in both query functions.

Root cause: Cypher UNION/UNION ALL requires both sides to be complete
independent queries with identical return columns. You cannot use UNION ALL
between two CALL{} sub-queries inside a sequential pipeline.

Fix: use two sequential CALL{} subqueries, each collecting hits into a list,
then merge the lists with +, UNWIND, and aggregate with max(score).
"""
import pathlib, ast

qb_path = pathlib.Path(r"src\database\query_builder.py")
lines = qb_path.read_text(encoding="utf-8").splitlines(keepends=True)
total = len(lines)
print(f"Total lines: {total}")

# ── Locate build_fulltext_search_query (lines 155-253, 0-indexed 154-252) ──
# ── Locate build_advanced_search_query (lines 524+, 0-indexed 523+)       ──
ft_start = ft_end = adv_start = adv_end = None
for i, l in enumerate(lines):
    stripped = l.strip()
    if "def build_fulltext_search_query(" in l:
        ft_start = i
    elif ft_start is not None and ft_end is None and stripped.startswith("def "):
        ft_end = i
    if "def build_advanced_search_query(" in l:
        adv_start = i
    elif adv_start is not None and adv_end is None and stripped.startswith("def ") and i > adv_start:
        adv_end = i

if adv_end is None:
    adv_end = total  # last function in file

print(f"fulltext:  lines {ft_start+1}-{ft_end}")
print(f"advanced:  lines {adv_start+1}-{adv_end}")

# ════════════════════════════════════════════════════════════════
# NEW build_fulltext_search_query
# Uses two sequential CALL{} + collect() lists, then UNWIND+max
# ════════════════════════════════════════════════════════════════
NEW_FULLTEXT = """\
    def build_fulltext_search_query(
        self,
        search_text: str,
        limit: int = 50,
        min_score: float = 0.5,
    ) -> str:
        \"\"\"
        Relevance-gated full-text search across ProblemStatement and Content indexes.

        Strategy:
        - Builds a proper Lucene OR+fuzzy query so every keyword contributes to score.
        - Two sequential CALL{} subqueries (one per index) each collect scored hits
          into a list, avoiding the Cypher UNION ALL column-name restriction.
        - The two lists are merged with +, UNWINDed, and deduplicated by PS id
          keeping the max(score) so LIMIT cuts after relevance ranking, not before.

        Args:
            search_text: Free-text query (plain words, not Lucene syntax)
            limit:       Maximum results returned after score filtering
            min_score:   Minimum Lucene relevance score (default 0.5)
        \"\"\"
        terms = [t.strip() for t in search_text.split() if t.strip()]
        lucene_query = " OR ".join(f"{t}~" for t in terms) if terms else search_text
        safe_lucene = lucene_query.replace('"', '\\\\"')
        candidate_limit = limit * 5

        query = f\"\"\"
            // Phase 1: collect scored hits from ProblemStatement index
            CALL {{
                CALL db.index.fulltext.queryNodes("ps_text_index", "{safe_lucene}")
                YIELD node AS ps, score
                WHERE score >= {min_score}
                RETURN ps.id AS ps_id, ps.title AS title,
                       ps.text AS text, ps.summary AS summary,
                       score AS hit_score
                ORDER BY hit_score DESC
                LIMIT {candidate_limit}
            }}
            WITH collect({{ps_id: ps_id, title: title, text: text,
                          summary: summary, score: hit_score}}) AS ps_hits

            // Phase 2: collect scored hits from Content index, mapped back to PS
            CALL {{
                CALL db.index.fulltext.queryNodes("content_text_index", "{safe_lucene}")
                YIELD node AS c, score
                WHERE score >= {min_score}
                MATCH (sp:SubPhase)-[:HAS_CONTENT]->(c)
                MATCH (ph:Phase)-[:HAS_SUBPHASE]->(sp)
                MATCH (ps:ProblemStatement)-[:HAS_PHASE]->(ph)
                RETURN ps.id AS ps_id, ps.title AS title,
                       ps.text AS text, ps.summary AS summary,
                       score AS hit_score
                ORDER BY hit_score DESC
                LIMIT {candidate_limit}
            }}
            WITH ps_hits,
                 collect({{ps_id: ps_id, title: title, text: text,
                           summary: summary, score: hit_score}}) AS content_hits

            // Phase 3: merge, deduplicate by PS id, keep best score
            WITH ps_hits + content_hits AS all_hits
            UNWIND all_hits AS hit
            WITH hit.ps_id AS id,
                 hit.title   AS title,
                 hit.text    AS text,
                 hit.summary AS summary,
                 max(hit.score) AS score
            WHERE id IS NOT NULL
            RETURN id, title, text, summary, score
            ORDER BY score DESC
            LIMIT {limit}
        \"\"\"
        self.logger.debug(
            "Built relevance-filtered full-text query for %r | lucene=%r | min_score=%.2f | limit=%d",
            search_text, safe_lucene, min_score, limit,
        )
        return query

"""

# ════════════════════════════════════════════════════════════════
# NEW build_advanced_search_query
# Same sequential CALL{} collect pattern, then UNWIND+hydrate
# ════════════════════════════════════════════════════════════════
NEW_ADVANCED = """\
    def build_advanced_search_query(self, search_text: str, criteria: SearchCriteria) -> str:
        \"\"\"
        High-impact search combining:
          - Full-text Lucene scoring (OR + fuzzy terms) via ps_text_index + content_text_index
          - Two sequential CALL{} subqueries (avoids Cypher UNION column-name restriction)
          - Minimum relevance score gate before structured filters
          - Domain / phase / severity / date / category structured filters
          - Deduplication by PS id keeping max(score)
          - Returns relevance-ranked PS objects

        Args:
            search_text:  Free-text query (plain words -- Lucene syntax built internally)
            criteria:     Additional structured filters
        \"\"\"
        terms = [t.strip() for t in search_text.split() if t.strip()]
        lucene_query = " OR ".join(f"{t}~" for t in terms) if terms else search_text
        safe_text = lucene_query.replace('"', '\\\\"')

        limit = max(criteria.limit, 1)
        candidate_limit = limit * 5
        min_score = 0.3

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

        return f\"\"\"
            // Phase 1: collect scored hits from ProblemStatement index
            CALL {{
                CALL db.index.fulltext.queryNodes("ps_text_index", "{safe_text}")
                YIELD node AS ps, score
                WHERE score >= {min_score}
                RETURN ps.id AS hit_id, score * 2.0 AS hit_score
                ORDER BY hit_score DESC LIMIT {candidate_limit}
            }}
            WITH collect({{id: hit_id, score: hit_score}}) AS ps_hits

            // Phase 2: collect scored hits from Content index, mapped back to PS
            CALL {{
                CALL db.index.fulltext.queryNodes("content_text_index", "{safe_text}")
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

            // Phase 3: merge, deduplicate by PS id, keep best score
            WITH ps_hits + content_hits AS all_hits
            UNWIND all_hits AS hit
            WITH hit.id AS hit_id, max(hit.score) AS best_score
            WHERE hit_id IS NOT NULL

            // Phase 4: hydrate PS + apply structured filters
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
        \"\"\"
"""

# Assemble patched file
# Sections: [0..ft_start) + NEW_FULLTEXT + [ft_end..adv_start) + NEW_ADVANCED + [adv_end..]
before_ft   = "".join(lines[:ft_start])
between     = "".join(lines[ft_end:adv_start])
after_adv   = "".join(lines[adv_end:])

patched = before_ft + NEW_FULLTEXT + between + NEW_ADVANCED + after_adv
qb_path.write_text(patched, encoding="utf-8")

# Syntax check
try:
    ast.parse(qb_path.read_text(encoding="utf-8"))
    print("Syntax OK: query_builder.py")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    raise SystemExit(1)

print("Done. Both query functions patched with sequential CALL{} collect pattern.")
