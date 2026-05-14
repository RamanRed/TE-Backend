"""
Migration: Normalize existing Supabase records to current JSON structure.

Fixes:
  saved_ishikawa.data   → ensure list of {id, category, result:[{cause, evidence, severity, sub_category}]}
  saved_ishikawa.main_cause → ensure [] not NULL
  saved_five_whys.data  → ensure list of {problem_id, why_chain:[{level,question,answer}], root_cause, confidence}
  saved_five_whys.root_causes → rebuild from data if empty
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.utils.config import load_config
from src.database.prisma_client import get_prisma

load_config()
db = get_prisma()

# ── helpers ──────────────────────────────────────────────────────────────────

def safe_parse(val, fallback):
    if val is None:
        return fallback
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return fallback
    return fallback


def normalize_ishikawa_data(data):
    """Ensure ishikawa data is list[{id, category, result:[...]}]"""
    if not isinstance(data, list):
        data = []
    normalized = []
    for i, cat in enumerate(data):
        if not isinstance(cat, dict):
            continue
        results = cat.get("result", [])
        if not isinstance(results, list):
            results = []
        norm_results = []
        for item in results:
            if not isinstance(item, dict):
                continue
            norm_results.append({
                "sub_category": item.get("sub_category") or item.get("sub_category") or "",
                "cause":        item.get("cause") or "",
                "evidence":     item.get("evidence") or "",
                "severity":     item.get("severity") or "Medium",
                "immediate_action": bool(item.get("immediate_action", False)),
            })
        normalized.append({
            "id":       cat.get("id", i + 1),
            "category": cat.get("category", f"Category {i+1}"),
            "result":   norm_results,
        })
    return normalized


def normalize_five_why_data(data):
    """Ensure 5-why data is list[{problem_id, why_chain:[...], root_cause, confidence}]"""
    if isinstance(data, dict):
        # Old format: {"analysis": [...]}
        data = data.get("analysis", [data]) if "analysis" in data else [data]
    if not isinstance(data, list):
        data = []
    normalized = []
    for i, chain in enumerate(data):
        if not isinstance(chain, dict):
            continue
        why_chain = chain.get("why_chain", [])
        if not isinstance(why_chain, list):
            why_chain = []
        norm_chain = []
        for step in why_chain:
            if not isinstance(step, dict):
                continue
            norm_chain.append({
                "level":    int(step.get("level", 0)),
                "question": step.get("question") or "",
                "answer":   step.get("answer") or "",
            })
        normalized.append({
            "problem_id": str(chain.get("problem_id", f"{i+1}-1")),
            "why_chain":  norm_chain,
            "root_cause": chain.get("root_cause") or "",
            "confidence": float(chain.get("confidence", 0.0)),
        })
    return normalized


# ── migrate saved_ishikawa ───────────────────────────────────────────────────
print("\n── Migrating saved_ishikawa ──")
ishikawa_rows = db.savedishikawa.find_many()
print(f"Total rows: {len(ishikawa_rows)}")

ishi_fixed = 0
for row in ishikawa_rows:
    raw = safe_parse(row.data, [])
    normalized = normalize_ishikawa_data(raw)
    main_cause = row.mainCause if row.mainCause else []

    needs_update = (
        json.dumps(raw) != json.dumps(normalized) or
        row.mainCause is None
    )

    if needs_update:
        db.savedishikawa.update(
            where={"id": row.id},
            data={
                "data": json.dumps(normalized),
                "mainCause": main_cause,
            }
        )
        ishi_fixed += 1
        print(f"  Fixed ishikawa row: {row.id} (cats={len(normalized)}, main_cause={len(main_cause)})")

print(f"Done: {ishi_fixed}/{len(ishikawa_rows)} rows updated.\n")


# ── migrate saved_five_whys ──────────────────────────────────────────────────
print("── Migrating saved_five_whys ──")
fw_rows = db.savedfivewhys.find_many()
print(f"Total rows: {len(fw_rows)}")

fw_fixed = 0
for row in fw_rows:
    raw = safe_parse(row.data, [])
    normalized = normalize_five_why_data(raw)

    # Rebuild root_causes from normalized data if missing/empty
    root_causes = row.rootCauses or []
    if not root_causes:
        root_causes = [c["root_cause"] for c in normalized if c.get("root_cause")]

    needs_update = (
        json.dumps(raw) != json.dumps(normalized) or
        not row.rootCauses or
        len(row.rootCauses) != len([c for c in normalized if c.get("root_cause")])
    )

    if needs_update:
        db.savedfivewhys.update(
            where={"id": row.id},
            data={
                "data":       json.dumps(normalized),
                "chainCount": len(normalized),
                "rootCauses": root_causes,
            }
        )
        fw_fixed += 1
        print(f"  Fixed five_whys row: {row.id} (chains={len(normalized)}, roots={len(root_causes)})")

print(f"Done: {fw_fixed}/{len(fw_rows)} rows updated.\n")

print("✅ Migration complete.")
