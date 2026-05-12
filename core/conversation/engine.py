"""
Conversation engine v3.
- TTS: browser fallback when ElevenLabs fails
- Plugin responses also get TTS
- Less repetitive (lower repeat_penalty weight handled in prompt)
"""
import uuid, re, time, logging, asyncio
from typing import AsyncGenerator, Dict

from config.settings import LLM_BACKEND
from core.llm.prompt_builder import build_prompt
from core.memory.conversation_store import save_message, get_recent_messages
from core.memory.semantic_memory import search_memory, store_memory, get_all_facts
from core.memory.fact_extractor import extract_facts
from core.memory.semantic_memory import store_fact
from core.memory.reflection_engine import maybe_reflect, get_recent_reflections
from core.emotion.fusion_engine import fuse as fuse_emotion
from core.cognitive.mode_selector import select_cognitive_mode
from core.safety.safety_monitor import check_message, filter_response
from core.voice.elevenlabs_tts import synthesise, tts_backend

logger = logging.getLogger(__name__)


def _get_llm():
    if LLM_BACKEND == "openai":
        from core.llm.openai_client import get_openai_client
        return get_openai_client()
    from core.llm.ollama_client import get_ollama_client
    return get_ollama_client()


def _split_sentences(text: str):
    """Split text into speakable sentences."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    merged, buf = [], ""
    for p in parts:
        buf = (buf + " " + p).strip() if buf else p
        if len(buf) >= 35:
            merged.append(buf); buf = ""
    if buf: merged.append(buf)
    return merged


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
        self.llm          = _get_llm()
        self.session_id   = str(uuid.uuid4())
        self._tts         = tts_backend()
        self._stop_event  = asyncio.Event()
        self._active_response = ""
        self.emotion_state: Dict = {
            "current_emotion": "neutral",
            "emotional_trend": "neutral",
            "emotional_state": "stable",
            "valence": 0.0,
        }
        logger.info("Engine LLM=%s TTS=%s Session=%s", LLM_BACKEND, self._tts, self.session_id)

    def new_session(self) -> str:
        self.request_stop()
        self.session_id = str(uuid.uuid4())
        self._active_response = ""
        return self.session_id

    def request_stop(self) -> None:
        self._stop_event.set()

    def clear_stop(self) -> None:
        self._stop_event.clear()

    def get_partial_response(self) -> str:
        return self._active_response

    async def speak(self, text: str, emotion: str, tts_backend_override: str = None):
        """Yield tts_sentence events for a block of text."""
        backend = tts_backend_override or self._tts
        sentences = _split_sentences(text)
        events = []

        if backend == "browser":
            for s in sentences:
                events.append({"type": "tts_sentence", "text": s,
                               "audio_path": None, "emotion": emotion})
        elif backend == "elevenlabs":
            # Synthesise all in parallel
            tasks = [asyncio.create_task(synthesise(s, emotion)) for s in sentences]
            for s, task in zip(sentences, tasks):
                try:
                    path = await asyncio.wait_for(task, timeout=15)
                    if path:
                        events.append({"type": "tts_sentence", "text": s,
                                       "audio_path": str(path), "emotion": emotion})
                    else:
                        # ElevenLabs failed → browser fallback
                        events.append({"type": "tts_sentence", "text": s,
                                       "audio_path": None, "emotion": emotion})
                except Exception:
                    events.append({"type": "tts_sentence", "text": s,
                                   "audio_path": None, "emotion": emotion})
        return events

    async def process_message(self, user_text: str, audio_np=None) -> AsyncGenerator[Dict, None]:
        t0 = time.time()
        self.clear_stop()
        self._active_response = ""

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
            async for token in self.llm.generate_stream(
                prompt=user_prompt, system=system_prompt, mode=mode
            ):
                if self._stop_event.is_set():
                    stopped = True
                    break

                full_response  += token
                self._active_response = full_response
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
                self._active_response = full_response
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
            self._active_response = full_response

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
        self._active_response = full_response

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

    def _error_msg(self, e) -> str:
        s = str(e)
        if "401" in s: return "API key issue. Check your OPENAI_API_KEY in .env"
        if "429" in s: return "Rate limited. Please wait a moment."
        if "ConnectError" in type(e).__name__: return "Can't reach the AI server. Check your connection."
        return f"Something went wrong ({type(e).__name__}). Check the terminal."

    async def _reflect(self):
        try:
            summary = await maybe_reflect(self.session_id, self.llm, self.emotion_state)
            if summary:
                from core.memory.database import add_narrative_entry
                add_narrative_entry(self.session_id, summary)
        except Exception as e:
            logger.warning("Reflection error: %s", e)