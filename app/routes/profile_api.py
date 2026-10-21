"""
Dashboard API: the user's profile + stats, and Yashi's editable personality.
"""
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.security import require_app
from core.personalization import persona as persona_store
from core.personalization import profile as profile_store

router = APIRouter(prefix="/api")


# ── User profile ─────────────────────────────────────────────────────────────
@router.get("/profile")
async def get_profile():
    return await run_in_threadpool(profile_store.load_profile)


@router.put("/profile", dependencies=[Depends(require_app)])
async def put_profile(data: dict):
    return await run_in_threadpool(profile_store.save_profile, data)


@router.get("/profile/stats")
async def get_stats():
    return await run_in_threadpool(profile_store.compute_stats)


class CheckIn(BaseModel):
    willpower: int
    health: int
    mood: int
    note: str = ""


@router.post("/profile/checkin", dependencies=[Depends(require_app)])
async def post_checkin(checkin: CheckIn):
    return await run_in_threadpool(
        profile_store.save_checkin, checkin.willpower, checkin.health, checkin.mood, checkin.note
    )


# ── Yashi's personality ──────────────────────────────────────────────────────
@router.get("/persona")
async def get_persona():
    return await run_in_threadpool(persona_store.load)


@router.put("/persona", dependencies=[Depends(require_app)])
async def put_persona(data: dict):
    return await run_in_threadpool(persona_store.save, data)


@router.get("/persona/options")
async def persona_options():
    return {
        "defaults": persona_store.DEFAULT_PERSONA,
        "roles": list(persona_store.ROLES),
        "reply_length": list(persona_store.REPLY_LENGTH),
        "questions": list(persona_store.QUESTIONS),
        "japanese": list(persona_store.JAPANESE),
        "presets": {k: {key: v[key] for key in ("label", "tag", "blurb")} | {"patch": v["patch"]}
                    for k, v in persona_store.PRESETS.items()},
    }


@router.post("/persona/preset/{name}", dependencies=[Depends(require_app)])
async def apply_preset(name: str):
    if name not in persona_store.PRESETS:
        return JSONResponse({"error": "Unknown preset"}, status_code=404)
    return await run_in_threadpool(persona_store.apply_preset, name)


@router.post("/persona/reset", dependencies=[Depends(require_app)])
async def reset_persona():
    return await run_in_threadpool(persona_store.save, persona_store.DEFAULT_PERSONA)


@router.get("/persona/prompt")
async def persona_prompt():
    """The instructions Yashi actually receives (shown as a preview in the editor)."""
    current = await run_in_threadpool(persona_store.load)
    return {"prompt": persona_store.compile_persona(current)}


@router.post("/persona/voice-preview", dependencies=[Depends(require_app)])
async def voice_preview():
    """Speak a short line in Yashi's current voice (ElevenLabs if configured)."""
    from core.voice.elevenlabs_tts import synthesise, tts_backend
    current = await run_in_threadpool(persona_store.load)
    line = f"Hi! It's me, {current['name']}. This is how I sound right now."
    if tts_backend() != "elevenlabs":
        return {"text": line, "audio_path": None}
    path = await synthesise(line, "happy")
    return {"text": line, "audio_path": path.name if path else None}
