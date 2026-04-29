"""Constants and environment configuration for root cause routes."""

import os

FIVE_WHY_REQUEST_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT_FIVE_WHY", "900"))
FIVE_WHY_MAX_CAUSES = int(os.getenv("FIVE_WHY_MAX_CAUSES", "4"))
FIVE_WHY_MIN_NUM_PREDICT = int(os.getenv("FIVE_WHY_MIN_NUM_PREDICT", "900"))
FIVE_WHY_MAX_NUM_PREDICT = int(os.getenv("FIVE_WHY_MAX_NUM_PREDICT", "1800"))
FIVE_WHY_TOKENS_PER_CAUSE = int(os.getenv("FIVE_WHY_TOKENS_PER_CAUSE", "300"))

ISHIKAWA_REQUEST_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT_ISHIKAWA", "900"))
ISHIKAWA_NUM_PREDICT = int(os.getenv("ISHIKAWA_NUM_PREDICT", "3600"))
ISHIKAWA_MIN_RESULTS_PER_BONE = int(os.getenv("ISHIKAWA_MIN_RESULTS_PER_BONE", "3"))

ISHIKAWA_FILL_EMPTY_CATEGORIES = os.getenv("ISHIKAWA_FILL_EMPTY_CATEGORIES", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ISHIKAWA_EMPTY_SUBCATEGORY = os.getenv("ISHIKAWA_EMPTY_SUBCATEGORY", "Needs Investigation")
ISHIKAWA_EMPTY_EVIDENCE = os.getenv(
    "ISHIKAWA_EMPTY_EVIDENCE",
    "No direct evidence supplied in model output; refine query or regenerate for deeper coverage.",
)
ISHIKAWA_DEFAULT_SEVERITY = os.getenv("ISHIKAWA_DEFAULT_SEVERITY", "Medium")

CANONICAL_BONES = [
    "Machine",
    "Method",
    "Material",
    "Man",
    "Measurement",
    "Environment",
]

BONE_ALIASES = {
    "machine": "Machine",
    "machines": "Machine",
    "machinery": "Machine",
    "equipment": "Machine",
    "method": "Method",
    "methods": "Method",
    "manufacturing": "Method",
    "process": "Method",
    "processes": "Method",
    "procedure": "Method",
    "procedures": "Method",
    "material": "Material",
    "materials": "Material",
    "rawmaterial": "Material",
    "rawmaterials": "Material",
    "measurement": "Measurement",
    "measurements": "Measurement",
    "inspection": "Measurement",
    "quality": "Measurement",
    "metrology": "Measurement",
    "people": "Man",
    "person": "Man",
    "personnel": "Man",
    "man": "Man",
    "manpower": "Man",
    "human": "Man",
    "humanfactor": "Man",
    "humanfactors": "Man",
    "operator": "Man",
    "operators": "Man",
    "workforce": "Man",
    "environment": "Environment",
    "environmental": "Environment",
    "mothernature": "Environment",
    "milieu": "Environment",
    "surroundings": "Environment",
}
