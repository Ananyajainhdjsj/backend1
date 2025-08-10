from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.api import pdf, chunks, search, insights, tts, annotations, status

app = FastAPI(title="PDF Insights Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pdf.router, prefix="/api")
app.include_router(chunks.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(insights.router, prefix="/api")
app.include_router(tts.router, prefix="/api")
app.include_router(annotations.router, prefix="/api")
app.include_router(status.router, prefix="/api")

@app.on_event("startup")
def startup_event():
    # Create storage dirs if missing
    from app.config import PDF_DIR, ANNOTATION_DIR, INSIGHTS_DIR, INDEX_DIR
    for d in (PDF_DIR, ANNOTATION_DIR, INSIGHTS_DIR, INDEX_DIR):
        os.makedirs(d, exist_ok=True)
