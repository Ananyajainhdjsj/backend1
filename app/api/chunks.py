from fastapi import APIRouter, HTTPException, UploadFile, File  #type:ignore
from fastapi.responses import HTMLResponse #type:ignore
from pydantic import BaseModel  #type:ignore
from typing import List, Dict, Any
import json
import os
import re
from datetime import datetime
from app.storage.pdf_store import get_pdf_path, get_file_type, list_pdfs, save_pdf, save_json
from app.storage.file_metadata import (
    add_file_metadata, get_all_files_metadata, generate_doc_id, delete_file_metadata
)
from app.core.pdf_extractor import extract_text
from app.core.chunker import chunk_text, chunk_text_advanced
from app.core.extractor import extract_text_from_pdfs
from app.core.ranker import rank_chunks
from app.core.builder import build_output_json
from app.core.embeddings import embed_texts
from app.storage.index_store import add_chunks_to_index
from app.config import PDF_DIR

router = APIRouter()

class ChunkRequest(BaseModel):
    doc_id: str
    chunk_size: int = 400

class PersonaChunkRequest(BaseModel):
    doc_ids: List[str]  # Multiple documents for analysis
    persona: Dict[str, Any]  # {"role": "Data Scientist", "experience": "beginner"}
    job_to_be_done: Dict[str, Any]  # {"task": "understand ML algorithms"}
    job_description: str  # Detailed description of what user wants to learn/do
    chunk_size: int = 400

class PersonaAnalysisResponse(BaseModel):
    persona_analysis: Dict[str, Any]
    relevant_sections: int
    chunk_ids: List[str]
    processing_time: float

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

def simple_chunk_text(text: str, chunk_size: int = 400, doc_id: str = "unknown") -> List[Dict[str, Any]]:
    """
    Simple text chunking for single document processing.
    Splits text into chunks of approximately chunk_size characters.
    """
    MIN_CHUNK_LENGTH = 50
    
    if not text or not text.strip():
        return []
    
    # Split into sentences first
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    
    chunks = []
    current_chunk = ""
    chunk_num = 1
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # If adding this sentence would exceed chunk_size, save current chunk
        if current_chunk and len(current_chunk + " " + sentence) > chunk_size:
            if len(current_chunk.strip()) > MIN_CHUNK_LENGTH:
                chunks.append({
                    "text": current_chunk.strip(),
                    "chunk_number": chunk_num,
                    "doc_id": doc_id
                })
                chunk_num += 1
            current_chunk = sentence
        else:
            current_chunk = current_chunk + " " + sentence if current_chunk else sentence
    
    # Add the final chunk if it has content
    if current_chunk.strip() and len(current_chunk.strip()) > MIN_CHUNK_LENGTH:
        chunks.append({
            "text": current_chunk.strip(),
            "chunk_number": chunk_num,
            "doc_id": doc_id
        })
    
    return chunks

@router.post("/doc/{doc_id}/chunk")
def chunk_doc(doc_id: str, body: ChunkRequest):
    """
    Simple document chunking for single document processing.
    Splits document into fixed-size chunks for basic search indexing.
    """
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
    
    # Use simple chunking for single document
    chunks = simple_chunk_text(text, chunk_size=body.chunk_size, doc_id=doc_id)
    
    # Extract just the text for embedding
    chunk_texts = [chunk["text"] for chunk in chunks]
    
    # store chunks + embeddings in index store
    ids = add_chunks_to_index(doc_id, chunk_texts)
    
    PREVIEW_COUNT = 3
    
    return {
        "doc_id": doc_id, 
        "file_type": file_type, 
        "num_chunks": len(chunks), 
        "chunk_ids": ids,
        "chunks_preview": [chunk["text"][:100] + "..." for chunk in chunks[:PREVIEW_COUNT]]
    }

