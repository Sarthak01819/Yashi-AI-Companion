"""
OpenAI API client with automatic retry + exponential backoff.
Handles 429 rate limits gracefully instead of crashing.
"""

import json
import logging
import asyncio
from typing import AsyncGenerator, Optional

import httpx

import config.settings as S

logger = logging.getLogger(__name__)
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# Retry config — handles free-tier 3 RPM limit gracefully
MAX_RETRIES   = 4
RETRY_DELAYS  = [2, 5, 12, 25]   # seconds between retries


def _build_payload(messages: list, stream: bool) -> dict:
    return {
        "model":       S.OPENAI_MODEL,
        "messages":    messages,
        "max_tokens":  S.LLM_MAX_TOKENS,
        "temperature": S.LLM_TEMPERATURE,
        "top_p":       S.LLM_TOP_P,
        "stream":      stream,
    }


class OpenAIClient:
    def __init__(self):
        if not S.OPENAI_API_KEY:
            logger.warning("S.OPENAI_API_KEY not set — add it to your .env file")
        self._client = httpx.AsyncClient(
            timeout=S.OPENAI_TIMEOUT,
            headers={
                "Authorization": f"Bearer {S.OPENAI_API_KEY}",
                "Content-Type":  "application/json",
            }
        )

    async def is_available(self) -> bool:
        return bool(S.OPENAI_API_KEY)

    def _build_messages(self, prompt: str, system: Optional[str],
                        messages: Optional[list] = None) -> list:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        if messages:
            msgs.extend({"role": m["role"], "content": m["content"]}
                        for m in messages if m.get("content"))
        else:
            msgs.append({"role": "user", "content": prompt})
        return msgs

    async def generate(self, prompt: str, system: Optional[str] = None,
                       mode: str = "standard", messages: Optional[list] = None) -> str:
        msgs    = self._build_messages(prompt, system, messages)
        payload = _build_payload(msgs, stream=False)

        for attempt, delay in enumerate(RETRY_DELAYS):
            try:
                resp = await self._client.post(OPENAI_URL, json=payload)
                if resp.status_code == 429:
                    if "insufficient_quota" in resp.text or "credit" in resp.text:
                        raise RuntimeError("OpenAI 429 insufficient_quota: account has no credit")
                    retry_after = int(resp.headers.get("retry-after", delay))
                    logger.warning("OpenAI rate limit — retrying in %ds (attempt %d/%d)",
                                   retry_after, attempt + 1, MAX_RETRIES)
                    await asyncio.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except httpx.HTTPStatusError:
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(delay)
        raise RuntimeError("OpenAI request failed after all retries")

    async def generate_stream(self, prompt: str, system: Optional[str] = None,
                               mode: str = "standard",
                               messages: Optional[list] = None) -> AsyncGenerator[str, None]:
        msgs    = self._build_messages(prompt, system, messages)
        payload = _build_payload(msgs, stream=True)

        for attempt in range(MAX_RETRIES):
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            try:
                async with self._client.stream("POST", OPENAI_URL,
                                               json=payload) as resp:
                    if resp.status_code == 429:
                        body = (await resp.aread()).decode("utf-8", "ignore")
                        if "insufficient_quota" in body or "credit" in body:
                            # Out of credit is not transient — don't retry.
                            raise RuntimeError("OpenAI 429 insufficient_quota: account has no credit")
                        if attempt == MAX_RETRIES - 1:
                            raise RuntimeError("OpenAI 429 rate limited after all retries")
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
