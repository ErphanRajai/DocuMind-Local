import os
from pdf2image import convert_from_path
import pytesseract
from fitz import open as open_pdf 

class PDFProcessorService:

    @staticmethod
    def extract_text(file_path: str) -> str:
        """
        Hybrid Extraction Engine:
        Attempts standard digital text layer extraction first.
        If the page contains zero readable text, it falls back to a local OCR scan.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Target PDF file path not found: {file_path}")

        full_extracted_text = []

        try:
            with open_pdf(file_path) as doc:
                for page_num in range(len(doc)):
                    page_text = doc[page_num].get_text().strip()
                    
                    if len(page_text) > 50:
                        # Digital text layer exists for this page
                        full_extracted_text.append(page_text)
                    else:
                        # Page is likely a scanned image. Trigger fallback OCR for this specific page.
                        print(f"DEBUG: Digital text layer missing or empty on Page {page_num + 1}. Launching OCR...")
                        page_ocr_text = PDFProcessorService._ocr_single_page(file_path, page_num)
                        full_extracted_text.append(page_ocr_text)

        except Exception as e:
            print(f"DEBUG: Digital extraction encountered error, attempting complete file OCR fallback: {str(e)}")
            return PDFProcessorService._ocr_entire_pdf(file_path)

        return "\n\n".join(full_extracted_text)

    @staticmethod
    def _ocr_single_page(file_path: str, page_number: int) -> str:
        """
        Converts a single specific PDF page into a high-res image and runs Tesseract OCR.
        """
        try:
            images = convert_from_path(
                file_path, 
                dpi=300, 
                first_page=page_number + 1, 
                last_page=page_number + 1
            )
            if images:
                # Pass raw PIL Image memory directly to Tesseract
                ocr_text = pytesseract.image_to_string(images[0])
                return ocr_text.strip()
        except Exception as e:
            print(f"ERROR: OCR failed on page {page_number + 1}: {str(e)}")
        return ""

    @staticmethod
    def _ocr_entire_pdf(file_path: str) -> str:
        """
        Total fallback method if the entire file object breaks standard parsing.
        """
        print("DEBUG: Initiating full document image-to-text processing loop...")
        ocr_text_list = []
        try:
            images = convert_from_path(file_path, dpi=200) # Slightly lower DPI for speed on long full fallbacks
            for i, img in enumerate(images):
                text = pytesseract.image_to_string(img)
                ocr_text_list.append(text)
        except Exception as e:
            print(f"CRITICAL: Structural OCR breakdown: {str(e)}")
        return "\n\n".join(ocr_text_list)

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 4000, chunk_overlap: int = 400) -> list[str]:
        """
        Keeps your existing chunking logic intact.
        """
        if not text:
            return []
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - chunk_overlap
        return chunks