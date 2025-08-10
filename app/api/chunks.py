from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from app.storage.pdf_store import get_pdf_path
from app.core.pdf_extractor import extract_text
from app.core.chunker import chunk_text
from app.core.embeddings import embed_texts
from app.storage.index_store import add_chunks_to_index

router = APIRouter()

class ChunkRequest(BaseModel):
    doc_id: str
    chunk_size: int = 400

@router.post("/doc/{doc_id}/chunk")
def chunk_doc(doc_id: str, body: ChunkRequest):
    pdf_path = get_pdf_path(doc_id)
    if not pdf_path:
        raise HTTPException(status_code=404, detail="doc not found")
    text = extract_text(pdf_path)
    chunks = list(chunk_text(text, chunk_size=body.chunk_size))
    # store chunks + embeddings in index store
    ids = add_chunks_to_index(doc_id, chunks)
    return {"doc_id": doc_id, "num_chunks": len(chunks), "chunk_ids": ids}
