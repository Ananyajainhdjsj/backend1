#!/usr/bin/env python3
"""
PDF Outline Extractor Tool
Extracts structured outlines from PDF files with titles, headings, and page numbers.
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, List, Optional
import argparse
import logging

try:
    import PyPDF2
    import pdfplumber
except ImportError:
    print("Required libraries not found. Install with:")
    print("pip install PyPDF2 pdfplumber")
    exit(1)

# Optional OCR dependencies
try:
    from pdf2image import convert_from_path
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("OCR libraries not available. Install with: pip install pdf2image pillow pytesseract")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
for lib in ['pdfminer', 'pdfplumber', 'PIL']:
    logging.getLogger(lib).setLevel(logging.WARNING)



def extract_text_with_ocr(pdf_path: str, page_number: int) -> str: #changed lines from 35-45 added lang component
    """Convert a single PDF page to image and extract multilingual text using OCR"""
    if not OCR_AVAILABLE:
        logger.warning("OCR libraries not available, returning empty text")
        return ""
    
    try:
        images = convert_from_path(pdf_path, first_page=page_number, last_page=page_number)
        if images:
            # Use multiple languages: English, Japanese, Arabic, Chinese (simplified), Korean
            ocr_langs = (
                'eng+deu+fra+spa+ita+por+rus+hin+jpn+kor+chi_sim+chi_tra+ara+tur+nld+pol+ces+dan+'
                'swe+ell+heb+tha+vie+ron+ukr+bul+hun+ind+msa+srp+slk+hrv+lav+lit+est+slv+mkd+alb+cat+'
                'glg+eus+isl+mlt+epo+aze'
            )
            ocr_text = pytesseract.image_to_string(images[0], lang=ocr_langs)
            return ocr_text.strip()
    except Exception as e:
        logger.warning(f"OCR failed for page {page_number}: {e}")
    return ""


class PDFOutlineExtractor:
    def __init__(self, max_pages: int = 50):
        self.max_pages = max_pages

    def extract_title(self, pdf_path: str) -> Optional[str]:
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                if pdf_reader.metadata and pdf_reader.metadata.get('/Title'):
                    title = pdf_reader.metadata['/Title']
                    if title and title.strip():
                        return title.strip()
                if len(pdf_reader.pages) > 0:
                    first_page = pdf_reader.pages[0]
                    text = first_page.extract_text()
                    if text:
                        lines = text.split('\n')
                        for line in lines[:10]:
                            line = line.strip()
                            if 10 < len(line) < 100:
                                return line
        except Exception as e:
            logger.warning(f"Could not extract title from {pdf_path}: {e}")
        return None

    def is_heading(self, text: str, font_size: float, avg_font_size: float, line_y: float, prev_line_y: float) -> Optional[str]:
        text = text.strip()
        if len(text) < 3 or len(text) > 200:
            return None
        if re.match(r'^\d+$', text) or text.lower() in ['page', 'copyright', '©']:
            return None
        if re.match(r'^(\d+\.)+\s*[A-Z]', text):
            dots = text.count('.')
            return 'H1' if dots == 1 else 'H2' if dots == 2 else 'H3'
        if re.match(r'^[IVX]+\.\s*[A-Z]', text):
            return 'H1'
        if re.match(r'^[A-Z]\.\s*[A-Z]', text):
            return 'H2'
        font_size_threshold = avg_font_size * 1.1
        if font_size > font_size_threshold:
            return 'H1' if font_size > avg_font_size * 1.4 else 'H2' if font_size > avg_font_size * 1.2 else 'H3'
        if text.isupper() and len(text) > 5:
            return 'H2'
        if text.istitle() and len(text) > 10:
            if prev_line_y and (prev_line_y - line_y) > 20:
                return 'H3'
        return None

    def extract_outline(self, pdf_path: str) -> Dict:
        result = {
            "title": None,
            "outline": []
        }

        try:
            result["title"] = self.extract_title(pdf_path)

            with pdfplumber.open(pdf_path) as pdf:
                pages_to_process = pdf.pages[:self.max_pages] if len(pdf.pages) > self.max_pages else pdf.pages

                all_font_sizes = []
                for page in pages_to_process:
                    for char in page.chars:
                        if char.get('size'):
                            all_font_sizes.append(char['size'])

                avg_font_size = sum(all_font_sizes) / len(all_font_sizes) if all_font_sizes else 12

                for page_index, page in enumerate(pages_to_process):
                    try:
                        if not page.chars:
                            raise ValueError("No selectable text found; trying OCR")
                        self._extract_page_headings(page, page_index, avg_font_size, result["outline"])
                    except Exception as e:
                        logger.warning(f"Page {page_index}: standard extraction failed, trying OCR: {e}")
                        ocr_text = extract_text_with_ocr(pdf_path, page_index + 1)
                        if ocr_text:
                            self._extract_headings_from_ocr_text(ocr_text, page_index, result["outline"])
                        else:
                            logger.warning(f"OCR returned empty text for page {page_index}")
        except Exception as e:
            logger.error(f"Error processing {pdf_path}: {e}")

        return result

    def _extract_headings_from_ocr_text(self, text: str, page_index: int, outline: List[Dict]):
        lines = text.split("\n")
        for line in lines:
            clean = line.strip()
            if not clean or len(clean) < 4:
                continue

            if clean.isupper() and len(clean.split()) <= 10:
                level = "H1"
            elif clean.istitle() and len(clean.split()) <= 12:
                level = "H2"
            elif len(clean.split()) > 6 and clean.endswith('.'):
                level = "H3"
            else:
                continue

            outline.append({
                "level": level,
                "text": clean,
                "page": page_index
            })

    def _extract_page_headings(self, page, page_num: int, avg_font_size: float, headings: List[Dict]):
        try:
            chars = page.chars
            if not chars:
                return

            lines = []
            current_line = []
            current_y = None

            for char in chars:
                char_y = char.get('y0', 0)

                if current_y is None:
                    current_y = char_y
                elif abs(char_y - current_y) > 2:
                    if current_line:
                        lines.append(current_line)
                    current_line = []
                    current_y = char_y

                current_line.append(char)

            if current_line:
                lines.append(current_line)

            prev_y = None
            for line_chars in lines:
                if not line_chars:
                    continue

                text = ''.join(char.get('text', '') for char in line_chars)
                font_sizes = [char.get('size', avg_font_size) for char in line_chars if char.get('size')]
                line_font_size = max(font_sizes) if font_sizes else avg_font_size
                line_y = line_chars[0].get('y0', 0)

                heading_level = self.is_heading(text, line_font_size, avg_font_size, line_y, prev_y)

                if heading_level:
                    headings.append({
                        "level": heading_level,
                        "text": text.strip(),
                        "page": page_num
                    })

                prev_y = line_y

        except Exception as e:
            logger.warning(f"Error extracting headings from page {page_num}: {e}")

    def process_file(self, input_path: str, output_path: str) -> bool:
        try:
            logger.info(f"Processing {input_path}")
            outline = self.extract_outline(input_path)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(outline, f, indent=2, ensure_ascii=False)

            logger.info(f"Extracted {len(outline['outline'])} headings from {input_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to process {input_path}: {e}")
            return False

    def process_directory(self, input_dir: str, output_dir: str) -> Dict[str, bool]:
        input_path = Path(input_dir)
        output_path = Path(output_dir)

        output_path.mkdir(parents=True, exist_ok=True)
        results = {}

        pdf_files = list(input_path.glob('*.pdf'))
        if not pdf_files:
            logger.warning(f"No PDF files found in {input_dir}")
            return results

        logger.info(f"Found {len(pdf_files)} PDF files to process")

        for pdf_file in pdf_files:
            output_file = output_path / f"{pdf_file.stem}.json"
            success = self.process_file(str(pdf_file), str(output_file))
            results[pdf_file.name] = success

        return results


def main():
    parser = argparse.ArgumentParser(description='Extract structured outlines from PDF files')
    parser.add_argument('--input', '-i', default='/app/input',
                        help='Input directory containing PDF files (default: /app/input)')
    parser.add_argument('--output', '-o', default='/app/output',
                        help='Output directory for JSON files (default: /app/output)')
    parser.add_argument('--max-pages', '-m', type=int, default=50,
                        help='Maximum number of pages to process per PDF (default: 50)')
    parser.add_argument('--file', '-f', help='Process a single PDF file')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    extractor = PDFOutlineExtractor(max_pages=args.max_pages)

    if args.file:
        input_file = Path(args.file)
        if not input_file.exists():
            logger.error(f"File not found: {args.file}")
            return 1

        output_file = Path(args.output) / f"{input_file.stem}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        success = extractor.process_file(str(input_file), str(output_file))
        return 0 if success else 1
    else:
        if not Path(args.input).exists():
            logger.error(f"Input directory not found: {args.input}")
            return 1

        results = extractor.process_directory(args.input, args.output)

        total_files = len(results)
        successful_files = sum(1 for success in results.values() if success)

        print(f"\nProcessing Summary:")
        print(f"Total files: {total_files}")
        print(f"Successful: {successful_files}")
        print(f"Failed: {total_files - successful_files}")

        if total_files > 0:
            print(f"Success rate: {successful_files / total_files * 100:.1f}%")

        return 0 if successful_files == total_files else 1


if __name__ == "__main__":
    exit(main())
# This code is a complete implementation of a PDF outline extractor tool that can be run as a script.
# It extracts structured outlines from PDF files, including titles, headings, and page numbers,
# and saves them as JSON files in the specified output directory.