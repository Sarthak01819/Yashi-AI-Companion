"""
Ollama API client with async support and automatic fallback.
Fixed: LLM_REPEAT_PENALTY removed from import (no longer in settings.py)
"""

import json
import logging
import asyncio
import httpx
from typing import AsyncGenerator, Optional

from config.settings import (
    OLLAMA_BASE_URL, OLLAMA_TIMEOUT,
    DEFAULT_MODEL, FALLBACK_MODEL,
    LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_TOP_P,
)

# Repeat penalty no longer in settings — use a sensible default
LLM_REPEAT_PENALTY = 1.1

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=OLLAMA_BASE_URL,
            timeout=OLLAMA_TIMEOUT,
        )

    async def is_available(self) -> bool:
        try:
            r = await self._client.get("/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list:
        try:
            r = await self._client.get("/api/tags")
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        mode: str = "standard",
        stream: bool = False,
    ) -> str:
        from core.llm.model_router import select_model
        chosen_model = model or select_model(mode)

        payload = {
            "model":  chosen_model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "num_predict":    LLM_MAX_TOKENS,
                "temperature":    LLM_TEMPERATURE,
                "top_p":          LLM_TOP_P,
                "repeat_penalty": LLM_REPEAT_PENALTY,
                "num_ctx":        2048,
            },
        }
        if system:
            payload["system"] = system

        try:
            r = await self._client.post("/api/generate", json=payload,
                                        timeout=OLLAMA_TIMEOUT)
            r.raise_for_status()
            return r.json().get("response", "").strip()
        except httpx.HTTPStatusError as e:
            if "model not found" in str(e).lower():
                logger.warning("Model %s not found, trying fallback %s",
                               chosen_model, FALLBACK_MODEL)
                payload["model"] = FALLBACK_MODEL
                r2 = await self._client.post("/api/generate", json=payload)
                r2.raise_for_status()
                return r2.json().get("response", "").strip()
            raise

    async def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        mode: str = "standard",
    ) -> AsyncGenerator[str, None]:
        from core.llm.model_router import select_model
        chosen_model = model or select_model(mode)

        payload = {
            "model":  chosen_model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_predict":    LLM_MAX_TOKENS,
                "temperature":    LLM_TEMPERATURE,
                "top_p":          LLM_TOP_P,
                "repeat_penalty": LLM_REPEAT_PENALTY,
                "num_ctx":        2048,
            },
        }
        if system:
            payload["system"] = system

        async with self._client.stream("POST", "/api/generate",
                                       json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.strip():
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done", False):
                        break

    async def close(self):
        await self._client.aclose()


_client_instance: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = OllamaClient()
    return _client_instance