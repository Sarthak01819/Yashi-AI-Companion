"""
OpenAI API client with automatic retry + exponential backoff.
Handles 429 rate limits gracefully instead of crashing.
"""

import json
import time
import logging
import asyncio
from typing import AsyncGenerator, Optional

import httpx

from config.settings import (
    OPENAI_API_KEY, OPENAI_MODEL,
    OPENAI_TIMEOUT, LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_TOP_P,
)

logger = logging.getLogger(__name__)
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# Retry config — handles free-tier 3 RPM limit gracefully
MAX_RETRIES   = 4
RETRY_DELAYS  = [2, 5, 12, 25]   # seconds between retries


def _build_payload(messages: list, stream: bool) -> dict:
    return {
        "model":       OPENAI_MODEL,
        "messages":    messages,
        "max_tokens":  LLM_MAX_TOKENS,
        "temperature": LLM_TEMPERATURE,
        "top_p":       LLM_TOP_P,
        "stream":      stream,
    }


class OpenAIClient:
    def __init__(self):
        if not OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not set — add it to your .env file")
        self._client = httpx.AsyncClient(
            timeout=OPENAI_TIMEOUT,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type":  "application/json",
            }
        )

    async def is_available(self) -> bool:
        return bool(OPENAI_API_KEY)

    def _build_messages(self, prompt: str, system: Optional[str]) -> list:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    async def generate(self, prompt: str, system: Optional[str] = None,
                       mode: str = "standard") -> str:
        msgs    = self._build_messages(prompt, system)
        payload = _build_payload(msgs, stream=False)

        for attempt, delay in enumerate(RETRY_DELAYS):
            try:
                resp = await self._client.post(OPENAI_URL, json=payload)
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("retry-after", delay))
                    logger.warning("OpenAI rate limit — retrying in %ds (attempt %d/%d)",
                                   retry_after, attempt + 1, MAX_RETRIES)
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except httpx.HTTPStatusError as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(delay)
        raise RuntimeError("OpenAI request failed after all retries")

    async def generate_stream(self, prompt: str, system: Optional[str] = None,
                               mode: str = "standard") -> AsyncGenerator[str, None]:
        msgs    = self._build_messages(prompt, system)
        payload = _build_payload(msgs, stream=True)

        for attempt in range(MAX_RETRIES):
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            try:
                async with self._client.stream("POST", OPENAI_URL,
                                               json=payload) as resp:
                    if resp.status_code == 429:
                        # Read retry-after header before closing stream
                        retry_after = int(resp.headers.get("retry-after", delay))
                        logger.warning(
                            "OpenAI rate limit on stream — retrying in %ds (attempt %d/%d)",
                            retry_after, attempt + 1, MAX_RETRIES
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    resp.raise_for_status()

                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data_str)
                            token = chunk["choices"][0].get("delta", {}).get("content", "")
                            if token:
                                yield token
                        except Exception:
                            continue
                    return  # success

            except httpx.HTTPStatusError as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                logger.warning("OpenAI HTTP error %s — retrying in %ds", e.response.status_code, delay)
                await asyncio.sleep(delay)

    async def close(self):
        await self._client.aclose()


_client: Optional[OpenAIClient] = None

def get_openai_client() -> OpenAIClient:
    global _client
    if _client is None:
        _client = OpenAIClient()
    return _client
