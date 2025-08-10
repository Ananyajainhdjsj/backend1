import os
from app.config import AZURE_TTS_KEY, AZURE_TTS_REGION

def azure_tts_generate(text: str, voice: str = "en-US-JennyNeural", fmt="wav"):
    if not AZURE_TTS_KEY or not AZURE_TTS_REGION:
        raise RuntimeError("Azure TTS keys not configured")
    # Implement the Azure Text-to-Speech call here (REST or azure-cognitiveservices-speech)
    # For now raise; fallback will use local TTS.
    raise NotImplementedError("Azure TTS integration not implemented in this template.")
