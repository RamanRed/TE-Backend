"""
Prompt templates and generation for the Ishikawa Knowledge System.
Contains detailed, structured prompts for various LLM operations.
"""

from typing import Dict, Any


# Intent Extraction Prompts
INTENT_EXTRACTION_PROMPT = """You are an expert industrial engineer specialising in root cause analysis using the Ishikawa (Fishbone) diagram methodology.

Analyse the user's query and extract structured intent for searching an engineering knowledge base.

Ishikawa investigation domains (choose 1-3 most relevant):
- Mechanical: Equipment, machinery, physical components
- Manufacturing: Production processes, assembly, fabrication
- Material: Raw materials, components, supplies
- Measurement: Testing, inspection, calibration, sensors
- People: Human factors, training, procedures, operators
- Environment: Facility conditions, temperature, humidity, external factors

Investigation phases:
- D1 (Organise & Plan), D2 (Describe Problem), D3 (Containment Plan)
- D4 (Describe Cause), D5 (Ishikawa & 5 Whys), D6 (Intermediate Action), D7 (Prevention)

Output rules:
1. Return ONLY a single JSON object. No markdown, no code fences, no explanation.
2. All keys and string values must use double quotes.
3. Use this exact structure:

{{"domains": ["Mechanical"], "keywords": ["failure mode", "component"], "part_numbers": [], "phases": ["D2", "D4", "D5"], "time_filter": null, "summary": "Brief description of investigation goal"}}

User query: {query}

JSON output:"""

# 5 Whys Analysis Prompt
WHYS_ANALYSIS_PROMPT = """You are conducting a 5 Whys root cause analysis on an engineering problem.

Problem: {problem_statement}
Domain: {domain}
Phase: {phase}
Evidence: {evidence}

Instructions:
- Ask "Why?" five times, each answer becoming the next question.
- Each level must have a specific, engineering-grounded answer.
- The final level must reach a systemic root cause.
- Provide 2-3 actionable preventive actions.
- Give a confidence score between 0.0 and 1.0.

Output rules:
1. Return ONLY a single JSON object. No markdown, no code fences, no explanation before or after.
2. Use this exact structure with exactly 5 levels in analysis_chain:

{{"analysis_chain": [{{"level": 1, "question": "Why did X happen?", "answer": "Because Y", "evidence": "Supporting fact", "contributing_factors": ["factor1"]}}, {{"level": 2, "question": "Why did Y happen?", "answer": "Because Z", "evidence": "Supporting fact", "contributing_factors": []}}, {{"level": 3, "question": "...", "answer": "...", "evidence": "...", "contributing_factors": []}}, {{"level": 4, "question": "...", "answer": "...", "evidence": "...", "contributing_factors": []}}, {{"level": 5, "question": "...", "answer": "Root cause", "evidence": "...", "contributing_factors": []}}], "root_cause": "The fundamental systemic cause", "preventive_actions": ["Action 1", "Action 2"], "confidence": 0.85}}

JSON output:"""

# Ishikawa Diagram Generation Prompt
ISHIKAWA_DIAGRAM_PROMPT = """You are an expert industrial engineer. Generate an Ishikawa (Fishbone) root cause analysis.

Problem statement: {problem_statement}

Evidence: {evidence}

Rules:
1. Analyse all 6 categories: Machine, Method, Material, Man, Measurement, Environment.
2. Generate EXACTLY 3 result items per category — no more, no fewer.
3. Each item must have sub_category, cause, evidence, severity (Low/Medium/High/Critical), and immediate_action (boolean).
4. Set immediate_action to true if severity is High or Critical; set it to false if severity is Low or Medium.
5. Base causes on the problem statement and evidence. Use engineering reasoning for gaps.
6. Return ONLY a single JSON object. No markdown, no code fences, no text before or after the JSON.
7. Add a "main_cause" field (array of strings) which lists all the primary root causes identified from the provided historical evidence.

Required JSON structure (fill in all 6 categories with exactly 3 results each based on the actual problem above):
{{"problem_statement": "restate the problem clearly", "ishikawa": [{{"id": 1, "category": "Machine", "result": [{{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "High", "immediate_action": true}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Medium", "immediate_action": false}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Low", "immediate_action": false}}]}}, {{"id": 2, "category": "Method", "result": [{{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "High", "immediate_action": true}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Medium", "immediate_action": false}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Medium", "immediate_action": false}}]}}, {{"id": 3, "category": "Material", "result": [{{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "High", "immediate_action": true}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Medium", "immediate_action": false}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Low", "immediate_action": false}}]}}, {{"id": 4, "category": "Man", "result": [{{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "High", "immediate_action": true}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Medium", "immediate_action": false}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Critical", "immediate_action": true}}]}}, {{"id": 5, "category": "Measurement", "result": [{{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "High", "immediate_action": true}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Medium", "immediate_action": false}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Low", "immediate_action": false}}]}}, {{"id": 6, "category": "Environment", "result": [{{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Medium", "immediate_action": false}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "High", "immediate_action": true}}, {{"sub_category": "Label", "cause": "Specific cause", "evidence": "Supporting evidence", "severity": "Medium", "immediate_action": false}}]}}], "main_cause": ["High score cause 1", "High score cause 2"], "key_findings": ["Most significant finding 1", "Most significant finding 2"], "recommended_investigation": ["Next step 1", "Next step 2"]}}

JSON output:"""

