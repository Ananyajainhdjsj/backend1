from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import shutil, uuid, os, json
from app.storage.pdf_store import save_pdf, list_pdfs, get_pdf_path
from app.core.pdf_extractor import extract_outline_text

router = APIRouter()

@router.post("/pdf/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload either a PDF file or a JSON file with processed document data"""
    filename = file.filename.lower()
    
    if not (filename.endswith(".pdf") or filename.endswith(".json")):
        raise HTTPException(status_code=400, detail="Only PDF and JSON files are allowed")
    
    doc_id = str(uuid.uuid4())
    
    if filename.endswith(".pdf"):
        # Handle PDF upload
        path = save_pdf(doc_id, file)
        outline, text = extract_outline_text(path)
        return {"doc_id": doc_id, "file_type": "pdf", "outline": outline, "text_preview": text[:1000]}
    
    elif filename.endswith(".json"):
        # Handle JSON upload
        try:
            # Read and validate JSON content
            content = await file.read()
            json_data = json.loads(content.decode('utf-8'))
            
            # Save JSON file to storage
            json_path = save_json_file(doc_id, content)
            
            # Extract preview information from JSON
            preview_info = extract_json_preview(json_data)
            
            return {
                "doc_id": doc_id, 
                "file_type": "json", 
                "outline": preview_info.get("sections", []),
                "text_preview": preview_info.get("preview", ""),
                "metadata": preview_info.get("metadata", {})
            }
            
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON file")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing JSON file: {str(e)}")

def save_json_file(doc_id: str, content: bytes) -> str:
    """Save JSON file to storage and return the path"""
    from app.config import PDF_DIR  # Reuse PDF directory for now
    os.makedirs(PDF_DIR, exist_ok=True)
    
    json_path = os.path.join(PDF_DIR, f"{doc_id}.json")
    with open(json_path, 'wb') as f:
        f.write(content)
    return json_path

def extract_json_preview(json_data: dict) -> dict:
    """Extract preview information from JSON data"""
    preview_info = {
        "sections": [],
        "preview": "",
        "metadata": {}
    }
    
    # Handle different JSON structures
    if "metadata" in json_data:
        preview_info["metadata"] = json_data["metadata"]
    
    # Extract sections from different possible structures
    if "extracted_sections" in json_data:
        for section in json_data["extracted_sections"][:10]:  # Limit to first 10
            preview_info["sections"].append({
                "level": "H1",
                "text": section.get("section_title", "Untitled"),
                "page": section.get("page_number", 0)
            })
    
    # Extract text preview from subsection analysis or other text fields
    text_parts = []
    if "subsection_analysis" in json_data:
        for item in json_data["subsection_analysis"][:3]:  # First 3 items
            text = item.get("refined_text") or item.get("text", "")
            if text:
                text_parts.append(text[:200])  # Limit each part
    
    preview_info["preview"] = " ".join(text_parts)[:1000]  # Total limit
    
    return preview_info

@router.get("/pdf/{doc_id}/file")
def get_file(doc_id: str):
    """Get file by doc_id (supports both PDF and JSON)"""
    path = get_pdf_path(doc_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine file type and set appropriate response
    if path.endswith('.pdf'):
        return FileResponse(path, media_type="application/pdf", filename=f"{doc_id}.pdf")
    elif path.endswith('.json'):
        return FileResponse(path, media_type="application/json", filename=f"{doc_id}.json")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")

@router.get("/pdf/list")
def file_list():
    """List all uploaded documents (PDFs and JSONs)"""
    return {"documents": list_pdfs()}
