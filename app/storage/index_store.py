try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("Warning: faiss not available. Install with: pip install faiss-cpu")

import numpy as np
import os
import json
import sqlite3
import uuid
from app.config import INDEX_DIR

MAPPING_DB = os.path.join(INDEX_DIR, "mapping.db")
VECTORS_FILE = os.path.join(INDEX_DIR, "vectors.npy")
IDS_FILE = os.path.join(INDEX_DIR, "ids.json")

# Ensure DB exists
def _ensure_mapping_db():
    """Set up database for chunk_id -> doc_id/text mappings."""
    # Ensure the directory exists
    os.makedirs(os.path.dirname(MAPPING_DB), exist_ok=True)
    
    conn = sqlite3.connect(MAPPING_DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        doc_id TEXT,
        text TEXT
    )''')
    conn.commit()
    conn.close()

_ensure_mapping_db()

# In-memory FAISS index (flat L2). For large corpora replace with IndexIVFFlat or HNSW.
_index = None
_ids = []  # map index position -> chunk_id

def _load_index():
    global _index, _ids
    if _index is not None:
        return
    
    if not FAISS_AVAILABLE:
        _index = None
        _ids = []
        return
        
    if os.path.exists(VECTORS_FILE) and os.path.exists(IDS_FILE):
        vecs = np.load(VECTORS_FILE)
        _ids = json.load(open(IDS_FILE, "r"))
        dim = vecs.shape[1]
        _index = faiss.IndexFlatL2(dim)
        _index.add(vecs)
    else:
        _index = None
        _ids = []

_load_index()

def add_chunks_to_index(doc_id: str, chunks: list, embeddings=None):
    """chunks: list[str] - if embeddings provided, must match order. returns new chunk ids"""
    import numpy as np
    
    if not FAISS_AVAILABLE:
        # Without FAISS, just store in database without vector search capability
        conn = sqlite3.connect(MAPPING_DB)
        c = conn.cursor()
        chunk_ids = []
        for txt in chunks:
            cid = str(uuid.uuid4())
            c.execute("INSERT OR REPLACE INTO chunks (chunk_id, doc_id, text) VALUES (?, ?, ?)", (cid, doc_id, txt))
            chunk_ids.append(cid)
        conn.commit()
        conn.close()
        return chunk_ids
    
    conn = sqlite3.connect(MAPPING_DB)
    c = conn.cursor()
    chunk_ids = []
    embs = embeddings
    if embs is None:
        # lazy: compute embeddings here if not passed
        from app.core.embeddings import embed_texts
        embs = embed_texts(chunks)
    global _index, _ids
    if _index is None:
        # initialize index
        dim = len(embs[0]) if embs else 384  # fallback dimension
        _index = faiss.IndexFlatL2(dim)
    # add each chunk text & mapping
    for i, txt in enumerate(chunks):
        cid = str(uuid.uuid4())
        c.execute("INSERT OR REPLACE INTO chunks (chunk_id, doc_id, text) VALUES (?, ?, ?)", (cid, doc_id, txt))
        chunk_ids.append(cid)
        vec = np.array(embs[i], dtype='float32').reshape(1, -1)
        _index.add(vec)
        _ids.append(cid)
    conn.commit()
    conn.close()
    # persist vectors and ids
    # NOTE: rebuilding vector store by extracting from index isn't trivial; we append to saved arrays for simplicity
    # Here we reconstruct saved arrays from current index (costly but simple).
    all_vecs = np.zeros((_index.ntotal, _index.d), dtype='float32')
    _index.reconstruct_n(0, _index.ntotal, all_vecs)
    np.save(VECTORS_FILE, all_vecs)
    with open(IDS_FILE, "w") as f:
        json.dump(_ids, f)
    return chunk_ids

def search_index(query_vec, k=5):
    import numpy as np
    
    if not FAISS_AVAILABLE:
        # Without FAISS, return empty results (or could implement simple text search)
        return []
    
    global _index, _ids
    if _index is None or _index.ntotal == 0:
        return []
    q = np.array(query_vec, dtype='float32').reshape(1, -1)
    D, I = _index.search(q, k)
    results = []
    for dist, idx in zip(D[0], I[0]):
        if idx < 0:
            continue
        cid = _ids[idx]
        results.append((cid, float(dist)))
    return results

def get_chunk_by_id(chunk_id: str):
    conn = sqlite3.connect(MAPPING_DB)
    c = conn.cursor()
    c.execute("SELECT text FROM chunks WHERE chunk_id = ?", (chunk_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""
