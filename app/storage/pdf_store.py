import os
import shutil
from app.config import PDF_DIR
from fastapi import UploadFile

def save_pdf(doc_id: str, upload_file: UploadFile):
    path = os.path.join(PDF_DIR, f"{doc_id}.pdf")
    with open(path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return path

def save_json(doc_id: str, upload_file: UploadFile):
    """Save JSON file to storage"""
    path = os.path.join(PDF_DIR, f"{doc_id}.json")
    with open(path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return path

def list_pdfs():
    """List all documents (PDFs and JSONs)"""
    files = []
    for fn in os.listdir(PDF_DIR):
        if fn.endswith(".pdf") or fn.endswith(".json"):
            files.append(fn[:-4])  # Remove extension
    return files

def get_pdf_path(doc_id: str):
    """Get file path for a document (try PDF first, then JSON)"""
    pdf_path = os.path.join(PDF_DIR, f"{doc_id}.pdf")
    if os.path.exists(pdf_path):
        return pdf_path
    
    json_path = os.path.join(PDF_DIR, f"{doc_id}.json")
    if os.path.exists(json_path):
        return json_path
    
    return None

def get_file_type(doc_id: str):
    """Get the file type for a document"""
    pdf_path = os.path.join(PDF_DIR, f"{doc_id}.pdf")
    if os.path.exists(pdf_path):
        return "pdf"
    
    json_path = os.path.join(PDF_DIR, f"{doc_id}.json")
    if os.path.exists(json_path):
        return "json"
    
    return None
