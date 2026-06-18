from app.services.pdf_processor import PDFProcessorService
import os

# Create a small dummy text file or use a real PDF path
pdf_path = "./uploaded_pdfs/AI in Medical Imaging & Diagnostic.pdf"  # Replace with the name of the PDF you uploaded earlier

if os.path.exists(pdf_path):
    print("--- Testing Text Extraction ---")
    raw_text = PDFProcessorService.extract_text(pdf_path)
    print(f"Extracted Character Length: {len(raw_text)}")
    print("First 200 characters:")
    print(raw_text[:200])
    
    print("\n--- Testing Chunking ---")
    chunks = PDFProcessorService.chunk_text(raw_text, chunk_size=500, chunk_overlap=100)
    print(f"Total Chunks Created: {len(chunks)}")
    print("Chunk 1 Summary Length:", len(chunks[0]))
else:
    print(f"Please place a valid PDF at {pdf_path} or change the script path to test.")