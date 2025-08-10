# app/chunker.py
import re

def chunk_text(pages):
    chunks = []
    for item in pages:
        # Split text into blocks at sentence boundaries
        text_blocks = re.split(r'(?<=\.)\s+(?=[A-Z])', item['text'])
        
        for i, block in enumerate(text_blocks):
            cleaned = block.strip()
            if len(cleaned) > 100:  # Only keep substantial chunks
                chunks.append({
                    "document": item["document"],
                    "page_number": item["page_number"],
                    "text": cleaned,
                    # PRESERVE the original title from PDF extraction
                    "title": item["title"]  
                })
    return chunks

def chunk_text_advanced(pages):
    """
    Advanced chunking that can create multiple chunks per page while preserving titles
    """
    chunks = []
    for item in pages:
        text = item['text']
        original_title = item["title"]
        
        # Split into paragraphs first
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_chunk = ""
        chunk_count = 0
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
                
            # If adding this paragraph would make chunk too long, save current chunk
            if len(current_chunk) > 0 and len(current_chunk + paragraph) > 1000:
                chunks.append({
                    "document": item["document"],
                    "page_number": item["page_number"],
                    "text": current_chunk.strip(),
                    "title": original_title if chunk_count == 0 else f"{original_title} (Part {chunk_count + 1})"
                })
                chunk_count += 1
                current_chunk = paragraph
            else:
                current_chunk += " " + paragraph if current_chunk else paragraph
        
        # Add the final chunk if it has content
        if current_chunk.strip() and len(current_chunk.strip()) > 100:
            chunks.append({
                "document": item["document"],
                "page_number": item["page_number"],
                "text": current_chunk.strip(),
                "title": original_title if chunk_count == 0 else f"{original_title} (Part {chunk_count + 1})"
            })
    
    return chunks