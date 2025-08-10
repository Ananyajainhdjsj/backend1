from fastapi import APIRouter
from app.config import ONLINE_MODE, LLM_PROVIDER, GEMINI_API_KEY, AZURE_TTS_KEY

router = APIRouter()

@router.get("/status")
def status():
    services = {
        "pdf_extractor": True,
        "search_index": True,
        "insights": False,
        "tts": False
    }
    if ONLINE_MODE:
        # quick heuristics
        services["insights"] = bool(LLM_PROVIDER and GEMINI_API_KEY)
        services["tts"] = bool(AZURE_TTS_KEY)
    else:
        # local versions available
        services["insights"] = True
        services["tts"] = True
    return {"mode": "online" if ONLINE_MODE else "offline", "services": services}
