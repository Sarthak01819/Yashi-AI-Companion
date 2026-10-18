"""
Model router — selects which Ollama model to use.
Matches configured names against whatever is actually installed.
"""
import logging
from config.settings import MODEL_MAP, DEFAULT_MODEL

logger = logging.getLogger(__name__)

_available_models: list = []   # original names e.g. ["mistral:latest","phi3:mini"]
_available_lower:  list = []   # lowercase copies for matching


def set_available_models(models: list) -> None:
    global _available_models, _available_lower
    _available_models = list(models)
    _available_lower  = [m.lower() for m in models]
    logger.info("Ollama models available: %s", _available_models)


def select_model(mode: str = "standard") -> str:
    preferred = MODEL_MAP.get(mode, DEFAULT_MODEL)

    if not _available_models:
        logger.warning(
            "No Ollama models loaded yet — using '%s'. "
            "Is 'ollama serve' running?", preferred
        )
        return preferred

    plow = preferred.lower()
    pbase = plow.split(":")[0]  # "mistral" from "mistral:latest"

    # 1. Exact match
    for orig, low in zip(_available_models, _available_lower):
        if plow == low:
            return orig

    # 2. Base name prefix — "mistral" → "mistral:latest"
    for orig, low in zip(_available_models, _available_lower):
        if low.startswith(pbase + ":") or low == pbase:
            logger.info("'%s' matched installed model '%s'", preferred, orig)
            return orig

    # 3. Substring anywhere
    for orig, low in zip(_available_models, _available_lower):
        if pbase in low:
            logger.info("'%s' partial-matched '%s'", preferred, orig)
            return orig

    # 4. Last resort — use first installed model
    fallback = _available_models[0]
    logger.warning(
        "Model '%s' not found in %s — using '%s' as fallback. "
        "Run: ollama pull mistral",
        preferred, _available_models, fallback
    )
    return fallback
