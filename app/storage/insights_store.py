import os, json
from app.config import INSIGHTS_DIR

def save_insight(doc_id: str, chunk_id: str, insight: dict):
    d = os.path.join(INSIGHTS_DIR, doc_id)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{chunk_id}.json")
    with open(path, "w") as f:
        json.dump(insight, f)
    return path

def load_insight(doc_id: str, chunk_id: str):
    path = os.path.join(INSIGHTS_DIR, doc_id, f"{chunk_id}.json")
    if not os.path.exists(path):
        return None
    return json.load(open(path, "r"))
