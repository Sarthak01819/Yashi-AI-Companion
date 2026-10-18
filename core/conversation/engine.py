"""
Conversation engine: one user message -> emotion, safety, memory, prompt,
streamed LLM reply, sentence-by-sentence TTS events.
"""
import uuid, re, time, logging, asyncio
from typing import AsyncGenerator, Dict

import config.settings as settings
from core.llm.prompt_builder import build_prompt, build_chat_messages
from core.memory.conversation_store import save_message, get_recent_messages
from core.memory.semantic_memory import search_memory, store_memory, get_all_facts
from core.memory.fact_extractor import extract_facts
from core.memory.semantic_memory import store_fact
from core.memory.reflection_engine import maybe_reflect, get_recent_reflections
from core.emotion.fusion_engine import fuse as fuse_emotion
from core.cognitive.mode_selector import select_cognitive_mode
from core.safety.safety_monitor import check_message, filter_response, strip_emojis
from core.voice.elevenlabs_tts import synthesise, tts_backend

logger = logging.getLogger(__name__)


def current_backend() -> str:
    """Read the backend at call time so the sidebar toggle takes effect live."""
    return getattr(settings, "LLM_BACKEND", "anthropic")


def _get_llm(backend: str = None):
    backend = backend or current_backend()
    if backend == "anthropic":
        from core.llm.anthropic_client import get_anthropic_client
        return get_anthropic_client()
    if backend == "ollama_cloud":
        from core.llm.ollama_client import get_ollama_cloud_client
        return get_ollama_cloud_client()
    if backend == "openai":
        from core.llm.openai_client import get_openai_client
        return get_openai_client()
    from core.llm.ollama_client import get_ollama_client
    return get_ollama_client()




