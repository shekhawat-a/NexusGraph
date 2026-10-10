"""
upload_router.py - NexusGraph file ingestion (Abhishek)
Accepts: .txt / .pdf / .png / .jpg / .jpeg  -> text -> AI entity extraction
         .csv (bank logs, CDRs)             -> saved + validated only (graph engine reads these directly)
"""
import csv
import logging
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.services.ai_extractor import extract_entities_from_fir

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from PIL import Image
    import pytesseract
    # Windows: if Tesseract is not on PATH, uncomment and fix the path:
    # pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
except ImportError:
    Image = None
    pytesseract = None

try:  # optional: OCR for scanned PDFs (needs the Poppler binaries)
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None

logger = logging.getLogger(__name__)
router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[2]          # backend/
UPLOAD_DIR = BASE_DIR / "data" / "uploads"              # keeps uploads away from the synthetic files
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

OCR_LANGS = os.getenv("OCR_LANGS", "hin+eng")
MAX_UPLOAD_MB = 15
TEXT_EXT, PDF_EXT, CSV_EXT = {".txt"}, {".pdf"}, {".csv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg"}
ALLOWED_EXT = TEXT_EXT | PDF_EXT | CSV_EXT | IMAGE_EXT


def _save_upload(file: UploadFile, safe_name: str) -> Path:
    dest = UPLOAD_DIR / f"{uuid4().hex[:8]}_{safe_name}"
    size = 0
    with open(dest, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File is larger than {MAX_UPLOAD_MB} MB.")
            out.write(chunk)
    return dest


def _ocr_image(img) -> str:
    if Image is None or pytesseract is None:
        raise HTTPException(500, "OCR needs Pillow and pytesseract. Run: pip install Pillow pytesseract")
    try:
        try:
            return pytesseract.image_to_string(img, lang=OCR_LANGS)
        except pytesseract.TesseractError:
            logger.warning("OCR language pack %s missing, falling back to English", OCR_LANGS)
            return pytesseract.image_to_string(img, lang="eng")
    except pytesseract.TesseractNotFoundError:
        raise HTTPException(500, "Tesseract is not installed or not on PATH. See the Windows setup steps.")


def _read_pdf(path: Path, force_ocr: bool):
    """Returns (text, ocr_used)."""
    if not force_ocr:
        if PdfReader is None:
            raise HTTPException(500, "pypdf is not installed. Run: pip install pypdf")
        pages = (page.extract_text() or "" for page in PdfReader(str(path)).pages)
        text = "\n".join(p for p in pages if p.strip())
        if text.strip():
            return text, False
    if convert_from_path is None:
        return "", False  # scanned PDF but no OCR fallback available
    images = convert_from_path(str(path), dpi=200)
    return "\n".join(_ocr_image(im) for im in images), True


def _validate_csv(path: Path) -> dict:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = sum(1 for _ in reader)
    if "txn_id" in headers:
        kind = "bank_log"
    elif "call_id" in headers:
        kind = "cdr"
    else:
        kind = "unknown_csv"
    return {"csv_type": kind, "rows": rows, "columns": headers}


@router.post("/")
def upload_document(file: UploadFile = File(...), force_ocr: bool = False):
    """Ingest FIRs (TXT, PDF, PNG, JPG) for AI extraction, or bank/CDR CSVs for the graph engine."""
    safe_name = Path(file.filename or "").name
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, "Unsupported file format. Upload TXT, PDF, PNG, JPG or CSV.")

    try:
        saved = _save_upload(file, safe_name)

        if ext in CSV_EXT:
            return {"status": "success", "filename": safe_name, "file_type": "csv", **_validate_csv(saved)}

        ocr_used = False
        if ext in TEXT_EXT:
            content = saved.read_text(encoding="utf-8-sig", errors="replace")
        elif ext in PDF_EXT:
            content, ocr_used = _read_pdf(saved, force_ocr)
        else:
            if Image is None:
                raise HTTPException(500, "OCR needs Pillow and pytesseract. Run: pip install Pillow pytesseract")
            content, ocr_used = _ocr_image(Image.open(saved)), True

        if not content.strip():
            return {
                "status": "empty",
                "filename": safe_name,
                "message": "No readable text found. For scanned PDFs install pdf2image + Poppler, or upload it as an image.",
                "ai_extracted_entities": {},
            }

        entities = extract_entities_from_fir(content)
        failed = "error" in entities
        return {
            "status": "partial" if failed else "success",
            "filename": safe_name,
            "file_type": ext.lstrip("."),
            "ocr_used": ocr_used,
            "preview": content[:200].replace("\n", " ") + "...",
            "ai_extracted_entities": entities,
            **({"warning": entities["error"]} if failed else {}),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Upload processing failed")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Error during file processing: {exc}")