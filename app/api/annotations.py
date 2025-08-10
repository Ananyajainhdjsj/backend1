from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Any
from app.storage.annotations_store import load_annotations, save_annotation

router = APIRouter()

class Annotation(BaseModel):
    id: str
    doc_id: str
    body: Any
    target: Any
    created: str = None
    modified: str = None
    user: str = "local"

@router.get("/doc/{doc_id}/annotations")
def get_annotations(doc_id: str):
    anns = load_annotations(doc_id)
    return {"annotations": anns}

@router.post("/doc/{doc_id}/annotations")
def upsert_annotation(doc_id: str, ann: Annotation):
    res = save_annotation(doc_id, ann.dict())
    return {"ok": True, "annotation": res}
