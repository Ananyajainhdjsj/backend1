import os
import uuid
import pyttsx3
from app.config import DATA_DIR

TTS_DIR = os.path.join(DATA_DIR, "tts")
os.makedirs(TTS_DIR, exist_ok=True)

def tts_save_file(text: str, voice: str = None, filename: str = None, speed: float = 1.0):
    engine = pyttsx3.init()
    
    # Set speaking rate (words per minute)
    rate = engine.getProperty('rate')
    engine.setProperty('rate', int(rate * speed))
    
    # Set voice if specified
    if voice and voice != "default":
        voices = engine.getProperty('voices')
        if voices:
            if voice == "male":
                # Try to find a male voice
                for v in voices:
                    if 'male' in v.name.lower() or 'david' in v.name.lower():
                        engine.setProperty('voice', v.id)
                        break
            elif voice == "female":
                # Try to find a female voice
                for v in voices:
                    if 'female' in v.name.lower() or 'zira' in v.name.lower() or 'hazel' in v.name.lower():
                        engine.setProperty('voice', v.id)
                        break
    
    if filename is None:
        filename = f"{uuid.uuid4()}.wav"
    
    outpath = os.path.join(TTS_DIR, filename)
    engine.save_to_file(text, outpath)
    engine.runAndWait()
    engine.stop()
    return outpath
