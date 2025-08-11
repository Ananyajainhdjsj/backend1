import os

# Mode detection
ONLINE_MODE = os.getenv("ONLINE_MODE", "false").lower() in ("1", "true", "yes")

# Use local data directory in development, /app/storage in container
if os.path.exists("/app"):
    # Running in container
    DATA_DIR = os.getenv("DATA_DIR", "/app/storage")
else:
    # Running locally
    DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.getcwd(), "data"))

import os

# PDF storage directory
PDF_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "pdfs")

# Adobe PDF Embed API configuration
ADOBE_PDF_CLIENT_ID = os.getenv("ADOBE_PDF_CLIENT_ID", "")

# Ensure PDF directory exists
os.makedirs(PDF_DIR, exist_ok=True)
ANNOTATION_DIR = os.path.join(DATA_DIR, "annotations")
INSIGHTS_DIR = os.path.join(DATA_DIR, "insights")
INDEX_DIR = os.path.join(DATA_DIR, "index")

# External providers envs (optional)
LLM_PROVIDER = os.getenv("LLM_PROVIDER")              # e.g. "gemini" or "local"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
AZURE_TTS_KEY = os.getenv("AZURE_TTS_KEY")
AZURE_TTS_REGION = os.getenv("AZURE_TTS_REGION")
