"""
Anthropic (Claude) client — streaming chat backend for Yashi.

Uses the official `anthropic` SDK (AsyncAnthropic). Exposes the same surface as
the Ollama / OpenAI clients so the conversation engine can swap backends freely:

    await client.generate(prompt, system=..., mode=...)          -> str
    async for token in client.generate_stream(prompt, ...)       -> tokens
"""

import logging
from typing import AsyncGenerator, List, Optional

import anthropic

from config.settings import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    ANTHROPIC_TIMEOUT,
    ANTHROPIC_THINKING,
    ANTHROPIC_EFFORT_MAP,
    ANTHROPIC_MAX_TOKENS_MAP,
    LLM_MAX_TOKENS,
)

logger = logging.getLogger(__name__)

# Guard rail recommended when extended thinking is turned off: keeps internal
# reasoning tags out of the spoken response.
NO_THINKING_GUARD = (
    "Do not include internal or system XML tags in your response."
)


class AnthropicClient:
    def __init__(self):
        if not ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set — add it to your .env file")
        self._client = anthropic.AsyncAnthropic(
            api_key=ANTHROPIC_API_KEY or None,
            timeout=ANTHROPIC_TIMEOUT,
            max_retries=2,
        )

    async def is_available(self) -> bool:
        return bool(ANTHROPIC_API_KEY)

    async def verify(self) -> tuple:
        """Cheap auth probe (no tokens billed). Returns (ok, detail)."""
        if not ANTHROPIC_API_KEY:
            return False, "ANTHROPIC_API_KEY is not set"
        try:
            await self._client.models.list(limit=1)
            return True, ANTHROPIC_MODEL
        except anthropic.AuthenticationError:
            return False, "API key is invalid or revoked"
        except anthropic.PermissionDeniedError:
            return False, "API key lacks permission for this model"
        except anthropic.APIConnectionError:
            return False, "cannot reach api.anthropic.com"
        except Exception as e:                      # noqa: BLE001 — startup probe
            return False, f"{type(e).__name__}: {str(e)[:100]}"

    # ── request assembly ─────────────────────────────────────────────────────
    def _build_messages(self, prompt: str, messages: Optional[List[dict]]) -> List[dict]:
        """Prefer real chat turns; fall back to a single user message."""
        if messages:
            cleaned = [
                {"role": m["role"], "content": m["content"]}
                for m in messages
                if m.get("content") and m.get("role") in ("user", "assistant")
            ]
            # The API requires the first turn to be from the user.
            while cleaned and cleaned[0]["role"] != "user":
                cleaned.pop(0)
            if cleaned and cleaned[-1]["role"] == "user":
                return cleaned
            if cleaned:
                cleaned.append({"role": "user", "content": prompt})
                return cleaned
        return [{"role": "user", "content": prompt}]

    def _kwargs(self, prompt: str, system: Optional[str], mode: str,
                messages: Optional[List[dict]]) -> dict:
        system_text = system or ""
        thinking_off = ANTHROPIC_THINKING == "disabled"
        if thinking_off and system_text:
            system_text = f"{system_text}\n{NO_THINKING_GUARD}"

        kwargs = {
            "model":      ANTHROPIC_MODEL,
            "max_tokens": ANTHROPIC_MAX_TOKENS_MAP.get(mode, LLM_MAX_TOKENS),
            "messages":   self._build_messages(prompt, messages),
            "output_config": {"effort": ANTHROPIC_EFFORT_MAP.get(mode, "low")},
        }
        if system_text:
            kwargs["system"] = system_text
        if thinking_off:
            # Accepted on Opus 5 at effort "high" or below — keeps first-token
            # latency low, which matters for a spoken companion.
            kwargs["thinking"] = {"type": "disabled"}
        else:
            kwargs["thinking"] = {"type": "adaptive"}
        return kwargs

    # ── generation ───────────────────────────────────────────────────────────
    async def generate(self, prompt: str, system: Optional[str] = None,
                       mode: str = "standard", messages: Optional[List[dict]] = None) -> str:
        resp = await self._client.messages.create(
            **self._kwargs(prompt, system, mode, messages)
        )
        if resp.stop_reason == "refusal":
            logger.warning("Claude declined the request (%s)",
                           getattr(resp.stop_details, "category", None))
            return "I'd rather not go into that one — can we talk about something else?"
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    async def generate_stream(self, prompt: str, system: Optional[str] = None,
                              mode: str = "standard", model: Optional[str] = None,
                              messages: Optional[List[dict]] = None) -> AsyncGenerator[str, None]:
        kwargs = self._kwargs(prompt, system, mode, messages)
        if model:
            kwargs["model"] = model

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    if event.delta.text:
                        yield event.delta.text

            final = await stream.get_final_message()
            if final.stop_reason == "refusal":
                logger.warning("Claude declined mid-stream (%s)",
                               getattr(final.stop_details, "category", None))

    async def close(self):
        await self._client.close()


_client: Optional[AnthropicClient] = None


def get_anthropic_client() -> AnthropicClient:
    global _client
    if _client is None:
        _client = AnthropicClient()
    return _client