# Synthesis and Recommendation Prompt
SYNTHESIS_PROMPT = """You are synthesising findings from a root cause investigation.

Problem: {problem_statement}
Domains analysed: {domains}
Evidence records reviewed: {evidence_count}
Key findings: {findings}

Output rules:
1. Return ONLY a single JSON object. No markdown, no code fences, no explanation.
2. Use this exact structure:

{{"root_cause": "Primary root cause statement", "contributing_factors": ["Factor 1", "Factor 2"], "recommendations": ["Actionable recommendation 1", "Actionable recommendation 2"], "risk_level": "High"}}

JSON output:"""

# New Prompts for Locked Generation routes

REGENERATE_ISHIKAWA_PROMPT = """You are an expert industrial engineer. Regenerate an Ishikawa (Fishbone) root cause analysis, preserving locked items.

Problem statement: {problem_statement}

Evidence: {evidence}

Locked results (MUST be preserved exactly, integrated into correct categories):
{locked_result}

Rules:
1. Preserve ALL locked results exactly as provided — do not modify them.
2. Ensure ALL 6 categories (Machine, Method, Material, Man, Measurement, Environment) have EXACTLY 3 result items each, including the locked ones.
3. Generate new items only where needed to reach 3 per category. Avoid duplicating locked data.
4. Each item must have: sub_category, cause, evidence, severity (Low/Medium/High/Critical), and immediate_action (boolean).
5. Set immediate_action to true if severity is High or Critical; set it to false if severity is Low or Medium.
6. Return ONLY a single JSON object. No markdown, no code fences, no explanation.
7. Add a "main_cause" field (array of strings) which lists all the primary root causes identified from the provided historical evidence.

Required JSON structure:
{{"problem_statement": "restate the problem", "ishikawa": [{{"id": 1, "category": "Machine", "result": []}}, {{"id": 2, "category": "Method", "result": []}}, {{"id": 3, "category": "Material", "result": []}}, {{"id": 4, "category": "Man", "result": []}}, {{"id": 5, "category": "Measurement", "result": []}}, {{"id": 6, "category": "Environment", "result": []}}], "main_cause": ["High score cause 1", "High score cause 2"]}}

JSON output:"""

