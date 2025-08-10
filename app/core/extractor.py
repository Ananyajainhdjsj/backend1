import fitz  # PyMuPDF # type: ignore
import os
import re

def extract_text_from_pdfs(pdf_dir, input_documents):
    pages = []
    for filename in input_documents:
        path = os.path.join(pdf_dir, filename)
        doc = fitz.open(path)
        
        for i, page in enumerate(doc):
            blocks = page.get_text("dict")["blocks"]
            text = ""
            title = None
            
            # Collect all text spans with their properties
            text_spans = []
            
            for block in blocks:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    for span in line["spans"]:
                        span_text = span["text"].strip()
                        if not span_text:
                            continue
                            
                        text += span_text + " "
                        
                        # Store span info for title detection
                        text_spans.append({
                            'text': span_text,
                            'size': span["size"],
                            'flags': span.get("flags", 0),  # Bold, italic flags
                            'bbox': span["bbox"],  # Position on page
                            'y_pos': span["bbox"][1]  # Y position for ordering
                        })
            
            # Find the best title candidate
            title = find_best_title(text_spans)
            
            pages.append({
                "document": filename,
                "page_number": i + 1,
                "text": text.strip(),
                "title": title if title else f"Page {i + 1}"
            })
            
        doc.close()
    return pages

def find_best_title(text_spans):
    """
    Find the best title candidate from text spans using multiple criteria
    """
    if not text_spans:
        return None
    
    # Sort spans by Y position (top to bottom)
    text_spans.sort(key=lambda x: x['y_pos'])
    
    # Get spans from the top 30% of the page for title candidates
    max_y = max(span['y_pos'] for span in text_spans)
    min_y = min(span['y_pos'] for span in text_spans)
    top_30_percent = min_y + (max_y - min_y) * 0.3
    
    top_spans = [span for span in text_spans if span['y_pos'] <= top_30_percent]
    
    if not top_spans:
        top_spans = text_spans[:3]  # Fallback to first 3 spans
    
    # Score each span for title likelihood
    candidates = []
    avg_font_size = sum(span['size'] for span in text_spans) / len(text_spans)
    
    for span in top_spans:
        text = span['text'].strip()
        
        # Skip very short or very long text
        if len(text) < 3 or len(text) > 100:
            continue
            
        # Skip text that looks like body content
        if is_body_text(text):
            continue
        
        score = calculate_title_score(span, text, avg_font_size)
        
        if score > 0:
            candidates.append((text, score))
    
    # Return the highest scoring candidate
    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
    
    # Fallback: return first meaningful text
    for span in text_spans[:5]:
        text = span['text'].strip()
        if len(text) >= 3 and not is_body_text(text):
            return text
    
    return None

def calculate_title_score(span, text, avg_font_size):
    """
    Calculate a score for how likely this text is to be a title
    """
    score = 0
    
    # Font size bonus (larger fonts are more likely to be titles)
    if span['size'] > avg_font_size * 1.2:
        score += 30
    elif span['size'] > avg_font_size:
        score += 15
    
    # Bold text bonus
    if span['flags'] & 2**4:  # Bold flag
        score += 20
    
    # Position bonus (higher on page = more likely to be title)
    score += max(0, 10 - span['y_pos'] / 20)
    
    # Length bonus (titles are usually medium length)
    word_count = len(text.split())
    if 2 <= word_count <= 10:
        score += 15
    elif 1 <= word_count <= 15:
        score += 10
    
    # Capitalization patterns
    if text.isupper():
        score += 10
    elif text.istitle():
        score += 15
    
    # Penalize certain patterns
    if re.search(r'^\d+\.', text):  # Starts with number and dot
        score -= 10
    
    if any(phrase in text.lower() for phrase in ['page', 'continued', 'chapter']):
        score += 5
    
    return score

def is_body_text(text):
    """
    Check if text looks like body content rather than a title
    """
    # Very long sentences are likely body text
    if len(text) > 200:
        return True
    
    # Multiple sentences are likely body text
    if text.count('.') > 1:
        return True
    
    # Common body text patterns
    body_patterns = [
        r'^this\s+guide',
        r'^welcome\s+to',
        r'^in\s+this\s+section',
        r'^\d+\.\s+',  # Numbered lists
        r'^•\s+',      # Bullet points
        r'page\s+\d+',
        r'copyright',
        r'all\s+rights\s+reserved'
    ]
    
    for pattern in body_patterns:
        if re.search(pattern, text.lower()):
            return True
    
    return False