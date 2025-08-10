from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from app.core.embeddings import embed_texts
from app.storage.index_store import search_index, get_chunk_by_id

router = APIRouter()

class SearchQuery(BaseModel):
    query: str
    k: int = 5

@router.post("/search")
def search(q: SearchQuery):
    q_emb = embed_texts([q.query])
    results = search_index(q_emb[0], k=q.k)
    # results: list of (chunk_id, score)
    out = []
    for chunk_id, score in results:
        chunk = get_chunk_by_id(chunk_id)
        out.append({"chunk_id": chunk_id, "score": float(score), "text_snippet": chunk[:300]})
    return {"results": out}
