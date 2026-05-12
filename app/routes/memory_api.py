"""
Memory API — REST endpoints for viewing/managing Yashi's memory.
"""

from fastapi import APIRouter
from core.memory.semantic_memory import get_all_facts, search_memory
from core.memory.reflection_engine import get_recent_reflections
from core.memory.conversation_store import get_recent_messages, get_all_sessions

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/facts")
def get_facts():
    return {"facts": get_all_facts()}


@router.get("/reflections")
def get_reflections(limit: int = 5):
    return {"reflections": get_recent_reflections(limit)}


@router.get("/search")
def memory_search(q: str, top_k: int = 5):
    results = search_memory(q, top_k=top_k)
    return {"results": [{"content": c, "score": s} for c, s in results]}


@router.get("/sessions")
def sessions():
    return {"sessions": get_all_sessions()}


@router.get("/history/{session_id}")
def history(session_id: str, limit: int = 30):
    msgs = get_recent_messages(session_id, limit=limit)
    return {"messages": msgs}


@router.get("/narrative/{session_id}")
def get_narrative_thread(session_id: str, limit: int = 10):
    """Return the narrative memory thread for a session."""
    from core.memory.database import get_narrative
    return {"narrative": get_narrative(session_id, limit=limit)}


@router.get("/debug/ollama")
async def debug_ollama():
    """Check Ollama status and show available models — visit this in browser to diagnose."""
    from core.llm.ollama_client import get_ollama_client
    from core.llm.model_router import get_available_models, select_model
    import httpx

    client = get_ollama_client()
    is_up = await client.is_available()
    models = await client.list_models() if is_up else []

    return {
        "ollama_running":   is_up,
        "available_models": models,
        "model_for_standard": select_model("standard") if models else "none",
        "model_for_light":    select_model("light")    if models else "none",
        "instruction": (
            "If available_models is empty: run 'ollama pull mistral' in your terminal. "
            "If ollama_running is false: run 'ollama serve' in a separate terminal."
        )
    }