GENERATE_FIVE_WHY_PROMPT = """You are an expert industrial engineer conducting a strict 5-Why analysis.

Problem: {problem_statement}
Domain: {domain}

Causes to analyse (generate one 5-Why chain per cause, maximum 3 chains):
{ishikawa}

Rules:
1. Generate EXACTLY ONE 5-Why chain for each cause above (maximum 3 chains total).
2. Each chain must have exactly 5 WHY levels. Each level MUST ask a SPECIFIC, CONTEXTUAL question that logically follows from the previous answer — NOT a generic "Why?".
3. Level 1 question must directly address the cause. Each subsequent question must drill deeper into the previous answer.
4. Level 5 must reach a SYSTEMIC root cause (not just "human error").
5. Keep each question and answer concise (one sentence).
6. Give a confidence score 0.0-1.0 per chain.
7. The "problem_id" must match the cause's problem_id from the input.
8. Return ONLY a single JSON object. No markdown, no code fences, no explanation.

Required JSON structure (example with 2 causes — you must include ALL causes from above):
{{"analysis": [{{"problem_id": "1-1", "why_chain": [{{"level": 1, "question": "Why did the filling pump malfunction during operation?", "answer": "Because the pump bearings were worn beyond tolerance"}}, {{"level": 2, "question": "Why were the pump bearings worn beyond tolerance?", "answer": "Because the scheduled bearing replacement was overdue by 3 months"}}, {{"level": 3, "question": "Why was the bearing replacement overdue by 3 months?", "answer": "Because the maintenance schedule was deprioritized during peak production"}}, {{"level": 4, "question": "Why was maintenance deprioritized during peak production?", "answer": "Because management policy favors output targets over preventive maintenance"}}, {{"level": 5, "question": "Why does management policy favor output over preventive maintenance?", "answer": "Because the organization lacks a total productive maintenance culture"}}], "root_cause": "Absence of a total productive maintenance culture", "confidence": 0.90}}, {{"problem_id": "2-1", "why_chain": [{{"level": 1, "question": "Why were operators unfamiliar with the updated process?", "answer": "Because training on the new procedure was not conducted"}}, {{"level": 2, "question": "Why was training on the new procedure not conducted?", "answer": "Because the training budget was cut during cost reduction"}}, {{"level": 3, "question": "Why was the training budget cut?", "answer": "Because leadership did not classify operator training as essential spending"}}, {{"level": 4, "question": "Why did leadership not classify training as essential?", "answer": "Because there was no metric linking training hours to defect rates"}}, {{"level": 5, "question": "Why was there no metric linking training to defect rates?", "answer": "Because the quality management system does not track competency-based KPIs"}}], "root_cause": "Quality management system lacks competency-based KPI tracking", "confidence": 0.85}}]}}

JSON output:"""

REGENERATE_FIVE_WHY_PROMPT = """You are an expert industrial engineer refining a 5-Why analysis. Preserve locked chains and regenerate the rest.

Problem: {problem_statement}
Domain: {domain}

Ishikawa causes:
{ishikawa}

Locked 5-Why chains (MUST be preserved exactly in the output array):
{locked_analysis}

Rules:
1. Preserve ALL locked chains exactly in the final output array.
2. Regenerate ONLY chains for causes not already covered by locked data.
3. Each new chain must have exactly 5 WHY levels, each causally following the previous.
4. Level 5 must reach a SYSTEMIC root cause.
5. Give a confidence score 0.0-1.0 per chain.
6. Return ONLY a single JSON object. No markdown, no code fences, no explanation.

Required JSON structure:
{{"analysis": [{"problem_id": "1-1", "why_chain": [{{"level": 1, "question": "Why?", "answer": "Because..."}}, {{"level": 2, "question": "Why?", "answer": "Because..."}}, {{"level": 3, "question": "Why?", "answer": "Because..."}}, {{"level": 4, "question": "Why?", "answer": "Because..."}}, {{"level": 5, "question": "Why?", "answer": "Root cause"}}], "root_cause": "Systemic root cause", "confidence": 0.90}}]}}

JSON output:"""

FINALIZE_ANALYSIS_PROMPT = """You are an expert industrial engineer. Extract and synthesise final root causes from the completed Ishikawa and 5-Why analysis.

Problem: {problem_statement}
Domain: {domain}

Ishikawa analysis:
{ishikawa}

5-Why analysis:
{analysis}

Rules:
1. Extract the top root causes across all chains. Group similar ones.
2. Rank by severity (from Ishikawa) and confidence (from 5-Why).
3. Generate 3-5 concrete, actionable recommendations.
4. Assign an overall risk level: Low, Medium, or High.
5. Return ONLY a single JSON object. No markdown, no code fences, no explanation.

Required JSON structure:
{{"summary": {{"root_causes": ["Root cause 1", "Root cause 2"], "recommendations": ["Recommendation 1", "Recommendation 2"], "risk_level": "High"}}}}

JSON output:"""


