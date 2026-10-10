import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, status

# Import Jagriti's AI Extractor
from app.services.ai_extractor import extract_entities_from_fir

router = APIRouter()

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

@router.post("/")
async def upload_document(file: UploadFile = File(...)):
    """
    Endpoint to ingest FIR documents and run AI entity extraction on text files.
    """
    try:
        file_location = os.path.join(DATA_DIR, file.filename)
        
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        extracted_data = {}
        content_preview = ""
        
        # If it's a text file (FIR), read it and pass to Groq LLM
        if file.filename.endswith(".txt"):
            with open(file_location, "r", encoding="utf-8") as f:
                content = f.read()
                content_preview = content[:200] + "..."
                
                # Execute Jagriti's AI Extraction
                extracted_data = extract_entities_from_fir(content)
                
        return {
            "status": "success",
            "filename": file.filename,
            "message": "File successfully uploaded.",
            "preview": content_preview,
            "ai_extracted_entities": extracted_data  # AI output goes straight to frontend
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {str(e)}"
        )