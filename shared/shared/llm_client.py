"""Pluggable LLM client abstraction.

Supports Ollama (local), OpenAI, and Anthropic as providers.
Each service that needs LLM calls uses this interface so the provider
can be swapped via config without changing service code.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

import httpx

from .config import LLMConfig
from .models import LLMProvider

logger = logging.getLogger(__name__)


class LLMClient(ABC):
    """Abstract LLM client — all providers implement this interface."""

    @abstractmethod
    async def complete(self, prompt: str, *, max_tokens: int = 2000) -> str:
        """Send a prompt and return the text response."""
        ...

    async def complete_json(self, prompt: str, *, max_tokens: int = 2000) -> dict | list | None:
        """Send a prompt and parse the response as JSON.

        Returns None if the response isn't valid JSON.
        """
        text = await self.complete(prompt, max_tokens=max_tokens)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if "```" in text:
                for block in text.split("```"):
                    block = block.strip()
                    if block.startswith("json"):
                        block = block[4:].strip()
                    try:
                        return json.loads(block)
                    except json.JSONDecodeError:
                        continue
            logger.warning("LLM response was not valid JSON: %s...", text[:200])
            return None

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        ...


class OllamaClient(LLMClient):
    """LLM client for local Ollama instance."""

    def __init__(self, base_url: str, model: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(timeout=timeout)

    async def complete(self, prompt: str, *, max_tokens: int = 2000) -> str:
        response = await self._client.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"num_predict": max_tokens},
            },
        )
        response.raise_for_status()
        return response.json().get("response", "")

    async def close(self) -> None:
        await self._client.aclose()


class OpenAIClient(LLMClient):
    """LLM client for OpenAI-compatible APIs."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def complete(self, prompt: str, *, max_tokens: int = 2000) -> str:
        response = await self._client.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    async def close(self) -> None:
        await self._client.aclose()


class AnthropicClient(LLMClient):
    """LLM client for Anthropic Claude API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self._client = httpx.AsyncClient(
            base_url="https://api.anthropic.com/v1",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=timeout,
        )

    async def complete(self, prompt: str, *, max_tokens: int = 2000) -> str:
        response = await self._client.post(
            "/messages",
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        content = response.json()["content"]
        return content[0]["text"] if content else ""

    async def close(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_llm_client(config: LLMConfig) -> LLMClient:
    """Create an LLM client based on config.

    This is the entry point — services call this and get back whichever
    provider is configured, without knowing the implementation details.
    """
    match config.llm_provider:
        case LLMProvider.OLLAMA:
            return OllamaClient(
                base_url=config.llm_base_url,
                model=config.llm_model,
                timeout=config.llm_timeout,
            )
        case LLMProvider.OPENAI:
            if not config.llm_api_key:
                raise ValueError("LLM_API_KEY required for OpenAI provider")
            return OpenAIClient(
                api_key=config.llm_api_key,
                model=config.llm_model,
                base_url=config.llm_base_url
                if "openai" not in config.llm_base_url
                else "https://api.openai.com/v1",
                timeout=config.llm_timeout,
            )
        case LLMProvider.ANTHROPIC:
            if not config.llm_api_key:
                raise ValueError("LLM_API_KEY required for Anthropic provider")
            return AnthropicClient(
                api_key=config.llm_api_key,
                model=config.llm_model,
                timeout=config.llm_timeout,
            )
        case _:
            raise ValueError(f"Unknown LLM provider: {config.llm_provider}")