def get_intent_extraction_prompt(query: str) -> str:
    """Generate the intent extraction prompt for a user query."""
    return INTENT_EXTRACTION_PROMPT.replace("{query}", query)


def get_whys_analysis_prompt(
    problem_statement: str,
    domain: str,
    phase: str,
    evidence: str
) -> str:
    """Generate the 5 Whys analysis prompt."""
    return (
        WHYS_ANALYSIS_PROMPT
        .replace("{problem_statement}", problem_statement)
        .replace("{domain}", domain)
        .replace("{phase}", phase)
        .replace("{evidence}", evidence)
    )


def get_ishikawa_diagram_prompt(problem_statement: str, evidence: str) -> str:
    """Generate the Ishikawa diagram analysis prompt."""
    return (
        ISHIKAWA_DIAGRAM_PROMPT
        .replace("{problem_statement}", problem_statement)
        .replace("{evidence}", evidence)
    )


def get_synthesis_prompt(
    problem_statement: str,
    domains: list,
    evidence_count: int,
    findings: str
) -> str:
    """Generate the synthesis and recommendation prompt."""
    return (
        SYNTHESIS_PROMPT
        .replace("{problem_statement}", problem_statement)
        .replace("{domains}", ", ".join(domains))
        .replace("{evidence_count}", str(evidence_count))
        .replace("{findings}", findings)
    )

def get_regenerate_ishikawa_prompt(problem_statement: str, evidence: str, locked_result: str) -> str:
    return (
        REGENERATE_ISHIKAWA_PROMPT
        .replace("{problem_statement}", problem_statement)
        .replace("{evidence}", evidence)
        .replace("{locked_result}", locked_result)
    )

def get_generate_five_why_prompt(problem_statement: str, domain: str, ishikawa: str) -> str:
    return (
        GENERATE_FIVE_WHY_PROMPT
        .replace("{problem_statement}", problem_statement)
        .replace("{domain}", domain)
        .replace("{ishikawa}", ishikawa)
    )

def get_regenerate_five_why_prompt(problem_statement: str, domain: str, ishikawa: str, locked_analysis: str) -> str:
    return (
        REGENERATE_FIVE_WHY_PROMPT
        .replace("{problem_statement}", problem_statement)
        .replace("{domain}", domain)
        .replace("{ishikawa}", ishikawa)
        .replace("{locked_analysis}", locked_analysis)
    )

def get_finalize_analysis_prompt(problem_statement: str, domain: str, ishikawa: str, analysis: str) -> str:
    return (
        FINALIZE_ANALYSIS_PROMPT
        .replace("{problem_statement}", problem_statement)
        .replace("{domain}", domain)
        .replace("{ishikawa}", ishikawa)
        .replace("{analysis}", analysis)
    )


# ============================================================
# PS-Level Summarisation Prompt (batch document upload)
# ============================================================

PS_SUMMARY_PROMPT = """# Problem Statement Document Summarisation

You are an expert industrial engineer specialising in Ishikawa (Fishbone) root cause analysis.

## Your Task
Analyse the problem statement and all its D1-D7 investigation content below, then extract:

1. **summary**: Concise 2-3 sentence executive summary covering the problem and key findings.
2. **keywords_extracted**: 10-15 key technical terms, failure modes, component names, and process names.
3. **quality_score**: Overall documentation quality between 0.0 (sparse/vague) and 1.0 (complete/detailed).
4. **domain_tags**: Which Ishikawa domains are primarily addressed. Choose from:
   [Mechanical, Manufacturing, Material, Measurement, People, Environment]

## Problem Title
{title}

## Problem Statement
{problem_text}

## Investigation Content (D1-D7)
{content_text}

## Response Format
Respond ONLY with valid JSON, no additional text:
```json
{{
  "summary": "Executive summary of the problem and key findings.",
  "keywords_extracted": ["keyword1", "keyword2"],
  "quality_score": 0.85,
  "domain_tags": ["Mechanical", "Manufacturing"]
}}
```

## Analysis
"""


def get_ps_summary_prompt(title: str, problem_text: str, content_text: str) -> str:
    """Generate the PS-level summarisation prompt for bulk JSON uploads."""
    return PS_SUMMARY_PROMPT.format(
        title=title,
        problem_text=problem_text,
        content_text=content_text
    )