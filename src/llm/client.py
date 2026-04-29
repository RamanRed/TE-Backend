"""Low-level client for interacting with Ollama-compatible APIs."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests

from ..utils.config import LLMConfig
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""

    content: str
    raw_response: dict[str, Any]
    success: bool
    error_message: str | None = None
    tokens_used: int | None = None
    response_time: float | None = None


class OllamaClient:
    """Client for interacting with the Ollama API."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.model = config.model
        self.timeout = config.timeout
        self.max_retries = getattr(config, "max_retries", 3)
        self.num_gpu = getattr(config, "num_gpu", -1)
        self.num_thread = getattr(config, "num_thread", 0) or (os.cpu_count() or 4)

        logger.info(
            "Initialized Ollama client for model %s (num_gpu=%s, num_thread=%s)",
            self.model,
            self.num_gpu,
            self.num_thread,
        )

    def _make_request(
        self,
        endpoint: str,
        payload: dict[str, Any],
        request_timeout: float | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the Ollama API with retries."""
        url = f"{self.base_url}/{endpoint}"
        timeout = request_timeout if request_timeout is not None else self.timeout

        for attempt in range(self.max_retries):
            try:
                logger.debug("Making request to %s (attempt %s)", url, attempt + 1)
                response = requests.post(url, json=payload, timeout=timeout)
                response.raise_for_status()
                result = response.json()
                logger.debug("Request successful: %s chars", len(result.get("response", "")))
                return result
            except requests.exceptions.RequestException as exc:
                logger.warning("Request attempt %s failed: %s", attempt + 1, exc)
                if attempt == self.max_retries - 1:
                    raise

        raise RuntimeError(f"Failed after {self.max_retries} attempts")

    def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Generate text using the configured model."""
        try:
            start_time = time.time()
            request_timeout = kwargs.pop("request_timeout", None)
            merged_options = {
                "num_gpu": self.num_gpu,
                "num_thread": self.num_thread,
                **kwargs.pop("options", {}),
            }
            payload_generate = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": merged_options,
                **kwargs,
            }

            endpoint = "api/generate"
            fallback_codes = {404, 500}

            try:
                result = self._make_request(endpoint, payload_generate, request_timeout=request_timeout)
                content = result.get("response", "")
                tokens_used = result.get("eval_count", 0)
            except requests.exceptions.HTTPError as exc:
                status_code = getattr(exc.response, "status_code", None)
                if status_code not in fallback_codes:
                    raise

                logger.warning("/api/generate returned %s; falling back to /api/chat", status_code)
                endpoint = "api/chat"
                payload_chat = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": merged_options,
                    **kwargs,
                }

                try:
                    result = self._make_request(endpoint, payload_chat, request_timeout=request_timeout)
                    content = result.get("message", {}).get("content", "")
                    tokens_used = result.get("eval_count", 0)
                except requests.exceptions.HTTPError as nested_exc:
                    status_code = getattr(nested_exc.response, "status_code", None)
                    if status_code not in fallback_codes:
                        raise

                    logger.warning(
                        "/api/chat returned %s; falling back to /v1/chat/completions",
                        status_code,
                    )
                    endpoint = "v1/chat/completions"
                    payload_v1 = {
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "options": merged_options,
                        **kwargs,
                    }
                    result = self._make_request(endpoint, payload_v1, request_timeout=request_timeout)
                    choices = result.get("choices", [])
                    content = choices[0].get("message", {}).get("content", "") if choices else ""
                    usage = result.get("usage", {})
                    tokens_used = usage.get("completion_tokens") or usage.get("total_tokens") or 0

            response_time = time.time() - start_time
            logger.info(
                "Generation completed via %s in %.2fs, %s tokens",
                endpoint,
                response_time,
                tokens_used,
            )
            return LLMResponse(
                content=content,
                raw_response=result,
                success=True,
                tokens_used=tokens_used,
                response_time=response_time,
            )
        except Exception as exc:
            logger.error("Generation failed: %s", exc)
            return LLMResponse(
                content="",
                raw_response={},
                success=False,
                error_message=str(exc),
            )

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        """Chat with the model using message format."""
        request_timeout = kwargs.pop("request_timeout", None)
        merged_options = {
            "num_gpu": self.num_gpu,
            "num_thread": self.num_thread,
            **kwargs.pop("options", {}),
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": merged_options,
            **kwargs,
        }

        try:
            start_time = time.time()
            result = self._make_request("api/chat", payload, request_timeout=request_timeout)
            response_time = time.time() - start_time

            content = result.get("message", {}).get("content", "")
            tokens_used = result.get("eval_count", 0)
            logger.info("Chat completed in %.2fs, %s tokens", response_time, tokens_used)

            return LLMResponse(
                content=content,
                raw_response=result,
                success=True,
                tokens_used=tokens_used,
                response_time=response_time,
            )
        except Exception as exc:
            logger.error("Chat failed: %s", exc)
            return LLMResponse(
                content="",
                raw_response={},
                success=False,
                error_message=str(exc),
            )

    def check_model_availability(self) -> bool:
        """Check whether the configured model is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
            model_names = [model["name"] for model in response.json().get("models", [])]
            available = self.model in model_names
            logger.info("Model %s availability: %s", self.model, available)
            logger.debug("Available models: %s", model_names)
            return available
        except Exception as exc:
            logger.error("Failed to check model availability: %s", exc)
            return False

    def pull_model(self) -> bool:
        """Pull the configured model if not already available."""
        try:
            logger.info("Pulling model: %s", self.model)
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": self.model},
                timeout=300,
            )
            response.raise_for_status()
            logger.info("Successfully pulled model: %s", self.model)
            return True
        except Exception as exc:
            logger.error("Failed to pull model %s: %s", self.model, exc)
            return False
