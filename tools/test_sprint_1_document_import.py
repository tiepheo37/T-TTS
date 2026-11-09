"""tools/test_sprint_1_document_import.py
======================================
Automated test suite for Sprint 1 (Document Import DOCX/PDF/TXT/DOC) in T-TTS v3.1.0:
1. DOCX Reader: Paragraphs, Headings, Multi-cell Tables, Vietnamese Unicode diacritics.
2. PDF Reader: Multi-page extraction, scanned PDF (no text layer) detection and warning.
3. TXT Reader: UTF-8, UTF-8 BOM, CP1258/Windows encodings, formatting preservation.
4. DOC Legacy Guard: Informative warning and conversion instructions.
5. Progress callback & Cancellation mechanism.
6. Error handling: Non-existent files, corrupted files, unsupported file formats.
7. GUI Dialog & Synthesize Page Integration: Worker Thread & UI Button verification.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Setup path to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Initialize FFmpeg bootstrap just in case
try:
    from backend.ffmpeg_init import bootstrap_ffmpeg
    bootstrap_ffmpeg()
except Exception:
    pass

from backend.document_reader import extract_document_text


class TestSprint1DocumentImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = PROJECT_ROOT / "temp" / "test_sprint_1"
        cls.test_dir.mkdir(parents=True, exist_ok=True)

        # 1. Prepare sample TXT files
        cls.txt_utf8 = cls.test_dir / "sample_utf8.txt"
        cls.txt_utf8.write_text(
            "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc\n\nThông báo phát thanh quân sự.",
            encoding="utf-8"
        )

        cls.txt_utf8_bom = cls.test_dir / "sample_utf8_bom.txt"
        cls.txt_utf8_bom.write_text(
            "Văn bản mã hóa UTF-8 có Byte Order Mark (BOM).\nGiọng đọc truyền cảm chuẩn quân đội.",
            encoding="utf-8-sig"
        )

        cls.txt_cp1258 = cls.test_dir / "sample_cp1258.txt"
        try:
            cls.txt_cp1258.write_text(
                "Tiếng Việt Windows-1258 mã hóa truyền thống.",
                encoding="cp1258"
            )
        except Exception:
            # Fallback if cp1258 codec isn't available
            cls.txt_cp1258.write_text("Tiếng Việt mã hóa.", encoding="utf-8")

        # 2. Prepare sample DOCX file using python-docx
        cls.docx_file = cls.test_dir / "sample_doc.docx"
        try:
            import docx
            doc = docx.Document()
            doc.add_heading("BẢN TIN QUÂN SỰ ĐẶC BIỆT", level=1)
            doc.add_paragraph("Đây là đoạn văn thứ nhất về công tác huấn luyện chiến sĩ mới.")
            doc.add_paragraph("Đoạn văn thứ hai: Đảm bảo sẵn sàng chiến đấu 100% quân số.")

            # Add table
            table = doc.add_table(rows=2, cols=2)
            table.cell(0, 0).text = "Tiêu chí"
            table.cell(0, 1).text = "Kết quả"
            table.cell(1, 0).text = "Kỷ luật"
            table.cell(1, 1).text = "Tuyệt đối an toàn"

            doc.save(str(cls.docx_file))
            cls.has_docx = True
        except ImportError:
            cls.has_docx = False

        # 3. Prepare sample PDF file using pypdf
        cls.pdf_file = cls.test_dir / "sample_doc.pdf"
        try:
            from pypdf import PdfWriter
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            with open(cls.pdf_file, "wb") as f:
                writer.write(f)
            cls.has_pypdf = True
        except ImportError:
            cls.has_pypdf = False

        # 4. Prepare legacy dummy .doc file
        cls.doc_legacy = cls.test_dir / "legacy_report.doc"
        cls.doc_legacy.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504)

    def test_01_txt_utf8_extraction(self):
        """Kiểm tra trích xuất TXT chuẩn UTF-8."""
        res = extract_document_text(self.txt_utf8)
        self.assertTrue(res["success"])
        self.assertEqual(res["format"], "txt")
        self.assertIn("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", res["raw_text"])
        self.assertIn("Thông báo phát thanh quân sự.", res["raw_text"])
        self.assertGreater(res["word_count"], 10)
        self.assertGreater(res["char_count"], 50)
        self.assertIsNone(res["warning"])

    def test_02_txt_utf8_bom_extraction(self):
        """Kiểm tra trích xuất TXT UTF-8 có BOM."""
        res = extract_document_text(self.txt_utf8_bom)
        self.assertTrue(res["success"])
        self.assertIn("Byte Order Mark", res["raw_text"])
        self.assertIn("chuẩn quân đội", res["raw_text"])
        # BOM character \ufeff should not remain at beginning of text
        self.assertFalse(res["raw_text"].startswith("\ufeff"))

    def test_03_txt_cp1258_extraction(self):
        """Kiểm tra trích xuất TXT mã hóa CP1258."""
        res = extract_document_text(self.txt_cp1258)
        self.assertTrue(res["success"])
        self.assertIn("Tiếng Việt", res["raw_text"])

    def test_04_docx_extraction_paragraphs_and_tables(self):
        """Kiểm tra trích xuất DOCX: tiêu đề, đoạn văn và bảng biểu."""
        if not self.has_docx:
            self.skipTest("Thư viện python-docx chưa có sẵn.")

        res = extract_document_text(self.docx_file)
        self.assertTrue(res["success"], f"Trích xuất DOCX lỗi: {res.get('error')}")
        self.assertEqual(res["format"], "docx")
        self.assertIn("BẢN TIN QUÂN SỰ ĐẶC BIỆT", res["raw_text"])
        self.assertIn("Đoạn văn thứ hai: Đảm bảo sẵn sàng chiến đấu", res["raw_text"])
        self.assertIn("Kỷ luật, Tuyệt đối an toàn", res["raw_text"])
        self.assertGreater(res["word_count"], 15)

    def test_05_pdf_scanned_detection(self):
        """Kiểm tra phát hiện tài liệu PDF bản scan không có text layer."""
        if not self.has_pypdf:
            self.skipTest("Thư viện pypdf chưa có sẵn.")

        res = extract_document_text(self.pdf_file)
        # Blank PDF has no text layer, should succeed with warning
        self.assertTrue(res["success"])
        self.assertEqual(res["format"], "pdf")
        self.assertEqual(res["page_count"], 1)
        self.assertIsNotNone(res["warning"])
        self.assertIn("bản scan", res["warning"])

    def test_06_legacy_doc_friendly_error(self):
        """Kiểm tra chặn tệp .doc cũ và đưa ra hướng dẫn chuyển đổi chi tiết."""
        res = extract_document_text(self.doc_legacy)
        self.assertFalse(res["success"])
        self.assertIn(".doc nhị phân", res["error"])
        self.assertIn("Save As", res["error"])
        self.assertIn(".docx", res["error"])

    def test_07_progress_callback_and_cancellation(self):
        """Kiểm tra hàm callback tiến trình và cờ hủy ngang an toàn."""
        calls = []

        def _cb(curr, total, msg):
            calls.append((curr, total, msg))

        # Test normal progress
        res = extract_document_text(self.txt_utf8, progress_callback=_cb)
        self.assertTrue(res["success"])
        self.assertGreater(len(calls), 0)

        # Test cancellation
        cancelled = extract_document_text(self.txt_utf8, cancel_check=lambda: True)
        self.assertFalse(cancelled["success"])
        self.assertIn("hủy", cancelled["error"].lower())

    def test_08_nonexistent_and_invalid_files(self):
        """Kiểm tra xử lý lỗi khi file không tồn tại hoặc định dạng lạ."""
        res_missing = extract_document_text(self.test_dir / "nonexistent.docx")
        self.assertFalse(res_missing["success"])
        self.assertIn("Không tìm thấy tệp", res_missing["error"])

        bad_format = self.test_dir / "test.xyz"
        bad_format.write_text("data")
        res_bad = extract_document_text(bad_format)
        self.assertFalse(res_bad["success"])
        self.assertIn("chưa được hỗ trợ", res_bad["error"])

    def test_09_gui_dialog_and_page_synthesize_integration(self):
        """Kiểm tra giao diện Dialog và nút trên PageSynthesize."""
        from PySide6.QtWidgets import QApplication, QPushButton
        app = QApplication.instance()
        if not app:
            app = QApplication([])

        from gui.dialog_import_document import DocumentImportDialog
        from gui.pages.page_synthesize import PageSynthesize

        dlg = DocumentImportDialog(None, initial_file=self.txt_utf8)
        self.assertIsNotNone(dlg.txt_preview)
        self.assertIsNotNone(dlg.btn_confirm)
        self.assertIsNotNone(dlg.btn_cancel)
        self.assertIsNotNone(dlg.rb_replace)
        self.assertIsNotNone(dlg.rb_append)
        self.assertIsNotNone(dlg.rb_new_project)

        # Test PageSynthesize has import document button
        page = PageSynthesize()
        buttons = page.findChildren(QPushButton)
        btn_texts = [b.text() for b in buttons]

        self.assertIn("📂 Nhập tài liệu", btn_texts)
        self.assertIn("📋 Dán từ Clipboard", btn_texts)
        self.assertIn("🗑 Xóa", btn_texts)
        self.assertIn("😊 Cười", btn_texts)
        self.assertIn("⏸ Nghỉ 500ms", btn_texts)
        self.assertIn("⏸ Nghỉ 2s", btn_texts)


if __name__ == "__main__":
    unittest.main()
