"""
Ollama API client — used for both the local Ollama app and Ollama Cloud.

Local:  http://localhost:11434, model chosen per cognitive mode (model_router).
Cloud:  https://ollama.com with an API key and one fixed model.
"""

import json
import logging
import httpx
from typing import AsyncGenerator, Optional

from config.settings import (
    OLLAMA_BASE_URL, OLLAMA_TIMEOUT,
    FALLBACK_MODEL,
    LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_TOP_P,
    OLLAMA_CLOUD_URL, OLLAMA_CLOUD_MODEL, OLLAMA_CLOUD_TIMEOUT, OLLAMA_API_KEY,
)

# Repeat penalty no longer in settings — use a sensible default
LLM_REPEAT_PENALTY = 1.1

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE_URL, api_key: str = "",
                 model: Optional[str] = None, timeout: float = OLLAMA_TIMEOUT):
        self.cloud = bool(api_key)
        self.fixed_model = model          # cloud: one model for every mode
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers=headers,
        )

    def _pick_model(self, model: Optional[str], mode: str) -> str:
        if model:
            return model
        if self.fixed_model:
            return self.fixed_model
        from core.llm.model_router import select_model
        return select_model(mode)

    def _tune(self, payload: dict) -> dict:
        """Cloud: no reasoning traces in the reply, no local-only knobs."""
        if self.cloud:
            payload["think"] = False
            payload.pop("keep_alive", None)
            for knob in ("num_ctx", "repeat_penalty"):
                payload["options"].pop(knob, None)
        return payload

    async def verify(self) -> tuple:
        """Check the server (and, for cloud, the key + model). Returns (ok, detail)."""
        try:
            r = await self._client.get("/api/tags", timeout=10)
        except Exception as e:
            return False, f"cannot reach {self._client.base_url} ({type(e).__name__})"
        if r.status_code in (401, 403):
            return False, "API key rejected"
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        names = [m.get("name", "") for m in r.json().get("models", [])]
        if self.fixed_model and self.fixed_model not in names:
            return False, f"model '{self.fixed_model}' not available"
        return True, self.fixed_model or ", ".join(names)

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
        messages: Optional[list] = None,   # accepted for API parity; unused
    ) -> str:
        chosen_model = self._pick_model(model, mode)

        payload = {
            "model":  chosen_model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": "30m",
            "options": {
                "num_predict":    LLM_MAX_TOKENS,
                "temperature":    LLM_TEMPERATURE,
                "top_p":          LLM_TOP_P,
                "repeat_penalty": LLM_REPEAT_PENALTY,
                "num_ctx":        4096,
            },
        }
        if system:
            payload["system"] = system
        self._tune(payload)

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
        messages: Optional[list] = None,   # accepted for API parity; unused
    ) -> AsyncGenerator[str, None]:
        chosen_model = self._pick_model(model, mode)

        payload = {
            "model":  chosen_model,
            "prompt": prompt,
            "stream": True,
            "keep_alive": "30m",
            "options": {
                "num_predict":    LLM_MAX_TOKENS,
                "temperature":    LLM_TEMPERATURE,
                "top_p":          LLM_TOP_P,
                "repeat_penalty": LLM_REPEAT_PENALTY,
                "num_ctx":        4096,
            },
        }
        if messages:
            # Chat endpoint with real turns — far more natural replies than a
            # "User:/Yashi:" transcript pushed through /api/generate.
            chat = [{"role": "system", "content": system}] if system else []
            chat += [{"role": m["role"], "content": m["content"]} for m in messages]
            payload.pop("prompt", None)
            payload["messages"] = chat
            endpoint, key = "/api/chat", "message"
        else:
            if system:
                payload["system"] = system
            payload["options"]["stop"] = ["\nUser:", "\nuser:"]
            endpoint, key = "/api/generate", "response"
        self._tune(payload)

        async with self._client.stream("POST", endpoint, json=payload) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", "ignore")
                raise RuntimeError(f"Ollama {resp.status_code}: {body[:200]}")
            async for line in resp.aiter_lines():
                if line.strip():
                    chunk = json.loads(line)
                    part = chunk.get(key, "")
                    token = part.get("content", "") if isinstance(part, dict) else part
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

_cloud_instance: Optional[OllamaClient] = None


def get_ollama_cloud_client() -> OllamaClient:
    """Ollama Cloud — big models on Ollama's servers, authenticated by API key."""
    global _cloud_instance
    if _cloud_instance is None:
        _cloud_instance = OllamaClient(
            base_url=OLLAMA_CLOUD_URL,
            api_key=OLLAMA_API_KEY,
            model=OLLAMA_CLOUD_MODEL,
            timeout=OLLAMA_CLOUD_TIMEOUT,
        )
    return _cloud_instance
