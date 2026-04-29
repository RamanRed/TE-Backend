"""High-level LLM service for analysis workflows."""

from __future__ import annotations

import ast
import json
import os
from typing import Any

import yaml

from .client import LLMResponse, OllamaClient
from .json_parser import cleanup_json_candidate, extract_json_candidate
from ..utils.config import LLMConfig
from ..utils.logging import get_logger

logger = get_logger(__name__)


class LLMService:
    """High-level service for LLM operations."""

    ISHIKAWA_NUM_PREDICT = int(os.environ.get("ISHIKAWA_NUM_PREDICT", "3600"))
    ISHIKAWA_REQUEST_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT_ISHIKAWA", "900"))

    def __init__(self, config: LLMConfig):
        self.client = OllamaClient(config)
        self.config = config

    def ensure_model_available(self) -> bool:
        """Ensure the configured model is available, pulling it if required."""
        if not self.client.check_model_availability():
            logger.info("Model %s not available, attempting to pull", self.config.model)
            return self.client.pull_model()
        return True

    def _repair_json_with_model(self, malformed_json: str, output_name: str) -> Any:
        """Ask the model once to rewrite malformed JSON into strict valid JSON."""
        repair_prompt = (
            f"Rewrite the following {output_name} payload into strict valid JSON. "
            "Return only JSON with no explanation, no markdown, and no code fences.\n\n"
            f"{malformed_json[:12000]}"
        )

        repaired = self.client.generate(repair_prompt, temperature=0.0)
        if not repaired.success:
            raise RuntimeError(f"Failed to repair {output_name} JSON: {repaired.error_message}")

        repaired_candidate = cleanup_json_candidate(extract_json_candidate(repaired.content))
        return json.loads(repaired_candidate)

    def _parse_json_response(self, content: str, output_name: str) -> Any:
        """Parse JSON response robustly with tolerant fallbacks and one repair pass."""
        candidate = extract_json_candidate(content)

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        cleaned = cleanup_json_candidate(candidate)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as parse_error:
            try:
                yaml_loaded = yaml.safe_load(cleaned)
                if isinstance(yaml_loaded, (dict, list)):
                    logger.info("Recovered %s payload via YAML tolerant parsing", output_name)
                    return yaml_loaded
            except Exception:
                pass

            try:
                literal_loaded = ast.literal_eval(cleaned)
                if isinstance(literal_loaded, (dict, list)):
                    logger.info("Recovered %s payload via literal_eval tolerant parsing", output_name)
                    return literal_loaded
            except Exception:
                pass

            logger.warning(
                "Initial parse failed for %s; attempting one JSON repair pass: %s",
                output_name,
                parse_error,
            )
            return self._repair_json_with_model(cleaned, output_name)

    def _generate_json(
        self,
        prompt: str,
        output_name: str,
        *,
        temperature: float,
        request_timeout: float | None = None,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Run a prompt that is expected to return JSON."""
        response: LLMResponse = self.client.generate(
            prompt,
            temperature=temperature,
            request_timeout=request_timeout,
            options=options or {},
        )
        if not response.success:
            raise RuntimeError(f"{output_name} failed: {response.error_message}")
        return self._parse_json_response(response.content, output_name)

    def extract_intent(self, query: str) -> dict[str, Any]:
        """Extract intent from a user query."""
        from .prompts import get_intent_extraction_prompt

        prompt = get_intent_extraction_prompt(query)
        return self._generate_json(prompt, "Intent extraction", temperature=0.1)

    def perform_whys_analysis(
        self,
        problem_statement: str,
        domain: str,
        phase: str,
        evidence: str,
    ) -> dict[str, Any]:
        """Perform 5 Whys analysis."""
        from .prompts import get_whys_analysis_prompt

        prompt = get_whys_analysis_prompt(
            problem_statement=problem_statement,
            domain=domain,
            phase=phase,
            evidence=evidence,
        )
        return self._generate_json(prompt, "5 Whys analysis", temperature=0.3)

    def generate_ishikawa_diagram(self, problem_statement: str, evidence: str) -> dict[str, Any]:
        """Generate Ishikawa diagram analysis."""
        from .prompts import get_ishikawa_diagram_prompt

        prompt = get_ishikawa_diagram_prompt(
            problem_statement=problem_statement,
            evidence=evidence,
        )
        return self._generate_json(
            prompt,
            "Ishikawa",
            temperature=0.2,
            request_timeout=self.ISHIKAWA_REQUEST_TIMEOUT,
            options={"num_predict": self.ISHIKAWA_NUM_PREDICT},
        )

    def synthesize_findings(
        self,
        problem_statement: str,
        domains: list[str],
        evidence_count: int,
        findings: str,
    ) -> dict[str, Any]:
        """Synthesize findings into recommendations."""
        from .prompts import get_synthesis_prompt

        prompt = get_synthesis_prompt(
            problem_statement=problem_statement,
            domains=domains,
            evidence_count=evidence_count,
            findings=findings,
        )
        return self._generate_json(prompt, "Synthesis", temperature=0.1)

    def summarize_problem_statement(
        self,
        title: str,
        problem_text: str,
        content_text: str,
    ) -> dict[str, Any]:
        """Run PS-level summarisation on a full structured problem statement document."""
        from .prompts import get_ps_summary_prompt

        prompt = get_ps_summary_prompt(
            title=title,
            problem_text=problem_text,
            content_text=content_text,
        )
        return self._generate_json(prompt, "PS summary", temperature=0.1)