@router.post("/persona-analyze", response_model=PersonaAnalysisResponse)
def persona_analyze_docs(body: PersonaChunkRequest):
    """
    Intelligent persona-based document analysis.
    Processes multiple PDFs and extracts content relevant to user's persona and goals.
    """
    start_time = datetime.now()
    
    # Validate document IDs
    available_docs = list_pdfs()
    missing_docs = [doc_id for doc_id in body.doc_ids if doc_id not in available_docs]
    if missing_docs:
        raise HTTPException(
            status_code=404, 
            detail=f"Documents not found: {missing_docs}"
        )
    
    try:
        # 1. Prepare input documents list
        input_documents = []
        for doc_id in body.doc_ids:
            file_type = get_file_type(doc_id)
            if file_type == "pdf":
                input_documents.append(f"{doc_id}.pdf")
            elif file_type == "json":
                input_documents.append(f"{doc_id}.json")
            else:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Unsupported file type for document {doc_id}: {file_type}"
                )
        
        # 2. Extract text from all PDFs with advanced extraction
        all_pages = extract_text_from_pdfs(PDF_DIR, input_documents)
        
        if not all_pages:
            raise HTTPException(
                status_code=400, 
                detail="No content could be extracted from the provided documents"
            )
        
        # 3. Advanced chunking with title preservation
        all_chunks = chunk_text_advanced(all_pages)
        
        if not all_chunks:
            raise HTTPException(
                status_code=400, 
                detail="No meaningful chunks could be created from the documents"
            )
        
        # 4. Persona-based ranking and relevance scoring
        ranked_sections, refined_texts = rank_chunks(
            chunks=all_chunks,
            job_description=body.job_description,
            persona=body.persona,
            job_to_be_done=body.job_to_be_done
        )
        
        # 5. Build structured persona-specific output in your desired format
        # Format persona and job_to_be_done as strings for clean display
        persona_str = body.persona.get('role', 'Unknown Role')
        job_str = body.job_to_be_done.get('task', 'Unknown Task')
        
        result = {
            "metadata": {
                "input_documents": input_documents,
                "persona": persona_str,
                "job_to_be_done": job_str,
                "processing_timestamp": datetime.now().isoformat()
            },
            "extracted_sections": [
                {
                    "document": section["document"],
                    "section_title": section.get("title", "Untitled Section"),
                    "importance_rank": i + 1,
                    "page_number": section["page_number"]
                }
                for i, section in enumerate(ranked_sections)
            ],
            "subsection_analysis": [
                {
                    "document": chunk["document"],
                    "refined_text": chunk["refined_text"],
                    "page_number": chunk["page_number"]
                }
                for chunk in refined_texts
            ]
        }
        
        # 6. Create persona-specific search index
        # Generate unique persona identifier for indexing
        persona_hash = hash(f"{body.persona}_{body.job_to_be_done}")
        persona_index_id = f"persona_{abs(persona_hash)}"
        
        # Store the refined, relevant chunks for persona-specific search
        persona_chunks = []
        for chunk in refined_texts:
            persona_chunks.append({
                "text": chunk["refined_text"],
                "document": chunk["document"],
                "page_number": chunk["page_number"],
                "title": chunk["title"],
                "relevance_score": chunk["relevance_score"]
            })
        
        # Add to search index
        chunk_texts = [chunk["text"] for chunk in persona_chunks]
        ids = add_chunks_to_index(persona_index_id, chunk_texts)
        
        # Calculate processing time
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        return PersonaAnalysisResponse(
            persona_analysis=result,
            relevant_sections=len(ranked_sections),
            chunk_ids=ids,
            processing_time=processing_time
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error during persona analysis: {str(e)}"
        )

