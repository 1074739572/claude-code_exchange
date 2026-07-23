"""Regression coverage for PDF text and image ingestion."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.rag.chunking import _vector_regions
from harness.rag.enrichment import pdf_ocr_mode
from harness.rag.eval import _hit_matches
from harness.rag.ingest import ingest_path, load_chunks_for_source

from tests.rag_fixtures import rag_env  # noqa: F401


def test_pdf_ingest_extracts_text_and_embedded_image(tmp_path: Path, rag_env, monkeypatch):
    fitz = pytest.importorskip("fitz")
    monkeypatch.delenv("HARNESS_RAG_VLM_MODEL", raising=False)

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    pdf_path = corpus / "quarterly.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Revenue trend and quarterly delivery milestones.")
    pixmap = fitz.Pixmap(fitz.csRGB, 2, 2, bytes([255, 0, 0] * 4), False)
    page.insert_image(fitz.Rect(72, 100, 144, 172), pixmap=pixmap)
    document.save(pdf_path)
    document.close()

    result = ingest_path(str(corpus))
    assert result["files"][0]["modalities"]["image"] == 1

    chunks = load_chunks_for_source("quarterly.pdf")
    assert any("Revenue trend" in chunk["text"] for chunk in chunks)
    image = next(chunk for chunk in chunks if chunk.get("modality") == "image")
    assert "未生成视觉描述" in image["text"]
    assert (rag_env / image["asset_uri"]).is_file()


def test_vector_region_detection_works_on_mixed_pdf_page(tmp_path: Path):
    fitz = pytest.importorskip("fitz")
    path = tmp_path / "mixed.pdf"
    document = fitz.open()
    page = document.new_page()
    page.draw_rect(fitz.Rect(80, 80, 400, 300), color=(0, 0, 0), width=2)
    pixmap = fitz.Pixmap(fitz.csRGB, 2, 2, bytes([0, 0, 255] * 4), False)
    page.insert_image(fitz.Rect(420, 80, 460, 120), pixmap=pixmap)
    document.save(path)
    document.close()

    document = fitz.open(path)
    assert _vector_regions(document[0])
    assert document[0].get_images(full=True), "fixture must include a raster image too"
    document.close()


def test_multimodal_eval_can_require_modality_and_page():
    case = {
        "expect_any": ["交付数量"],
        "expect_modality": "table",
        "expect_page": 3,
    }
    assert _hit_matches(
        {"text": "交付数量 12", "modality": "table", "page": 3},
        case,
    )
    assert not _hit_matches(
        {"text": "交付数量 12", "modality": "text", "page": 3},
        case,
    )


def test_scanned_pdf_uses_vlm_ocr_without_duplicate_full_page_image(
    tmp_path: Path, rag_env, monkeypatch
):
    fitz = pytest.importorskip("fitz")
    import harness.rag.enrichment as enrichment

    monkeypatch.setenv("HARNESS_RAG_PDF_OCR_MODE", "vlm")
    monkeypatch.setattr(
        enrichment,
        "transcribe_scanned_page",
        lambda path: (
            "扫描报告标题\n项目交付数量为 12 套，验收日期为 2026 年 8 月。"
            "本页同时说明全部设备必须通过最终现场测试并提交完整记录。"
        ),
    )

    corpus = tmp_path / "scans"
    corpus.mkdir()
    pdf_path = corpus / "scanned.pdf"
    document = fitz.open()
    page = document.new_page(width=300, height=400)
    samples = bytes([245, 245, 245] * 12)
    pixmap = fitz.Pixmap(fitz.csRGB, 3, 4, samples, False)
    page.insert_image(page.rect, pixmap=pixmap)
    document.save(pdf_path)
    document.close()

    ingest_path(str(corpus))
    chunks = load_chunks_for_source("scanned.pdf")
    assert any(chunk["style"] == "pdf-vlm-ocr" for chunk in chunks)
    assert any("交付数量为 12 套" in chunk["text"] for chunk in chunks)
    assert not any(chunk.get("modality") == "image" for chunk in chunks)
    assert list((rag_env / "assets").rglob("*-ocr-render.png"))


def test_legacy_ocr_boolean_maps_to_tesseract(monkeypatch):
    monkeypatch.delenv("HARNESS_RAG_PDF_OCR_MODE", raising=False)
    monkeypatch.setenv("HARNESS_RAG_PDF_OCR", "1")
    assert pdf_ocr_mode() == "tesseract"