def _normalise_tts_chunk(text: str, final_chunk: bool = False) -> str:
    """
    Prepare text for smoother speech output:
    - collapse noisy punctuation that creates long pauses
    - strip markdown artifacts
    - remove trailing hard punctuation on non-final chunks
    """
    t = text.strip()
    if not t:
        return ""

    # Remove markdown/code markers that sound robotic when read aloud.
    t = re.sub(r"[`*_#~]", "", t)

    # Replace long punctuation runs and heavy pause markers.
    t = re.sub(r"\.{3,}", ".", t)
    t = re.sub(r"[,:;]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()

    if not final_chunk:
        t = re.sub(r"[.!?]+$", "", t).strip()

    return t


class ConversationEngine:
    def __init__(self):
        self._backend     = current_backend()
        self.llm          = _get_llm(self._backend)
        self.session_id   = str(uuid.uuid4())
        self._stop_event  = asyncio.Event()
        self.emotion_state: Dict = {
            "current_emotion": "neutral",
            "emotional_trend": "neutral",
            "emotional_state": "stable",
            "valence": 0.0,
        }
        logger.info("Engine LLM=%s TTS=%s Session=%s",
                    self._backend, self._tts, self.session_id)

    @property
    def _tts(self) -> str:
        """Resolved at read time so the TTS toggle applies without a reconnect."""
        return tts_backend()

    def _sync_backend(self) -> None:
        """Pick up a runtime LLM backend switch before the next generation."""
        backend = current_backend()
        if backend != self._backend:
            logger.info("LLM backend switched: %s -> %s", self._backend, backend)
            self._backend = backend
            self.llm = _get_llm(backend)

    def new_session(self) -> str:
        self.request_stop()
        self.session_id = str(uuid.uuid4())
        return self.session_id

    def request_stop(self) -> None:
        self._stop_event.set()

    def clear_stop(self) -> None:
        self._stop_event.clear()



    async def process_message(self, user_text: str, audio_np=None) -> AsyncGenerator[Dict, None]:
        t0 = time.time()
        self.clear_stop()
        self._sync_backend()

        self.emotion_state = fuse_emotion(user_text, audio_np)
        yield {"type": "emotion", **self.emotion_state}

        safety = check_message(user_text, self.emotion_state, self.session_id)
        if safety.get("safety_note"):
            yield {"type": "safety", "note": safety["safety_note"]}

        save_message(self.session_id, "user", user_text,
                     self.emotion_state["current_emotion"])

        for cat, fact in extract_facts(user_text):
            store_fact(cat, fact)

        mode = select_cognitive_mode(user_text, self.emotion_state)
        yield {"type": "thinking", "mode": mode}

        history       = get_recent_messages(self.session_id)
        semantic_mems = search_memory(user_text)
        facts         = get_all_facts()
        reflections   = get_recent_reflections(2)

        system_prompt, user_prompt = build_prompt(
            user_message=user_text,
            conversation_history=history[:-1],
            semantic_memories=semantic_mems,
            personal_facts=facts,
            recent_reflections=reflections,
            emotion_state=self.emotion_state,
            cognitive_mode=mode,
        )
        # Chat-shaped history for message-based backends (Claude / OpenAI).
        chat_messages = build_chat_messages(user_text, history[:-1])

        full_response = ""
        sentence_buf  = ""
        emotion       = self.emotion_state["current_emotion"]
        stopped       = False
        # Collect (sentence, synth_task) for non-browser TTS
        tts_tasks     = []

        def _sentence_end(t):
            s = t.rstrip()
            return bool(s) and s[-1] in ".!?\n"

        def _soft_break(t):
            s = t.rstrip()
            return bool(s) and s[-1] in ",;:"

        try:
            async for token in self._stream_with_fallback(
                prompt=user_prompt, system=system_prompt, mode=mode,
                messages=chat_messages,
            ):
                if self._stop_event.is_set():
                    stopped = True
                    break

                token = strip_emojis(token)
                if not token:
                    continue
                full_response  += token
                sentence_buf   += token
                yield {"type": "token", "text": token}

                # Trigger TTS sentence by sentence
                if _sentence_end(sentence_buf) and len(sentence_buf.strip()) >= 20:
                    sent = sentence_buf.strip()
                    sentence_buf = ""
                    tts_text = _normalise_tts_chunk(sent, final_chunk=False)
                    if not tts_text:
                        continue
                    if self._tts == "browser":
                        yield {"type": "tts_sentence", "text": tts_text,
                               "audio_path": None, "emotion": emotion}
                    else:
                        task = asyncio.create_task(synthesise(tts_text, emotion))
                        tts_tasks.append((tts_text, task))

                # Soft punctuation flush helps reduce audible stalls in long clauses.
                elif _soft_break(sentence_buf) and len(sentence_buf.strip()) >= 70:
                    sent = sentence_buf.strip()
                    sentence_buf = ""
                    tts_text = _normalise_tts_chunk(sent, final_chunk=False)
                    if not tts_text:
                        continue
                    if self._tts == "browser":
                        yield {"type": "tts_sentence", "text": tts_text,
                               "audio_path": None, "emotion": emotion}
                    else:
                        task = asyncio.create_task(synthesise(tts_text, emotion))
                        tts_tasks.append((tts_text, task))

        except asyncio.CancelledError:
            logger.info("Generation cancelled for session %s", self.session_id)
            stopped = True
            self.request_stop()
        except Exception as e:
            if self._stop_event.is_set():
                stopped = True
                logger.info("Generation stopped for session %s", self.session_id)
            else:
                logger.error("LLM error: %s", e)
                msg = self._error_msg(e)
                full_response = msg
                yield {"type": "token", "text": msg}

        if self._stop_event.is_set():
            stopped = True

        # Speak remaining buffer
        if (not stopped) and sentence_buf.strip() and len(sentence_buf.strip()) >= 3:
            rem = _normalise_tts_chunk(sentence_buf.strip(), final_chunk=True)
            if not rem:
                rem = sentence_buf.strip()
            if self._tts == "browser":
                yield {"type": "tts_sentence", "text": rem, "audio_path": None, "emotion": emotion}
            else:
                task = asyncio.create_task(synthesise(rem, emotion))
                tts_tasks.append((rem, task))

        if stopped:
            for _, task in tts_tasks:
                task.cancel()

            full_response = filter_response(full_response.strip())

            if full_response:
                save_message(self.session_id, "assistant", full_response,
                             self.emotion_state["current_emotion"])
                store_memory(
                    f"User: {user_text} | Yashi: {full_response[:180]}",
                    source="conversation",
                )

            yield {
                "type": "done",
                "full_text": full_response,
                "audio_path": None,
                "emotion": emotion,
                "mode": mode,
                "elapsed": round(time.time() - t0, 2),
                "tts_backend": self._tts,
                "stopped": True,
            }
            return

        full_response = filter_response(full_response)

        # Collect ElevenLabs results — always fall back to browser on failure
        for sent_text, task in tts_tasks:
            try:
                path = await asyncio.wait_for(task, timeout=15)
                yield {"type": "tts_sentence", "text": sent_text,
                       "audio_path": str(path) if path else None,
                       "emotion": emotion}
            except Exception as e:
                logger.warning("TTS failed: %s", e)
                # Always yield so browser fallback works
                yield {"type": "tts_sentence", "text": sent_text,
                       "audio_path": None, "emotion": emotion}

        save_message(self.session_id, "assistant", full_response,
                     self.emotion_state["current_emotion"])
        store_memory(f"User: {user_text} | Yashi: {full_response[:180]}", source="conversation")

        yield {
            "type": "done", "full_text": full_response,
            "audio_path": None, "emotion": emotion,
            "mode": mode, "elapsed": round(time.time() - t0, 2),
            "tts_backend": self._tts,
        }

        asyncio.create_task(self._reflect())

    async def _stream_with_fallback(self, **kwargs):
        """
        Stream from the active backend. If Ollama Cloud fails before saying
        anything (offline, usage cap, outage), answer with the local model.
        """
        produced = False
        try:
            async for token in self.llm.generate_stream(**kwargs):
                produced = True
                yield token
        except Exception as e:
            if self._backend != "ollama_cloud" or produced or self._stop_event.is_set():
                raise
            logger.warning("Ollama Cloud failed (%s) — answering with local %s",
                           e, settings.DEFAULT_MODEL)
            from core.llm.ollama_client import get_ollama_client
            async for token in get_ollama_client().generate_stream(**kwargs):
                yield token

    def _error_msg(self, e) -> str:
        s = str(e)
        name = type(e).__name__
        key_var = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai":    "OPENAI_API_KEY",
            "ollama_cloud": "OLLAMA_API_KEY",
        }.get(self._backend)
        if "401" in s or "authentication" in s.lower():
            return (f"API key issue. Check your {key_var} in .env"
                    if key_var else "The local model rejected the request.")
        if "insufficient_quota" in s or "credit" in s.lower() or "billing" in s.lower():
            return ("The AI account is out of credit. Add credit, or switch the Brain "
                    "in AI Settings to a backend that works.")
        if "429" in s or "rate_limit" in s.lower():
            return "Rate limited. Please wait a moment."
        if "credit" in s.lower() or "billing" in s.lower():
            return "The AI account is out of credit. Check your Anthropic billing."
        if "ConnectError" in name or "APIConnectionError" in name:
            return "Can't reach the AI server. Check your connection."
        if self._backend == "ollama" and ("model" in s.lower() and "not found" in s.lower()):
            return "That local model isn't installed. Run: ollama pull phi3:mini"
        return f"Something went wrong ({name}). Check the terminal."

    async def _reflect(self):
        try:
            summary = await maybe_reflect(self.session_id, self.llm, self.emotion_state)
            if summary:
                from core.memory.database import add_narrative_entry
                add_narrative_entry(self.session_id, summary)
        except Exception as e:
            logger.warning("Reflection error: %s", e)