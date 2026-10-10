import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from app.services.ai_extractor import extract_entities_from_fir

# 1. Optional PDF Support
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

# 2. Optional Image OCR Support
try:
    from PIL import Image
    import pytesseract
    
    # WINDOWS USERS: Agar Tesseract error de, toh niche wali line se '#' hata kar apna path set kar lena
    # pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
except ImportError:
    Image = None
    pytesseract = None

router = APIRouter()
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

@router.post("/")
async def upload_document(file: UploadFile = File(...)):
    """
    Endpoint to ingest FIR documents (TXT, PDF, PNG, JPG, JPEG) and run AI entity extraction.
    """
    try:
        file_location = os.path.join(DATA_DIR, file.filename)
        
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        extracted_data = {}
        content_preview = ""
        content = ""
        
        ext = file.filename.lower()
        
        # --- A. Handle TEXT files ---
        if ext.endswith(".txt"):
            with open(file_location, "r", encoding="utf-8") as f:
                content = f.read()
                
        # --- B. Handle PDF files ---
        elif ext.endswith(".pdf"):
            if PdfReader is None:
                raise HTTPException(status_code=500, detail="PyPDF is not installed. Run: pip install pypdf")
            reader = PdfReader(file_location)
            content = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
            
        # --- C. Handle IMAGE files (OCR) ---
        elif ext.endswith((".png", ".jpg", ".jpeg")):
            if Image is None or pytesseract is None:
                raise HTTPException(status_code=500, detail="Pillow or pytesseract is not installed. Run: pip install Pillow pytesseract")
            
            # Extract text from image using Tesseract OCR
            img = Image.open(file_location)
            content = pytesseract.image_to_string(img)
            
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload TXT, PDF, PNG, or JPG.")

        # --- D. Send Extracted Text to AI ---
        if content and content.strip():
            content_preview = content[:200].replace("\n", " ") + "..."
            extracted_data = extract_entities_from_fir(content)
        else:
            content_preview = "No readable text could be extracted from the file."
                
        return {
            "status": "success",
            "filename": file.filename,
            "message": "File successfully uploaded and processed.",
            "preview": content_preview,
            "ai_extracted_entities": extracted_data
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during file processing: {str(e)}"
        )