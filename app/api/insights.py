from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import ONLINE_MODE, LLM_PROVIDER
from app.core.summarizer import extractive_summary
from app.services.gemini_client import gemini_summarize

router = APIRouter()

class InsightsRequest(BaseModel):
    doc_id: str = None
    chunk_text: str = None
    mode: str = "bulb"   # bulb, keypoints, contradictions

@router.post("/insights/summarize")
def summarize(req: InsightsRequest):
    if not req.chunk_text and not req.doc_id:
        raise HTTPException(status_code=400, detail="chunk_text or doc_id required")
    text = req.chunk_text
    if not text and req.doc_id:
        # get doc-level summarization (use extractive on whole doc if present)
        from app.storage.pdf_store import get_pdf_path
        path = get_pdf_path(req.doc_id)
        if not path:
            raise HTTPException(status_code=404, detail="doc not found")
        from app.core.pdf_extractor import extract_text
        text = extract_text(path)
    # Online preference: use Gemini if online and configured
    if ONLINE_MODE and LLM_PROVIDER == "gemini":
        try:
            result = gemini_summarize(text, mode=req.mode)
            return {"source": "gemini", "insights": result}
        except Exception as e:
            # fallback to local extractive summarizer
            pass
    # Offline/default
    summary = extractive_summary(text, num_sentences=4)
    return {"source": "local-extractive", "insights": summary}
