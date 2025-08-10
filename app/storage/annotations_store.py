import os, json
from app.config import ANNOTATION_DIR

def _path(doc_id):
    return os.path.join(ANNOTATION_DIR, f"{doc_id}.json")

def load_annotations(doc_id: str):
    p = _path(doc_id)
    if not os.path.exists(p):
        return []
    return json.load(open(p, "r"))

def save_annotation(doc_id: str, annotation: dict):
    anns = load_annotations(doc_id)
    # simple upsert by id
    ids = [a.get("id") for a in anns]
    if annotation.get("id") in ids:
        for i, a in enumerate(anns):
            if a.get("id") == annotation.get("id"):
                anns[i] = annotation
                break
    else:
        anns.append(annotation)
    with open(_path(doc_id), "w") as f:
        json.dump(anns, f, indent=2)
    return annotation
