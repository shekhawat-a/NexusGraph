"""File ingestion and multi-crime entity extraction endpoints."""
from __future__ import annotations

import csv
import io
import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.services.ai_extractor import extract_entities_from_fir, extract_text_from_image
from app.services.crime_entity_parser import (
    build_entity_graph,
    parse_multi_crime_entities,
)

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - optional dependency
    PdfReader = None

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - optional dependency
    fitz = None

try:
    from PIL import Image
    import pytesseract
except ImportError:  # pragma: no cover - optional dependency
    Image = None
    pytesseract = None

logger = logging.getLogger(__name__)
router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

OCR_LANGS = os.getenv("OCR_LANGS", "hin+eng")
MAX_UPLOAD_MB = 15
MAX_PDF_PAGES = 50
MAX_IMAGE_PIXELS = 40_000_000
TEXT_EXT, PDF_EXT, CSV_EXT = {".txt"}, {".pdf"}, {".csv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg"}
ALLOWED_EXT = TEXT_EXT | PDF_EXT | CSV_EXT | IMAGE_EXT
ALLOWED_MIME_TYPES = {
    ".txt": {"text/plain"},
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"},
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
}
GENERIC_MIME_TYPES = {"", "application/octet-stream", "binary/octet-stream"}


def _save_upload(file: UploadFile, safe_name: str) -> tuple[Path, str]:
    upload_id = uuid4().hex
    dest = UPLOAD_DIR / f"{upload_id}_{safe_name}"
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"File is larger than {MAX_UPLOAD_MB} MB.",
                    )
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty.")
    return dest, upload_id


def _validate_content(path: Path, ext: str, content_type: str | None) -> None:
    mime_type = (content_type or "").split(";", 1)[0].strip().lower()
    if mime_type not in GENERIC_MIME_TYPES and mime_type not in ALLOWED_MIME_TYPES[ext]:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Content-Type {mime_type!r} does not match the {ext} file extension.",
        )

    with path.open("rb") as uploaded:
        header = uploaded.read(16)
    signatures = {
        ".pdf": header.startswith(b"%PDF-"),
        ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": header.startswith(b"\xff\xd8\xff"),
        ".jpeg": header.startswith(b"\xff\xd8\xff"),
    }
    if ext in signatures and not signatures[ext]:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"The uploaded content is not a valid {ext} file.",
        )
    if ext in TEXT_EXT | CSV_EXT:
        if b"\x00" in header:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "Text and CSV uploads must contain text, not binary data.",
            )


def _ocr_image(img: Any) -> str:
    if Image is None or pytesseract is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Image OCR is unavailable. Install Pillow and pytesseract, and install the Tesseract OCR executable.",
        )
    try:
        return pytesseract.image_to_string(img, lang=OCR_LANGS)
    except pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Tesseract is not installed or not available on PATH.",
        ) from exc
    except pytesseract.TesseractError as exc:
        logger.warning("OCR language configuration %s failed; retrying English: %s", OCR_LANGS, exc)
        try:
            return pytesseract.image_to_string(img, lang="eng")
        except pytesseract.TesseractNotFoundError as fallback_exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Tesseract is not installed or not available on PATH.",
            ) from fallback_exc
        except pytesseract.TesseractError as fallback_exc:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                f"Tesseract OCR failed. Verify the executable and language data: {fallback_exc}",
            ) from fallback_exc


