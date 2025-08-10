from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import json
from app.storage.pdf_store import get_pdf_path, get_file_type
from app.core.pdf_extractor import extract_text
from app.core.chunker import chunk_text
from app.core.embeddings import embed_texts
from app.storage.index_store import add_chunks_to_index

router = APIRouter()

class ChunkRequest(BaseModel):
    doc_id: str
    chunk_size: int = 400

def extract_text_from_json(json_path: str) -> str:
    """Extract text content from JSON file for chunking"""
    with open(json_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    
    text_parts = []
    
    # Extract from subsection_analysis
    if "subsection_analysis" in json_data:
        for item in json_data["subsection_analysis"]:
            text = item.get("refined_text") or item.get("text", "")
            if text:
                text_parts.append(text)
    
    # Extract from extracted_sections if no subsection_analysis
    elif "extracted_sections" in json_data:
        for section in json_data["extracted_sections"]:
            title = section.get("section_title", "")
            if title:
                text_parts.append(title)
    
    return "\n\n".join(text_parts)

@router.post("/doc/{doc_id}/chunk")
def chunk_doc(doc_id: str, body: ChunkRequest):
    file_path = get_pdf_path(doc_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Document not found")
    
    file_type = get_file_type(doc_id)
    
    if file_type == "pdf":
        text = extract_text(file_path)
    elif file_type == "json":
        text = extract_text_from_json(file_path)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    
    chunks = list(chunk_text(text, chunk_size=body.chunk_size))
    # store chunks + embeddings in index store
    ids = add_chunks_to_index(doc_id, chunks)
    return {"doc_id": doc_id, "file_type": file_type, "num_chunks": len(chunks), "chunk_ids": ids}
