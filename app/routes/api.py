"""
REST API routes — memory, facts, status, audio serving.
"""

import os
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.memory.conversation_store import get_recent_messages, get_all_sessions
from core.memory.semantic_memory import search_memory, get_all_facts
from core.memory.reflection_engine import get_recent_reflections
from core.llm.ollama_client import get_ollama_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


@router.get("/health")
async def health():
    ollama = get_ollama_client()
    ollama_ok = await ollama.is_available()
    models = await ollama.list_models() if ollama_ok else []
    return {
        "status": "ok",
        "ollama": ollama_ok,
        "models": models,
    }


@router.get("/sessions")
async def list_sessions():
    return {"sessions": get_all_sessions()}


@router.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 20):
    msgs = get_recent_messages(session_id, limit=limit)
    return {"messages": msgs}


@router.post("/memory/search")
async def memory_search(req: SearchRequest):
    results = search_memory(req.query, top_k=req.top_k)
    return {"results": [{"content": c, "score": round(s, 3)} for c, s in results]}


@router.get("/facts")
async def get_facts(category: str = None):
    facts = get_all_facts(category)
    return {"facts": facts}


@router.get("/reflections")
async def reflections(limit: int = 5):
    return {"reflections": get_recent_reflections(limit)}


@router.get("/audio/{filename}")
async def serve_audio(filename: str):
    from config.settings import PIPER_OUTPUT_DIR
    path = Path(PIPER_OUTPUT_DIR) / filename
    if not path.exists() or not path.suffix == ".wav":
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(path), media_type="audio/wav")