def _render_pdf_pages(path: Path) -> list[bytes]:
    if fitz is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "PDF image rendering is unavailable. Install the PyMuPDF dependency.",
        )
    if Image is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "PDF image processing is unavailable. Install Pillow.",
        )
    pages: list[bytes] = []
    try:
        with fitz.open(str(path)) as document:
            if len(document) > MAX_PDF_PAGES:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    f"PDFs may contain at most {MAX_PDF_PAGES} pages.",
                )
            for page in document:
                width = page.rect.width * 2
                height = page.rect.height * 2
                if width * height > MAX_IMAGE_PIXELS:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        "A PDF page exceeds the image processing pixel limit.",
                    )
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pages.append(pixmap.tobytes("png"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Could not render the uploaded PDF: {exc}"
        ) from exc
    return pages


def _read_pdf(path: Path, force_ocr: bool) -> tuple[str, bool, str, bool]:
    """Use Groq vision on rendered pages, falling back to embedded text/Tesseract."""
    vision_warning = ""
    page_images: list[bytes] = []
    vision_pages: list[str] = []
    if fitz is not None:
        page_images = _render_pdf_pages(path)
        for page_image in page_images:
            try:
                vision_pages.append(extract_text_from_image(page_image, "image/png"))
            except Exception as exc:
                logger.warning("Groq vision failed for a PDF page: %s", exc)
                vision_pages.append("")
                if not vision_warning:
                    vision_warning = (
                        f"Groq vision unavailable for one or more PDF pages "
                        f"({type(exc).__name__})."
                    )
    else:
        vision_warning = "PyMuPDF is unavailable; PDF pages could not be sent to Groq vision."

    if PdfReader is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "PDF text extraction is unavailable. Install pypdf.",
        )
    try:
        reader = PdfReader(str(path))
        if len(reader.pages) > MAX_PDF_PAGES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"PDFs may contain at most {MAX_PDF_PAGES} pages.",
            )
        embedded_pages = [page.extract_text() or "" for page in reader.pages]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Could not read the uploaded PDF: {exc}"
        ) from exc

    if page_images:
        vision_used = any(page.strip() for page in vision_pages)
        local_ocr_used = False
        if not force_ocr:
            vision_pages = [
                vision_text or embedded_text
                for vision_text, embedded_text in zip(vision_pages, embedded_pages)
            ]
        for index, page_text in enumerate(vision_pages):
            if not page_text.strip():
                if Image is None or pytesseract is None:
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "Scanned PDF OCR is unavailable. Install Pillow, pytesseract, and the Tesseract OCR executable.",
                    )
                try:
                    with Image.open(io.BytesIO(page_images[index])) as image:
                        vision_pages[index] = _ocr_image(image)
                    local_ocr_used = True
                except HTTPException:
                    raise
                except Exception as exc:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        f"Could not OCR PDF page {index + 1}: {exc}",
                    ) from exc
        return (
            "\n".join(page for page in vision_pages if page.strip()),
            vision_used,
            vision_warning,
            vision_used or local_ocr_used,
        )

    if not force_ocr:
        embedded_text = "\n".join(embedded_pages)
        if embedded_text.strip():
            return embedded_text, False, vision_warning, False

    if fitz is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Scanned PDF OCR is unavailable. Install the PyMuPDF dependency.",
        )
    if Image is None or pytesseract is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Scanned PDF OCR is unavailable. Install Pillow, pytesseract, and the Tesseract OCR executable.",
        )
    try:
        pages_text = []
        for page_bytes in _render_pdf_pages(path):
            with Image.open(io.BytesIO(page_bytes)) as image:
                pages_text.append(_ocr_image(image))
        return "\n".join(pages_text), False, vision_warning, True
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Could not OCR the scanned PDF: {exc}",
        ) from exc


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
def upload_document(
    file: UploadFile = File(...),
    force_ocr: bool = Query(False, description="Run OCR even when the PDF contains selectable text."),
):
    """Ingest supported reports and return extracted entities with a graph projection."""
    safe_name = Path(file.filename or "").name
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Unsupported file format. Upload TXT, CSV, PDF, JPG, JPEG, or PNG.",
        )

    try:
        saved, upload_id = _save_upload(file, safe_name)
        try:
            _validate_content(saved, ext, file.content_type)
        except HTTPException:
            saved.unlink(missing_ok=True)
            raise

        if ext in CSV_EXT:
            return {
                "status": "success",
                "document_id": upload_id,
                "filename": safe_name,
                "file_type": "csv",
                **_validate_csv(saved),
            }

        ocr_used = False
        vision_used = False
        vision_warning = ""
        if ext in TEXT_EXT:
            content = saved.read_text(encoding="utf-8-sig", errors="replace")
        elif ext in PDF_EXT:
            content, vision_used, vision_warning, ocr_used = _read_pdf(saved, force_ocr)
        else:
            if Image is None:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "Image OCR is unavailable. Install Pillow and pytesseract.",
                )
            try:
                with Image.open(saved) as image:
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise HTTPException(
                            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"Images may not exceed {MAX_IMAGE_PIXELS:,} pixels.",
                        )
                    image.verify()
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Could not read the uploaded image: {exc}",
                ) from exc

            try:
                content = extract_text_from_image(
                    saved.read_bytes(),
                    "image/png" if ext == ".png" else "image/jpeg",
                )
                vision_used = True
                ocr_used = True
            except Exception as exc:
                logger.warning("Groq vision image extraction failed: %s", exc)
                vision_warning = f"Groq vision unavailable for this image ({type(exc).__name__})."
                try:
                    with Image.open(saved) as image:
                        content = _ocr_image(image)
                        ocr_used = True
                except HTTPException:
                    raise
                except Exception as fallback_exc:
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        f"Groq vision and local OCR both failed ({type(fallback_exc).__name__}).",
                    ) from fallback_exc

        if not content.strip():
            return {
                "status": "empty",
                "document_id": upload_id,
                "filename": safe_name,
                "message": "No readable text was found in the uploaded document.",
                "ai_extracted_entities": {},
            }

        local_entities = parse_multi_crime_entities(content)
        ai_entities = extract_entities_from_fir(content)
        entities = {**local_entities, **ai_entities}
        for field in local_entities:
            if isinstance(local_entities[field], list):
                merged_values = []
                for value in local_entities[field] + ai_entities.get(field, []):
                    if value not in merged_values:
                        merged_values.append(value)
                entities[field] = merged_values
        entity_graph = build_entity_graph(entities, upload_id, safe_name)
        extraction_warning = entities.get("extraction_warning", "")
        return {
            "status": "partial" if extraction_warning else "success",
            "document_id": upload_id,
            "filename": safe_name,
            "file_type": ext.lstrip("."),
            "ocr_used": ocr_used,
            "vision_used": vision_used,
            "preview": content[:200].replace("\n", " "),
            "ai_extracted_entities": entities,
            "entity_graph": entity_graph,
            **({"vision_warning": vision_warning} if vision_warning else {}),
            **({"warning": extraction_warning} if extraction_warning else {}),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Upload processing failed")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Error while processing the uploaded file.",
        ) from exc
    finally:
        file.file.close()