@router.post("/files/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a PDF or JSON file for analysis.
    Returns the document ID and metadata.
    """
    # Configuration constants
    SUPPORTED_FILE_TYPES = ['pdf', 'json']
    PREVIEW_TEXT_LENGTH = 100
    
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    file_extension = file.filename.lower().split('.')[-1]
    if file_extension not in SUPPORTED_FILE_TYPES:
        raise HTTPException(
            status_code=400, 
            detail=f"Only {', '.join(SUPPORTED_FILE_TYPES).upper()} files are supported"
        )
    
    # Generate unique document ID
    doc_id = generate_doc_id()
    
    try:
        # Read file content to get size
        content = await file.read()
        file_size = len(content)
        
        # Reset file pointer
        await file.seek(0)
        
        # Save file based on type
        if file_extension == 'pdf':
            file_path = save_pdf(doc_id, file)
        else:
            file_path = save_json(doc_id, file)
        
        # Save metadata
        add_file_metadata(
            doc_id=doc_id,
            original_filename=file.filename,
            file_type=file_extension,
            file_size=file_size
        )
        
        return {
            "doc_id": doc_id,
            "original_filename": file.filename,
            "file_type": file_extension,
            "file_size_bytes": file_size,
            "message": "File uploaded successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

@router.delete("/files/{doc_id}")
def delete_file(doc_id: str):
    """
    Delete a file and its metadata.
    """
    file_path = get_pdf_path(doc_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        # Delete the actual file
        os.remove(file_path)
        
        # Delete metadata
        delete_file_metadata(doc_id)
        
        return {"message": "File deleted successfully", "doc_id": doc_id}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

@router.get("/persona-analyze/available-docs")
def get_available_documents():
    """
    Get list of all available documents for persona analysis with original filenames.
    """
    try:
        # Use metadata system to get files with original names
        doc_details = get_all_files_metadata()
        
        # If no metadata exists, fall back to old system
        if not doc_details:
            docs = list_pdfs()
            for doc_id in docs:
                file_type = get_file_type(doc_id)
                file_path = get_pdf_path(doc_id)
                
                if file_path and os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    doc_details.append({
                        "doc_id": doc_id,
                        "original_filename": f"{doc_id}.{file_type}",
                        "file_type": file_type,
                        "file_size_bytes": file_size,
                        "upload_timestamp": "unknown"
                    })
        
        return {
            "available_documents": doc_details,
            "total_count": len(doc_details)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving documents: {str(e)}"
        )



@router.get("/persona-analyze/demo", response_class=HTMLResponse)
def get_demo_page():
    """
    Advanced custom persona analyzer with user input for personas and document selection
    """
    from fastapi.responses import HTMLResponse  #type:ignore
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Custom Persona Analyzer</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; background: #f8f9fa; }
            .header { text-align: center; margin-bottom: 30px; }
            .container { display: flex; gap: 20px; }
            .form-section { flex: 1; background: #fff; padding: 25px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .result-section { flex: 1; background: #fff; padding: 25px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .input-group { margin-bottom: 20px; }
            label { display: block; font-weight: bold; margin-bottom: 8px; color: #333; }
            input, textarea { width: 100%; padding: 12px; margin: 5px 0; border: 2px solid #e1e5e9; border-radius: 6px; font-size: 14px; box-sizing: border-box; }
            input:focus, textarea:focus { border-color: #007bff; outline: none; }
            .persona-inputs { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
            .job-inputs { margin-bottom: 20px; }
            .docs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; max-height: 200px; overflow-y: auto; padding: 10px; border: 2px solid #e1e5e9; border-radius: 6px; }
            .doc-item { display: flex; align-items: center; padding: 8px; background: #f8f9fa; border-radius: 4px; }
            .doc-item input { width: auto; margin-right: 8px; }
            button { background: linear-gradient(135deg, #007bff, #0056b3); color: white; padding: 12px 30px; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%; }
            button:hover { background: linear-gradient(135deg, #0056b3, #004085); }
            .result { background: #f8f9fa; padding: 20px; border-radius: 6px; font-family: 'Courier New', monospace; white-space: pre-wrap; max-height: 600px; overflow-y: auto; font-size: 13px; line-height: 1.4; }
            .loading { color: #666; font-style: italic; text-align: center; }
            .section-header { background: #007bff; color: white; padding: 8px 15px; margin: 10px 0; border-radius: 4px; font-weight: bold; }
            .select-all-btn { background: #28a745; padding: 6px 12px; font-size: 12px; margin-bottom: 10px; width: auto; }
            .example-persona { background: #e7f3ff; padding: 10px; border-radius: 4px; margin: 5px 0; cursor: pointer; border: 1px solid #007bff; }
            .example-persona:hover { background: #d1ecf1; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🧠 Custom Persona Analyzer</h1>
            <p>Create your own persona and analyze documents for personalized insights</p>
        </div>
        
        <div class="container">
            <div class="form-section">
                <h3>📝 Create Your Custom Persona</h3>
                
                <!-- Example Personas for Quick Start -->
                <div class="input-group">
                    <label>💡 Quick Start Examples (click to auto-fill):</label>
                    <div class="example-persona" onclick="fillExample('travel')">
                        🌍 Travel Planner - Planning group trips and itineraries
                    </div>
                    <div class="example-persona" onclick="fillExample('data')">
                        📊 Data Scientist - Learning ML and analytics techniques
                    </div>
                    <div class="example-persona" onclick="fillExample('business')">
                        💼 Business Analyst - Strategic planning and decision making
                    </div>
                    <div class="example-persona" onclick="fillExample('marketing')">
                        📢 Marketing Manager - Brand strategy and campaign planning
                    </div>
                </div>
                
                <form id="personaForm">
                    <div class="input-group">
                        <label>👤 Your Persona Details:</label>
                        <div class="persona-inputs">
                            <div>
                                <input type="text" id="personaRole" placeholder="Your Role (e.g., Marketing Manager)" required>
                            </div>
                            <div>
                                <input type="text" id="personaExperience" placeholder="Experience Level (e.g., beginner, expert)">
                            </div>
                            <div>
                                <input type="text" id="personaBackground" placeholder="Background (e.g., business, technical)">
                            </div>
                            <div>
                                <input type="text" id="personaFocus" placeholder="Focus Areas (e.g., strategy, analytics)">
                            </div>
                        </div>
                    </div>
                    
                    <div class="input-group job-inputs">
                        <label>🎯 What Do You Want to Accomplish?</label>
                        <input type="text" id="jobTask" placeholder="Main Task (e.g., Create a marketing strategy)" required>
                        <input type="text" id="jobGoal" placeholder="End Goal (e.g., Increase brand awareness by 30%)">
                        <input type="text" id="jobTimeline" placeholder="Timeline (e.g., 3 months, Q1 2025)">
                    </div>
                    
                    <div class="input-group">
                        <label>📋 Detailed Description:</label>
                        <textarea id="jobDescription" rows="4" placeholder="Describe in detail what you want to learn or accomplish. Be specific about your needs, challenges, and expected outcomes..." required></textarea>
                    </div>
                    
                    <div class="input-group">
                        <label>📁 Upload New Files (PDF or JSON):</label>
                        <input type="file" id="fileUpload" accept=".pdf,.json" multiple style="margin-bottom: 10px;">
                        <button type="button" onclick="uploadFiles()" style="background: #28a745; width: auto; padding: 8px 16px; font-size: 14px;">📤 Upload Files</button>
                        <div id="uploadStatus" style="margin-top: 10px; font-size: 14px;"></div>
                    </div>
                    
                    <div class="input-group">
                        <label>📄 Select Documents to Analyze:</label>
                        <button type="button" class="select-all-btn" onclick="toggleAllDocs()">Select All / Deselect All</button>
                        <button type="button" class="select-all-btn" onclick="refreshDocuments()" style="background: #17a2b8;">🔄 Refresh List</button>
                        <div id="documentsList" class="docs-grid">Loading documents...</div>
                    </div>
                    
                    <div class="input-group">
                        <label>📏 Chunk Size: <span id="chunkDisplay">400 characters</span></label>
                        <input type="range" id="chunkSize" min="200" max="800" value="400" oninput="updateChunkDisplay()">
                    </div>
                    
                    <button type="submit">🚀 Analyze with My Persona</button>
                </form>
            </div>
            
            <div class="result-section">
                <h3>📊 Analysis Results</h3>
                <div id="results" class="result">Enter your persona details and click "Analyze" to see intelligent document analysis results...</div>
            </div>
        </div>

        <script>
            // Configuration constants
            const CONFIG = {
                DEFAULT_CHUNK_SIZE: 400,
                MIN_CHUNK_SIZE: 200,
                MAX_CHUNK_SIZE: 800,
                DEFAULT_SELECTED_DOCS: 3,
                MIN_CHUNK_LENGTH: 50,
                MAX_PREVIEW_LENGTH: 300,
                UPLOAD_TIMEOUT: 2000
            };

            let allDocsSelected = false;

            window.onload = function() {
                loadDocuments();
            };

            function updateChunkDisplay() {
                const size = document.getElementById('chunkSize').value;
                document.getElementById('chunkDisplay').textContent = size + ' characters';
            }

            function toggleAllDocs() {
                allDocsSelected = !allDocsSelected;
                document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                    cb.checked = allDocsSelected;
                });
            }

            // Example persona data
            const examplePersonas = {
                travel: {
                    role: 'Travel Planner',
                    experience: 'intermediate',
                    background: 'hospitality and tourism',
                    focus: 'group travel, itinerary planning',
                    task: 'Plan a 4-day trip for 10 college friends',
                    goal: 'Create memorable group experience within budget',
                    timeline: '2 weeks',
                    description: 'I need to plan a comprehensive 4-day trip for 10 college friends. Looking for destination recommendations, group activities, budget-friendly accommodation, dining options, and practical travel tips for coordinating a large group.'
                },
                data: {
                    role: 'Data Scientist',
                    experience: 'beginner',
                    background: 'computer science',
                    focus: 'machine learning, statistics',
                    task: 'Learn machine learning fundamentals',
                    goal: 'Build predictive models for business analytics',
                    timeline: '3 months',
                    description: 'I need to understand machine learning algorithms, statistical methods, and data preprocessing techniques to build predictive models for customer analytics and business insights.'
                },
                business: {
                    role: 'Business Analyst',
                    experience: 'intermediate',
                    background: 'business administration',
                    focus: 'strategic planning, process optimization',
                    task: 'Analyze business strategies and processes',
                    goal: 'Improve operational efficiency by 25%',
                    timeline: '6 months',
                    description: 'I need to understand business planning methodologies, organizational structures, and analytical frameworks to identify improvement opportunities and develop strategic recommendations.'
                },
                marketing: {
                    role: 'Marketing Manager',
                    experience: 'advanced',
                    background: 'marketing and communications',
                    focus: 'digital marketing, brand strategy',
                    task: 'Develop comprehensive marketing strategy',
                    goal: 'Increase brand awareness and lead generation',
                    timeline: '4 months',
                    description: 'I need to create a comprehensive marketing strategy that includes digital marketing tactics, brand positioning, customer segmentation, and campaign planning to drive business growth.'
                }
            };

            function fillExample(type) {
                const persona = examplePersonas[type];
                if (!persona) return;
                
                document.getElementById('personaRole').value = persona.role;
                document.getElementById('personaExperience').value = persona.experience;
                document.getElementById('personaBackground').value = persona.background;
                document.getElementById('personaFocus').value = persona.focus;
                document.getElementById('jobTask').value = persona.task;
                document.getElementById('jobGoal').value = persona.goal;
                document.getElementById('jobTimeline').value = persona.timeline;
                document.getElementById('jobDescription').value = persona.description;
            }

            async function uploadFiles() {
                const fileInput = document.getElementById('fileUpload');
                const files = fileInput.files;
                const statusDiv = document.getElementById('uploadStatus');
                
                if (files.length === 0) {
                    statusDiv.innerHTML = '<span style="color: orange;">Please select files to upload</span>';
                    return;
                }
                
                statusDiv.innerHTML = '<span style="color: blue;">⏳ Uploading files...</span>';
                
                let successCount = 0;
                let errorCount = 0;
                
                for (let file of files) {
                    try {
                        const formData = new FormData();
                        formData.append('file', file);
                        
                        const response = await fetch('/api/files/upload', {
                            method: 'POST',
                            body: formData
                        });
                        
                        if (response.ok) {
                            successCount++;
                        } else {
                            errorCount++;
                            console.error(`Failed to upload ${file.name}`);
                        }
                    } catch (error) {
                        errorCount++;
                        console.error(`Error uploading ${file.name}:`, error);
                    }
                }
                
                if (errorCount === 0) {
                    statusDiv.innerHTML = `<span style="color: green;">✅ Successfully uploaded ${successCount} file(s)</span>`;
                } else {
                    statusDiv.innerHTML = `<span style="color: orange;">⚠️ Uploaded ${successCount} file(s), ${errorCount} failed</span>`;
                }
                
                // Clear file input and refresh document list
                fileInput.value = '';
                setTimeout(() => {
                    loadDocuments();
                    statusDiv.innerHTML = '';
                }, CONFIG.UPLOAD_TIMEOUT);
            }

            function refreshDocuments() {
                loadDocuments();
            }

            async function loadDocuments() {
                try {
                    const response = await fetch('/api/persona-analyze/available-docs');
                    const data = await response.json();
                    
                    const docsList = document.getElementById('documentsList');
                    docsList.innerHTML = '';
                    
                    if (data.available_documents.length === 0) {
                        docsList.innerHTML = '<div style="color: #666; text-align: center; padding: 20px;">No documents available. Upload some files to get started!</div>';
                        return;
                    }
                    
                    data.available_documents.forEach((doc, index) => {
                        const div = document.createElement('div');
                        div.className = 'doc-item';
                        div.style.position = 'relative';
                        
                        const checkbox = document.createElement('input');
                        checkbox.type = 'checkbox';
                        checkbox.id = `doc_${doc.doc_id}`;
                        checkbox.value = doc.doc_id;
                        checkbox.checked = index < CONFIG.DEFAULT_SELECTED_DOCS;
                        
                        const label = document.createElement('label');
                        label.htmlFor = `doc_${doc.doc_id}`;
                        label.style.cursor = 'pointer';
                        label.style.fontSize = '12px';
                        label.style.flex = '1';
                        
                        // Show original filename if available, otherwise use doc_id
                        const filename = doc.original_filename || `${doc.doc_id.substring(0, 8)}...`;
                        const fileSize = doc.file_size_bytes ? `(${(doc.file_size_bytes / 1024).toFixed(1)}KB)` : '';
                        label.innerHTML = `${filename} ${fileSize}`;
                        label.title = `File: ${doc.original_filename || doc.doc_id}\\nType: ${doc.file_type.toUpperCase()}\\nSize: ${doc.file_size_bytes} bytes\\nUploaded: ${doc.upload_timestamp || 'Unknown'}`;
                        
                        // Add delete button
                        const deleteBtn = document.createElement('button');
                        deleteBtn.innerHTML = '🗑️';
                        deleteBtn.style.background = 'none';
                        deleteBtn.style.border = 'none';
                        deleteBtn.style.cursor = 'pointer';
                        deleteBtn.style.fontSize = '14px';
                        deleteBtn.style.marginLeft = '5px';
                        deleteBtn.title = 'Delete this file';
                        deleteBtn.onclick = (e) => {
                            e.stopPropagation();
                            deleteDocument(doc.doc_id, doc.original_filename || doc.doc_id);
                        };
                        
                        div.appendChild(checkbox);
                        div.appendChild(label);
                        div.appendChild(deleteBtn);
                        docsList.appendChild(div);
                    });
                } catch (error) {
                    document.getElementById('documentsList').innerHTML = '<div style="color: red;">Error loading documents</div>';
                }
            }

            async function deleteDocument(docId, filename) {
                if (!confirm(`Are you sure you want to delete "${filename}"?`)) {
                    return;
                }
                
                try {
                    const response = await fetch(`/api/files/${docId}`, {
                        method: 'DELETE'
                    });
                    
                    if (response.ok) {
                        loadDocuments(); // Refresh the list
                    } else {
                        alert('Failed to delete file');
                    }
                } catch (error) {
                    alert('Error deleting file: ' + error.message);
                }
            }

            document.getElementById('personaForm').onsubmit = async function(e) {
                e.preventDefault();
                
                const resultsDiv = document.getElementById('results');
                resultsDiv.innerHTML = '<div class="loading">🔄 Analyzing documents with your custom persona...</div>';
                
                // Get selected documents
                const selectedDocs = [];
                document.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
                    selectedDocs.push(cb.value);
                });
                
                if (selectedDocs.length === 0) {
                    resultsDiv.innerHTML = '❌ Please select at least one document to analyze';
                    return;
                }
                
                // Build custom persona object
                const persona = {
                    role: document.getElementById('personaRole').value,
                    experience: document.getElementById('personaExperience').value || 'not specified',
                    background: document.getElementById('personaBackground').value || 'general',
                    focus_areas: document.getElementById('personaFocus').value || 'general analysis'
                };
                
                // Build job to be done object
                const jobToBeDone = {
                    task: document.getElementById('jobTask').value,
                    goal: document.getElementById('jobGoal').value || 'achieve objectives',
                    timeline: document.getElementById('jobTimeline').value || 'flexible'
                };
                
                const requestData = {
                    doc_ids: selectedDocs,
                    persona: persona,
                    job_to_be_done: jobToBeDone,
                    job_description: document.getElementById('jobDescription').value,
                    chunk_size: parseInt(document.getElementById('chunkSize').value)
                };
                
                try {
                    const response = await fetch('/api/persona-analyze', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(requestData)
                    });
                    
                    if (response.ok) {
                        const result = await response.json();
                        displayFormattedResult(result);
                    } else {
                        const error = await response.text();
                        resultsDiv.innerHTML = `❌ Analysis Error: ${error}`;
                    }
                } catch (error) {
                    resultsDiv.innerHTML = `❌ Request Failed: ${error.message}`;
                }
            };

            function displayFormattedResult(result) {
                const analysis = result.persona_analysis;
                let output = '';
                
                // Header with stats
                output += `<div class="section-header">📈 ANALYSIS SUMMARY</div>`;
                output += `⏱️ Processing Time: ${result.processing_time.toFixed(2)} seconds\\n`;
                output += `📊 Relevant Sections Found: ${result.relevant_sections}\\n`;
                output += `🔗 Searchable Chunks Created: ${result.chunk_ids.length}\\n\\n`;
                
                // Metadata
                output += `<div class="section-header">📋 METADATA</div>`;
                output += "input_documents\\n";
                analysis.metadata.input_documents.forEach((doc, i) => {
                    output += `${i}\\t"${doc}"\\n`;
                });
                output += `persona\\t"${analysis.metadata.persona}"\\n`;
                output += `job_to_be_done\\t"${analysis.metadata.job_to_be_done}"\\n`;
                output += `processing_timestamp\\t"${analysis.metadata.processing_timestamp}"\\n\\n`;
                
                // Extracted Sections
                output += `<div class="section-header">🎯 EXTRACTED_SECTIONS</div>`;
                analysis.extracted_sections.forEach((section, i) => {
                    output += `${i}\\n`;
                    output += `document\\t"${section.document}"\\n`;
                    output += `section_title\\t"${section.section_title}"\\n`;
                    output += `importance_rank\\t${section.importance_rank}\\n`;
                    output += `page_number\\t${section.page_number}\\n`;
                });
                
                // Subsection Analysis
                output += `\\n<div class="section-header">📝 SUBSECTION_ANALYSIS</div>`;
                analysis.subsection_analysis.forEach((subsection, i) => {
                    output += `${i}\\n`;
                    output += `document\\t"${subsection.document}"\\n`;
                    const text = subsection.refined_text.length > CONFIG.MAX_PREVIEW_LENGTH ? 
                                 subsection.refined_text.substring(0, CONFIG.MAX_PREVIEW_LENGTH - 3) + "..." : 
                                 subsection.refined_text;
                    output += `refined_text\\t"${text}"\\n`;
                    output += `page_number\\t${subsection.page_number}\\n`;
                });
                
                document.getElementById('results').innerHTML = output;
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
