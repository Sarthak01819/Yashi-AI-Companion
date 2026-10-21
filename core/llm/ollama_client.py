"""
Ollama Cloud client — large models on https://ollama.com, authenticated with
OLLAMA_API_KEY. (Nothing runs locally; no Ollama install is needed.)
"""

import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from config.settings import (
    LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_TOP_P,
    OLLAMA_CLOUD_URL, OLLAMA_CLOUD_MODEL, OLLAMA_CLOUD_TIMEOUT, OLLAMA_API_KEY,
)

logger = logging.getLogger(__name__)


class OllamaCloudClient:
    def __init__(self, api_key: str = OLLAMA_API_KEY, model: str = OLLAMA_CLOUD_MODEL,
                 base_url: str = OLLAMA_CLOUD_URL, timeout: float = OLLAMA_CLOUD_TIMEOUT):
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def _payload(self, messages: list, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "think": False,                    # no reasoning traces in the reply
            "options": {
                "num_predict": LLM_MAX_TOKENS,
                "temperature": LLM_TEMPERATURE,
                "top_p": LLM_TOP_P,
            },
        }

    @staticmethod
    def _messages(prompt: str, system: Optional[str], messages: Optional[list]) -> list:
        chat = [{"role": "system", "content": system}] if system else []
        if messages:
            chat += [{"role": m["role"], "content": m["content"]} for m in messages]
        else:
            chat.append({"role": "user", "content": prompt})
        return chat

    async def verify(self) -> tuple:
        """Check the key and that the model is available. Returns (ok, detail)."""
        try:
            r = await self._client.get("/api/tags", timeout=10)
        except Exception as e:
            return False, f"cannot reach {self._client.base_url} ({type(e).__name__})"
        if r.status_code in (401, 403):
            return False, "API key rejected"
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        names = [m.get("name", "") for m in r.json().get("models", [])]
        if self.model not in names:
            return False, f"model '{self.model}' not available"
        return True, self.model

    async def generate(self, prompt: str, system: Optional[str] = None,
                       mode: str = "standard", messages: Optional[list] = None) -> str:
        r = await self._client.post(
            "/api/chat", json=self._payload(self._messages(prompt, system, messages), False)
        )
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()

    async def generate_stream(self, prompt: str, system: Optional[str] = None,
                              mode: str = "standard",
                              messages: Optional[list] = None) -> AsyncGenerator[str, None]:
        payload = self._payload(self._messages(prompt, system, messages), True)
        async with self._client.stream("POST", "/api/chat", json=payload) as resp:
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", "ignore")
                raise RuntimeError(f"Ollama Cloud {resp.status_code}: {body[:200]}")
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
                if chunk.get("done", False):
                    break

    async def close(self):
        await self._client.aclose()


_instance: Optional[OllamaCloudClient] = None


def get_ollama_cloud_client() -> OllamaCloudClient:
    global _instance
    if _instance is None:
        _instance = OllamaCloudClient()
    return _instance
