"""
PDF text extraction utilities for the API
"""
from typing import Tuple, List, Dict, Any
from .pdf_outline_extractor import PDFOutlineExtractor
import pdfplumber


def extract_text(pdf_path: str) -> str:
    """
    Extract all text content from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        String containing all text from the PDF
    """
    text_content = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_content += page_text + "\n"
    except Exception as e:
        # Return error info if extraction fails
        text_content = f"Error extracting text: {str(e)}"
    
    return text_content


def extract_outline_text(pdf_path: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    Extract outline and text preview from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Tuple of (outline, text_preview)
        - outline: List of headings with level, text, and page information
        - text_preview: Raw text content from first few pages
    """
    # Extract outline using PDFOutlineExtractor
    extractor = PDFOutlineExtractor(max_pages=10)  # Limit to first 10 pages for preview
    result = extractor.extract_outline(pdf_path)
    outline = result.get("outline", [])
    
    # Extract text preview
    text_preview = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Extract text from first 3 pages for preview
            pages_to_read = min(3, len(pdf.pages))
            for i in range(pages_to_read):
                page_text = pdf.pages[i].extract_text()
                if page_text:
                    text_preview += page_text + "\n"
    except Exception as e:
        # Fallback to empty text if extraction fails
        text_preview = f"Error extracting text: {str(e)}"
    
    return outline, text_preview
