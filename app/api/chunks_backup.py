from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Dict, Any
import json
import os
import re
from datetime import datetime
from app.storage.pdf_store import get_pdf_path, get_file_type, list_pdfs
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
            if len(current_chunk.strip()) > 50:  # Only save substantial chunks
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
    if current_chunk.strip() and len(current_chunk.strip()) > 50:
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
    
    return {
        "doc_id": doc_id, 
        "file_type": file_type, 
        "num_chunks": len(chunks), 
        "chunk_ids": ids,
        "chunks_preview": [chunk["text"][:100] + "..." for chunk in chunks[:3]]  # Show preview of first 3 chunks
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

@router.get("/persona-analyze/available-docs")
def get_available_documents():
    """
    Get list of all available documents for persona analysis.
    """
    docs = list_pdfs()
    doc_details = []
    
    for doc_id in docs:
        file_type = get_file_type(doc_id)
        file_path = get_pdf_path(doc_id)
        
        if file_path and os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            doc_details.append({
                "doc_id": doc_id,
                "file_type": file_type,
                "file_size_bytes": file_size
            })
    
    return {
        "available_documents": doc_details,
        "total_count": len(doc_details)
    }

@router.get("/persona-analyze/example")
def get_persona_example():
    """
    Get example request format for persona analysis.
    """
    return {
        "example_request": {
            "doc_ids": ["doc1", "doc2", "doc3"],
            "persona": {
                "role": "Data Scientist",
                "experience": "beginner",
                "background": "computer science",
                "focus_areas": ["machine learning", "statistics"]
            },
            "job_to_be_done": {
                "task": "understand machine learning fundamentals",
                "goal": "implement ML models",
                "timeline": "3 months"
            },
            "job_description": "I need to learn machine learning algorithms to build predictive models for customer analytics. Focus on supervised learning techniques and practical implementation.",
            "chunk_size": 400
        },
        "expected_output": {
            "persona_analysis": "Structured analysis with relevant sections",
            "relevant_sections": "Number of top-ranked sections",
            "chunk_ids": "List of searchable chunk IDs",
            "processing_time": "Time taken in seconds"
        }
    }

@router.get("/persona-analyze/demo", response_class=HTMLResponse)
def get_demo_page():
    """
    Demo page to test persona analysis in browser
    """
    from fastapi.responses import HTMLResponse
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Persona Analyzer Demo</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; color: #333; }
            input, textarea, select { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 14px; }
            button { background: #007bff; color: white; padding: 12px 30px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
            button:hover { background: #0056b3; }
            .result { margin-top: 30px; padding: 20px; background: #f8f9fa; border-radius: 5px; border-left: 4px solid #007bff; }
            .loading { color: #666; font-style: italic; }
            .error { color: #dc3545; background: #f8d7da; border-color: #dc3545; }
            .success { color: #155724; background: #d4edda; border-color: #28a745; }
            pre { background: #f1f1f1; padding: 15px; border-radius: 5px; overflow-x: auto; font-size: 12px; }
            .example-box { background: #e7f3ff; padding: 15px; border-radius: 5px; margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🧠 Persona Analyzer Demo</h1>
            <p>Test the intelligent document analysis API with different personas and goals.</p>
            
            <div class="example-box">
                <h3>📋 Output Format Preview</h3>
                <pre>metadata
input_documents
0    "document1.pdf"
1    "document2.pdf"
persona    "Travel Planner"
job_to_be_done    "Plan a trip of 4 days for a group of 10 college friends"
processing_timestamp    "2025-08-11T12:30:13.351174"

extracted_sections
0
    document    "document1.pdf"
    section_title    "Planning Tips"
    importance_rank    1
    page_number    1

subsection_analysis
0
    document    "document1.pdf"
    refined_text    "Key travel planning advice..."
    page_number    1</pre>
            </div>
            
            <form id="personaForm">
                <div class="form-group">
                    <label>Persona Role:</label>
                    <select id="persona" required>
                        <option value="">Select a persona...</option>
                        <option value="Travel Planner">Travel Planner</option>
                        <option value="Data Scientist">Data Scientist</option>
                        <option value="Business Analyst">Business Analyst</option>
                        <option value="Software Engineer">Software Engineer</option>
                        <option value="Student">Student</option>
                        <option value="Research Scientist">Research Scientist</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label>Job To Be Done:</label>
                    <input type="text" id="job" placeholder="e.g., Plan a 4-day trip for college friends" required>
                </div>
                
                <div class="form-group">
                    <label>Detailed Description:</label>
                    <textarea id="description" rows="4" placeholder="Describe what you want to achieve in detail..." required></textarea>
                </div>
                
                <div class="form-group">
                    <label>Number of Documents (1-5):</label>
                    <input type="number" id="docCount" value="2" min="1" max="5">
                </div>
                
                <button type="submit">🚀 Analyze Documents</button>
            </form>
            
            <div id="result" class="result" style="display: none;">
                <h3>📊 Analysis Result</h3>
                <div id="resultContent"></div>
            </div>
        </div>
        
        <script>
            document.getElementById('personaForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                
                const resultDiv = document.getElementById('result');
                const contentDiv = document.getElementById('resultContent');
                
                // Show loading
                resultDiv.style.display = 'block';
                resultDiv.className = 'result loading';
                contentDiv.innerHTML = '⏳ Analyzing documents...';
                
                try {
                    // First get available documents
                    const docsResponse = await fetch('/api/persona-analyze/available-docs');
                    const docsData = await docsResponse.json();
                    const availableDocs = docsData.available_documents.slice(0, parseInt(document.getElementById('docCount').value));
                    
                    // Prepare request
                    const requestData = {
                        doc_ids: availableDocs.map(doc => doc.doc_id),
                        persona: { role: document.getElementById('persona').value },
                        job_to_be_done: { task: document.getElementById('job').value },
                        job_description: document.getElementById('description').value,
                        chunk_size: 400
                    };
                    
                    // Send analysis request
                    const response = await fetch('/api/persona-analyze', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(requestData)
                    });
                    
                    if (response.ok) {
                        const result = await response.json();
                        resultDiv.className = 'result success';
                        
                        // Format the output
                        let formattedOutput = formatPersonaResult(result);
                        contentDiv.innerHTML = `
                            <p><strong>✅ Analysis completed in ${result.processing_time.toFixed(2)} seconds</strong></p>
                            <p><strong>📊 Found ${result.relevant_sections} relevant sections</strong></p>
                            <h4>📋 Formatted Output:</h4>
                            <pre>${formattedOutput}</pre>
                        `;
                    } else {
                        throw new Error(`HTTP ${response.status}: ${await response.text()}`);
                    }
                    
                } catch (error) {
                    resultDiv.className = 'result error';
                    contentDiv.innerHTML = `❌ Error: ${error.message}`;
                }
            });
            
            function formatPersonaResult(result) {
                const analysis = result.persona_analysis;
                let output = '';
                
                // Metadata
                output += 'metadata\\n';
                output += 'input_documents\\n';
                analysis.metadata.input_documents.forEach((doc, i) => {
                    output += `${i}\\t"${doc}"\\n`;
                });
                output += `persona\\t"${analysis.metadata.persona}"\\n`;
                output += `job_to_be_done\\t"${analysis.metadata.job_to_be_done}"\\n`;
                output += `processing_timestamp\\t"${analysis.metadata.processing_timestamp}"\\n`;
                
                // Extracted sections
                output += '\\nextracted_sections\\n';
                analysis.extracted_sections.forEach((section, i) => {
                    output += `${i}\\n`;
                    output += `document\\t"${section.document}"\\n`;
                    output += `section_title\\t"${section.section_title}"\\n`;
                    output += `importance_rank\\t${section.importance_rank}\\n`;
                    output += `page_number\\t${section.page_number}\\n`;
                });
                
                // Subsection analysis
                output += '\\nsubsection_analysis\\n';
                analysis.subsection_analysis.forEach((sub, i) => {
                    output += `${i}\\n`;
                    output += `document\\t"${sub.document}"\\n`;
                    let text = sub.refined_text;
                    if (text.length > 200) text = text.substring(0, 197) + '...';
                    output += `refined_text\\t"${text}"\\n`;
                    output += `page_number\\t${sub.page_number}\\n`;
                });
                
                return output;
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
