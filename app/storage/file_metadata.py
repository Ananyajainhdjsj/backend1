import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from app.config import PDF_DIR

METADATA_FILE = os.path.join(PDF_DIR, "file_metadata.json")

def load_metadata() -> Dict:
    """Load file metadata from storage"""
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_metadata(metadata: Dict):
    """Save file metadata to storage"""
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

def add_file_metadata(doc_id: str, original_filename: str, file_type: str, file_size: int):
    """Add metadata for a newly uploaded file"""
    metadata = load_metadata()
    metadata[doc_id] = {
        "original_filename": original_filename,
        "file_type": file_type,
        "file_size": file_size,
        "upload_timestamp": datetime.now().isoformat(),
        "doc_id": doc_id
    }
    save_metadata(metadata)

def get_file_metadata(doc_id: str) -> Optional[Dict]:
    """Get metadata for a specific file"""
    metadata = load_metadata()
    return metadata.get(doc_id)

def get_all_files_metadata() -> List[Dict]:
    """Get metadata for all files with original filenames"""
    metadata = load_metadata()
    files_list = []
    
    for doc_id, info in metadata.items():
        # Check if file still exists
        pdf_path = os.path.join(PDF_DIR, f"{doc_id}.pdf")
        json_path = os.path.join(PDF_DIR, f"{doc_id}.json")
        
        if os.path.exists(pdf_path) or os.path.exists(json_path):
            actual_size = 0
            if os.path.exists(pdf_path):
                actual_size = os.path.getsize(pdf_path)
            elif os.path.exists(json_path):
                actual_size = os.path.getsize(json_path)
            
            files_list.append({
                "doc_id": doc_id,
                "original_filename": info.get("original_filename", f"{doc_id}.{info.get('file_type', 'pdf')}"),
                "file_type": info.get("file_type", "pdf"),
                "file_size_bytes": actual_size,
                "upload_timestamp": info.get("upload_timestamp", "unknown")
            })
    
    return sorted(files_list, key=lambda x: x.get("upload_timestamp", ""), reverse=True)

def delete_file_metadata(doc_id: str):
    """Remove metadata for a deleted file"""
    metadata = load_metadata()
    if doc_id in metadata:
        del metadata[doc_id]
        save_metadata(metadata)

def generate_doc_id() -> str:
    """Generate a new unique document ID"""
    return str(uuid.uuid4())
