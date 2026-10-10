import io
from types import SimpleNamespace

import pymupdf as fitz
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.api import upload_router
from app.services import ai_extractor
from app.services.crime_entity_parser import (
    build_entity_graph,
    link_entities_across_reports,
    parse_multi_crime_entities,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(upload_router, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        upload_router,
        "extract_entities_from_fir",
        lambda _: {"suspect_names": [], "modus_operandi_summary": ""},
    )
    app = FastAPI()
    app.include_router(upload_router.router, prefix="/api/upload")
    return TestClient(app)


def test_text_upload_returns_multi_crime_entities_and_graph(client):
    text = (
        "Crypto wallet 0x1234567890abcdef1234567890abcdef12345678\n"
        "from 0x1234567890abcdef1234567890abcdef12345678 to "
        "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd\n"
        "Recruitment agency: North Star Placement\n"
        "Transit route contact 9876543210 and 9876543210\n"
        "Failed login from 192.168.1.10 at example.com; credential exfiltration"
    )
    response = client.post(
        "/api/upload/",
        files={"file": ("report.txt", text, "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    entities = payload["ai_extracted_entities"]
    assert {
        "crypto_fraud",
        "human_trafficking",
        "corporate_data_breach",
    } <= set(entities["crime_categories"])
    assert entities["shared_contact_numbers"] == ["9876543210"]
    assert any(edge["relation"] == "TRANSFERRED_TO" for edge in payload["entity_graph"]["edges"])


def test_pdf_upload_uses_groq_vision(client, monkeypatch):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Phishing report for example.com")
    pdf = document.tobytes()
    document.close()
    monkeypatch.setattr(
        upload_router,
        "extract_text_from_image",
        lambda *_: "Phishing report for example.com",
    )

    response = client.post(
        "/api/upload/",
        files={"file": ("report.pdf", pdf, "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ocr_used"] is True
    assert payload["vision_used"] is True
    assert "example.com" in payload["preview"]
    assert "cyber_fraud_phishing" in payload["ai_extracted_entities"]["crime_categories"]


def test_image_upload_runs_ocr(client, monkeypatch):
    image_bytes = io.BytesIO()
    Image.new("RGB", (16, 16), color="white").save(image_bytes, format="PNG")
    monkeypatch.setattr(
        upload_router,
        "extract_text_from_image",
        lambda *_: "UPI fraud from 9876543210",
    )

    response = client.post(
        "/api/upload/",
        files={"file": ("scan.png", image_bytes.getvalue(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["ocr_used"] is True
    assert response.json()["vision_used"] is True
    assert response.json()["ai_extracted_entities"]["phone_numbers"] == ["9876543210"]


def test_png_uses_tesseract_when_groq_vision_fails(client, monkeypatch):
    image_bytes = io.BytesIO()
    Image.new("RGB", (16, 16), color="white").save(image_bytes, format="PNG")
    monkeypatch.setattr(
        upload_router,
        "extract_text_from_image",
        lambda *_: (_ for _ in ()).throw(RuntimeError("model unavailable")),
    )
    monkeypatch.setattr(
        upload_router, "_ocr_image", lambda _: "UPI fraud from 9876543210"
    )

    response = client.post(
        "/api/upload/",
        files={"file": ("scan.png", image_bytes.getvalue(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["vision_used"] is False
    assert response.json()["ocr_used"] is True
    assert "vision_warning" in response.json()


@pytest.mark.parametrize("extension", ["jpg", "jpeg"])
def test_jpeg_upload_runs_ocr(client, monkeypatch, extension):
    image_bytes = io.BytesIO()
    Image.new("RGB", (16, 16), color="white").save(image_bytes, format="JPEG")
    monkeypatch.setattr(
        upload_router, "extract_text_from_image", lambda *_: "Crypto report"
    )

    response = client.post(
        "/api/upload/",
        files={"file": (f"scan.{extension}", image_bytes.getvalue(), "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["ocr_used"] is True
    assert response.json()["vision_used"] is True


def test_scanned_pdf_uses_ocr_fallback(client, monkeypatch):
    document = fitz.open()
    document.new_page()
    pdf = document.tobytes()
    document.close()
    monkeypatch.setattr(
        upload_router,
        "extract_text_from_image",
        lambda *_: (_ for _ in ()).throw(RuntimeError("Groq vision unavailable")),
    )
    monkeypatch.setattr(upload_router, "_ocr_image", lambda _: "Phishing report")

    response = client.post(
        "/api/upload/",
        files={"file": ("scanned.pdf", pdf, "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["ocr_used"] is True
    assert response.json()["vision_used"] is False
    assert "vision_warning" in response.json()
    assert "cyber_fraud_phishing" in response.json()["ai_extracted_entities"]["crime_categories"]


def test_groq_vision_request_uses_base64_data_url(monkeypatch):
    request_data = {}

    class FakeGroq:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self.create_completion)
            )

        def create_completion(self, **kwargs):
            request_data.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="Visible text")
                    )
                ]
            )

    monkeypatch.setattr(ai_extractor, "Groq", FakeGroq)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_VISION_MODEL", "vision-test-model")

    text = ai_extractor.extract_text_from_image(b"sample-image-bytes", "image/png")

    assert text == "Visible text"
    assert request_data["model"] == "vision-test-model"
    image_part = request_data["messages"][0]["content"][1]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


def test_mismatched_content_type_is_rejected(client, tmp_path):
    response = client.post(
        "/api/upload/",
        files={"file": ("report.pdf", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 415
    assert list(tmp_path.iterdir()) == []


def test_csv_upload_is_validated_without_text_extraction(client):
    response = client.post(
        "/api/upload/",
        files={
            "file": (
                "bank.csv",
                "txn_id,from_account,to_account\nT1,123,456\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["csv_type"] == "bank_log"
    assert response.json()["rows"] == 1


def test_reports_link_shared_contacts_and_graph_categories():
    parsed = parse_multi_crime_entities("Phone 9876543210")
    links = link_entities_across_reports(
        [
            {"document_id": "first", "ai_extracted_entities": parsed},
            {"document_id": "second", "ai_extracted_entities": parsed},
        ]
    )

    assert len(links) == 1
    assert links[0]["relation"] == "SHARES_CONTACT"
    graph = build_entity_graph(parsed, "first", "report.txt")
    assert graph["nodes"][0]["crime_categories"] == ["cyber_fraud_phishing"]


def test_local_extractor_returns_extended_fields_without_groq(monkeypatch):
    monkeypatch.setattr(ai_extractor, "Groq", None)

    result = ai_extractor.extract_entities_from_fir(
        "Crypto wallet 0x1234567890abcdef1234567890abcdef12345678"
    )

    assert result["extraction_source"] == "local"
    assert result["crypto_wallets"] == ["0x1234567890abcdef1234567890abcdef12345678"]
    assert "crypto_fraud" in result["crime_categories"]
