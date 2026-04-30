"""
Intent extraction and analysis module.
Handles user query processing, intent extraction, and analysis coordination.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from .service import LLMService
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Intent:
    """Structured intent extracted from user query."""
    domains: List[str]
    keywords: List[str]
    part_numbers: List[str]
    phases: List[str]
    time_filter: Optional[str]
    summary: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Intent':
        """Create Intent from dictionary."""
        return cls(
            domains=data.get('domains', []),
            keywords=data.get('keywords', []),
            part_numbers=data.get('part_numbers', []),
            phases=data.get('phases', []),
            time_filter=data.get('time_filter'),
            summary=data.get('summary', '')
        )


@dataclass
class AnalysisResult:
    """Result of root cause analysis."""
    root_cause: str
    contributing_factors: List[str]
    systemic_issues: List[str]
    immediate_actions: List[Dict[str, Any]]
    preventive_measures: List[Dict[str, Any]]
    confidence_level: float
    recommendations: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AnalysisResult':
        """Create AnalysisResult from dictionary."""
        return cls(
            root_cause=data.get('root_cause', ''),
            contributing_factors=data.get('contributing_factors', []),
            systemic_issues=data.get('systemic_issues', []),
            immediate_actions=data.get('immediate_actions', []),
            preventive_measures=data.get('preventive_measures', []),
            confidence_level=data.get('confidence_level', 0.0),
            recommendations=data.get('recommendations', [])
        )


class IntentExtractor:
    """Handles intent extraction from user queries."""

    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    def extract_intent(self, query: str) -> Intent:
        """
        Extract structured intent from user query.

        Args:
            query: Raw user query string

        Returns:
            Intent: Structured intent with domains, keywords, etc.

        Raises:
            RuntimeError: If intent extraction fails
        """
        logger.info(f"Extracting intent from query: {query[:100]}...")

        try:
            raw_intent = self.llm_service.extract_intent(query)
            intent = Intent.from_dict(raw_intent)

            logger.info(
                "Extracted intent: domains=%s, keywords=%s, phases=%s",
                intent.domains, intent.keywords, intent.phases,
            )
            logger.debug(f"Intent summary: {intent.summary}")

            return intent

        except Exception as e:
            logger.error(f"Intent extraction failed: {e}")
            raise RuntimeError(f"Failed to extract intent: {e}")

    def validate_intent(self, intent: Intent) -> List[str]:
        """
        Validate extracted intent for completeness and consistency.

        Args:
            intent: Intent to validate

        Returns:
            List of validation warnings/issues
        """
        warnings = []

        if not intent.domains:
            warnings.append("No investigation domains identified")

        if not intent.keywords:
            warnings.append("No technical keywords extracted")

        if not intent.phases:
            warnings.append("No investigation phases selected")

        if not intent.summary:
            warnings.append("No summary provided")

        # Check for valid domains
        valid_domains = {
            "Mechanical", "Manufacturing", "Material",
            "Measurement", "People", "Environment"
        }
        invalid_domains = set(intent.domains) - valid_domains
        if invalid_domains:
            warnings.append(f"Invalid domains: {invalid_domains}")

        # Check for valid phases
        valid_phases = {f"D{i}" for i in range(1, 8)}
        invalid_phases = set(intent.phases) - valid_phases
        if invalid_phases:
            warnings.append(f"Invalid phases: {invalid_phases}")

        return warnings


class AnalysisCoordinator:
    """Coordinates root cause analysis operations."""

    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    def perform_whys_analysis(
        self,
        problem_statement: str,
        domain: str,
        phase: str,
        evidence: str
    ) -> Dict[str, Any]:
        """
        Perform 5 Whys analysis for a specific problem.

        Args:
            problem_statement: Clear description of the problem
            domain: Primary investigation domain
            phase: Investigation phase
            evidence: Supporting evidence and context

        Returns:
            Analysis results dictionary
        """
        logger.info(f"Performing 5 Whys analysis for domain: {domain}, phase: {phase}")

        try:
            result = self.llm_service.perform_whys_analysis(
                problem_statement=problem_statement,
                domain=domain,
                phase=phase,
                evidence=evidence
            )

            logger.info(f"5 Whys analysis completed with {len(result.get('analysis_chain', []))} levels")
            return result

        except Exception as e:
            logger.error(f"5 Whys analysis failed: {e}")
            raise RuntimeError(f"5 Whys analysis failed: {e}")

    def generate_ishikawa_diagram(
        self,
        problem_statement: str,
        evidence: str
    ) -> Dict[str, Any]:
        """
        Generate Ishikawa (Fishbone) diagram analysis.

        Args:
            problem_statement: Problem to analyze
            evidence: Available evidence and data

        Returns:
            Fishbone diagram analysis results
        """
        logger.info("Generating Ishikawa diagram analysis")

        try:
            result = self.llm_service.generate_ishikawa_diagram(
                problem_statement=problem_statement,
                evidence=evidence
            )

            bones_count = sum(len(bones) for bones in result.get('bones', {}).values())
            logger.info(f"Ishikawa diagram generated with {bones_count} total causes")
            return result

        except Exception as e:
            logger.error(f"Ishikawa diagram generation failed: {e}")
            raise RuntimeError(f"Ishikawa diagram generation failed: {e}")

    def synthesize_findings(
        self,
        problem_statement: str,
        domains: List[str],
        evidence_count: int,
        findings: str
    ) -> AnalysisResult:
        """
        Synthesize multiple analysis findings into comprehensive recommendations.

        Args:
            problem_statement: Original problem statement
            domains: Investigation domains covered
            evidence_count: Number of evidence records reviewed
            findings: Summary of findings from various analyses

        Returns:
            Synthesized analysis result
        """
        logger.info(f"Synthesizing findings from {len(domains)} domains, {evidence_count} evidence records")

        try:
            raw_result = self.llm_service.synthesize_findings(
                problem_statement=problem_statement,
                domains=domains,
                evidence_count=evidence_count,
                findings=findings
            )

            result = AnalysisResult.from_dict(raw_result)

            logger.info(f"Synthesis completed with confidence: {result.confidence_level}")
            logger.info(f"Identified root cause: {result.root_cause[:100]}...")

            return result

        except Exception as e:
            logger.error(f"Findings synthesis failed: {e}")
            raise RuntimeError(f"Findings synthesis failed: {e}")


class AnalysisPipeline:
    """Complete analysis pipeline from intent extraction to final recommendations."""

    def __init__(self, llm_service: LLMService):
        self.intent_extractor = IntentExtractor(llm_service)
        self.analysis_coordinator = AnalysisCoordinator(llm_service)

    def analyze_query(self, query: str) -> Dict[str, Any]:
        """
        Complete analysis pipeline for a user query.

        Args:
            query: User query string

        Returns:
            Complete analysis results
        """
        logger.info("Starting complete analysis pipeline")

        # Step 1: Extract intent
        intent = self.intent_extractor.extract_intent(query)

        # Step 2: Validate intent
        validation_warnings = self.intent_extractor.validate_intent(intent)
        if validation_warnings:
            logger.warning(f"Intent validation warnings: {validation_warnings}")

        # Step 3: Perform analyses based on intent
        results = {
            "intent": {
                "domains": intent.domains,
                "keywords": intent.keywords,
                "part_numbers": intent.part_numbers,
                "phases": intent.phases,
                "time_filter": intent.time_filter,
                "summary": intent.summary
            },
            "validation_warnings": validation_warnings,
            "analyses": {}
        }

        # Perform 5 Whys if phases include D5
        if "D5" in intent.phases:
            try:
                whys_result = self.analysis_coordinator.perform_whys_analysis(
                    problem_statement=intent.summary,
                    domain=intent.domains[0] if intent.domains else "General",
                    phase="D5",
                    evidence=f"Keywords: {', '.join(intent.keywords)}"
                )
                results["analyses"]["whys"] = whys_result
            except Exception as e:
                logger.error(f"5 Whys analysis failed in pipeline: {e}")
                results["analyses"]["whys_error"] = str(e)

        # Generate Ishikawa diagram if multiple domains or complex problem
        if len(intent.domains) > 1 or len(intent.keywords) > 5:
            try:
                ishikawa_result = self.analysis_coordinator.generate_ishikawa_diagram(
                    problem_statement=intent.summary,
                    evidence=f"Domains: {', '.join(intent.domains)}, Keywords: {', '.join(intent.keywords)}"
                )
                results["analyses"]["ishikawa"] = ishikawa_result
            except Exception as e:
                logger.error(f"Ishikawa analysis failed in pipeline: {e}")
                results["analyses"]["ishikawa_error"] = str(e)

        # Synthesize findings if we have analysis results
        if results["analyses"]:
            try:
                synthesis = self.analysis_coordinator.synthesize_findings(
                    problem_statement=intent.summary,
                    domains=intent.domains,
                    evidence_count=len(intent.keywords),  # Simplified
                    findings=str(results["analyses"])
                )
                results["synthesis"] = {
                    "root_cause": synthesis.root_cause,
                    "contributing_factors": synthesis.contributing_factors,
                    "systemic_issues": synthesis.systemic_issues,
                    "immediate_actions": synthesis.immediate_actions,
                    "preventive_measures": synthesis.preventive_measures,
                    "confidence_level": synthesis.confidence_level,
                    "recommendations": synthesis.recommendations
                }
            except Exception as e:
                logger.error(f"Synthesis failed in pipeline: {e}")
                results["synthesis_error"] = str(e)

        logger.info("Analysis pipeline completed")
        return results
