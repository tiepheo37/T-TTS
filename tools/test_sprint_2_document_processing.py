"""tools/test_sprint_2_document_processing.py
=========================================
Comprehensive automated test suite for Sprint 2 (Text Processing & Document Project):
1. Number to Vietnamese words converter (cardinal, compound, special cases).
2. Date and Time normalization (DD/MM/YYYY, HH:MM, h format).
3. Acronym expansion (Military, Government, Rank abbreviations).
4. Percentage & Currency normalization.
5. Smart chunking & sentence-boundary preservation.
6. Document text statistics calculation.
7. DocumentProject schema, creation, persistence, loading, listing, and cleanup.
8. Ambiguous number protection (AK-47, K-54, F-35, B-52, Su-30).
9. Military unit and document ID normalization (f324, e1, Số 123/QĐ-BQP).
10. Ordinals, decimals, and negative numbers.
11. Vietnamese phone number reading.
12. Find & Replace engine (search, replace, regex, case sensitive).
13. DocumentProject Save As, Rename, Duplicate, Recent projects.
14. Corrupted project recovery mechanism.
15. Compatibility with existing Audio / Broadcast / Schedule projects.
16. UI Dialogs integration (TextProcessorDialog, FindReplaceDialog, DocumentProjectDialog).
"""

from __future__ import annotations

import os
import sys
import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.text_processor import (
    VietnameseTextProcessor,
    TextProcessingConfig,
    number_to_vietnamese_words,
)
from backend.project_manager import project_manager, get_projects_dir


class TestSprint2DocumentProcessing(unittest.TestCase):
    def test_01_number_to_vietnamese_words(self):
        """Kiểm tra đọc số nguyên tiếng Việt chuẩn."""
        cases = [
            (0, "không"),
            (1, "một"),
            (5, "năm"),
            (10, "mười"),
            (14, "mười bốn"),
            (15, "mười lăm"),
            (21, "hai mươi mốt"),
            (24, "hai mươi tư"),
            (25, "hai mươi lăm"),
            (105, "một trăm lẻ năm"),
            (115, "một trăm mười lăm"),
            (1000, "một nghìn"),
            (1500, "một nghìn năm trăm"),
            (1000000, "một triệu"),
            (1250000, "một triệu hai trăm năm mươi nghìn"),
        ]
        for val, expected in cases:
            actual = number_to_vietnamese_words(val)
            self.assertEqual(actual, expected, f"Lỗi đọc số {val}: nhận '{actual}', kỳ vọng '{expected}'")

    def test_02_dates_and_times_normalization(self):
        """Kiểm tra chuẩn hóa ngày tháng và mốc thời gian."""
        # 1. Ngày tháng năm
        text_date = "Kỷ niệm ngày thành lập QĐNDVN vào 22/12/1944 tại Cao Bằng."
        normalized_date = VietnameseTextProcessor.normalize_dates(text_date)
        self.assertIn("ngày hai mươi hai tháng mười hai năm một nghìn chín trăm bốn mươi tư", normalized_date)

        # 2. Giờ phút
        text_time = "Cuộc họp giao ban bắt đầu lúc 08:30 sáng và kết thúc lúc 11:00."
        normalized_time = VietnameseTextProcessor.normalize_times(text_time)
        self.assertIn("tám giờ rưỡi", normalized_time)
        self.assertIn("mười một giờ đúng", normalized_time)

    def test_03_acronyms_expansion(self):
        """Kiểm tra mở rộng từ viết tắt quân sự và chính trị."""
        text = "Đ/c Chỉ huy trưởng BCHQS tỉnh báo cáo BTL QK về kế hoạch huấn luyện."
        expanded = VietnameseTextProcessor.expand_acronyms(text)
        self.assertIn("Đồng chí Chỉ huy trưởng", expanded)
        self.assertIn("Ban chỉ huy quân sự", expanded)
        self.assertIn("Bộ tư lệnh", expanded)
        self.assertIn("Quân khu", expanded)

    def test_04_percentages_and_currency(self):
        """Kiểm tra chuẩn hóa phần trăm và tiền tệ."""
        text = "Tỷ lệ sẵn sàng chiến đấu đạt 100%. Kinh phí hỗ trợ là 500.000 VNĐ và $100."
        res = VietnameseTextProcessor.normalize_percentages_and_currencies(text)
        self.assertIn("một trăm phần trăm", res)
        self.assertIn("năm trăm nghìn đồng", res)
        self.assertIn("một trăm đô la", res)

    def test_05_smart_split_paragraphs(self):
        """Kiểm tra phân đoạn văn bản thông minh theo câu, không cắt ngang từ."""
        long_text = (
            "Chào mừng quý vị và các đồng chí đã đến với chương trình phát thanh Quân đội Nhân dân. "
            "Trong bản tin hôm nay, chúng tôi xin gửi tới các đồng chí những thông tin mới nhất về công tác "
            "huấn luyện và sẵn sàng chiến đấu của toàn quân. "
            "Các đơn vị thuộc Quân khu 1, Quân khu 2 và Quân khu 3 đã hoàn thành xuất sắc các nội dung diễn tập "
            "bắn đạn thật năm nay, đảm bảo an toàn tuyệt đối về người và vũ khí trang bị."
        )

        chunks = VietnameseTextProcessor.smart_split_paragraphs(long_text, max_chunk_chars=180)
        self.assertGreater(len(chunks), 1)

        for c in chunks:
            self.assertTrue(len(c) <= 200, f"Đoạn quá dài ({len(c)} ký tự): {c}")
            self.assertFalse(c.endswith(" "), "Đoạn không được kết thúc bằng khoảng trắng thừa.")

        reconstructed = " ".join(chunks)
        self.assertIn("Quân khu 1", reconstructed)
        self.assertIn("an toàn tuyệt đối", reconstructed)

    def test_06_text_statistics(self):
        """Kiểm tra tính toán số từ, ký tự và thời lượng phát thanh ước tính."""
        sample = "Đây là một đoạn văn bản mẫu kiểm thử gồm đúng mười từ tiếng Việt."
        stats = VietnameseTextProcessor.calculate_statistics(sample, words_per_minute=120.0)
        self.assertEqual(stats["word_count"], 15)
        self.assertGreater(stats["char_count"], 50)
        self.assertGreater(stats["estimated_minutes"], 0.0)
        self.assertGreater(stats["estimated_seconds"], 5.0)

    def test_07_document_project_lifecycle(self):
        """Kiểm tra toàn bộ vòng đời của DocumentProject: tạo, lưu, nạp, liệt kê và xóa."""
        raw_doc = (
            "Chỉ thị của BTL về tăng cường cảnh giác phòng thủ.\n\n"
            "Yêu cầu Đ/c Chỉ huy trưởng đôn đốc kiểm tra 100% quân số ngày 02/09/2026."
        )

        proj = project_manager.create_document_project(
            name="Chỉ thị Phòng thủ 2026",
            raw_text=raw_doc,
            source_path="/path/to/chi_thi.docx",
            voice_id="v-nam-qd-1",
            speed=1.05,
            fmt="wav",
        )

        pid = proj["id"]
        self.assertTrue(pid.startswith("documents_"))
        self.assertEqual(proj["name"], "Chỉ thị Phòng thủ 2026")
        self.assertEqual(proj["type"], "documents")
        self.assertIn("normalized_text", proj["data"])
        self.assertGreater(proj["data"]["total_segments"], 0)

        saved_id = project_manager.save_document_project(proj)
        self.assertEqual(saved_id, pid)

        loaded = project_manager.load_document_project(pid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["name"], "Chỉ thị Phòng thủ 2026")
        self.assertEqual(loaded["data"]["voice_id"], "v-nam-qd-1")
        self.assertEqual(len(loaded["data"]["segments"]), proj["data"]["total_segments"])

        all_docs = project_manager.list_document_projects()
        doc_ids = [d["id"] for d in all_docs]
        self.assertIn(pid, doc_ids)

        deleted = project_manager.delete_document_project(pid, delete_audio=False)
        self.assertTrue(deleted)
        self.assertIsNone(project_manager.load_document_project(pid))

    def test_08_ambiguous_number_protection(self):
        """Kiểm tra bảo vệ mã hiệu vũ khí, khí tài không bị đọc nhầm thành số đếm."""
        text = "Trang bị súng trường AK-47, súng ngắn K-54 và tiêm kích Su-30 cùng F-35."
        norm = VietnameseTextProcessor.full_normalize(text)
        self.assertIn("AK-47", norm)
        self.assertIn("K-54", norm)
        self.assertIn("Su-30", norm)
        self.assertIn("F-35", norm)

    def test_09_military_units_and_documents(self):
        """Kiểm tra chuẩn hóa số hiệu đơn vị quân sự và số công văn."""
        text = "Theo Số 123/QĐ-BQP, điều động f324 và e1 phối hợp cùng d4 thực hiện nhiệm vụ."
        norm = VietnameseTextProcessor.full_normalize(text)
        self.assertIn("trên Quyết định Bộ Quốc phòng", norm)
        self.assertIn("Sư đoàn 324", norm)
        self.assertIn("Trung đoàn 1", norm)
        self.assertIn("Tiểu đoàn 4", norm)

    def test_10_ordinals_and_decimals_and_negatives(self):
        """Kiểm tra đọc số thứ tự, số âm và số thập phân kèm đơn vị."""
        text = "Hoàn thành giai đoạn thứ 1, đạt hạng 1 toàn quân. Nhiệt độ là -5 độ, tiêu thụ 3,5 kg nhiên liệu."
        norm = VietnameseTextProcessor.full_normalize(text)
        self.assertIn("thứ nhất", norm)
        self.assertIn("hạng nhất", norm)
        self.assertIn("âm năm", norm)
        self.assertIn("ba phẩy năm", norm)

    def test_11_phone_number_reading(self):
        """Kiểm tra đọc số điện thoại liên lạc chỉ huy."""
        text = "Đường dây nóng trực ban tác chiến: 0912.345.678"
        norm = VietnameseTextProcessor.full_normalize(text)
        self.assertIn("không chín một hai", norm)
        self.assertIn("ba bốn năm", norm)
        self.assertIn("sáu bảy tám", norm)

    def test_12_find_and_replace_engine(self):
        """Kiểm tra động cơ Tìm kiếm & Thay thế (Find & Replace)."""
        doc = "Chiến sĩ thi đua cấp cơ sở. Có một chiến sĩ hoàn thành xuất sắc nhiệm vụ."

        # Case insensitive
        matches = VietnameseTextProcessor.find_text(doc, "chiến sĩ", case_sensitive=False)
        self.assertEqual(len(matches), 2)

        # Case sensitive
        matches_cs = VietnameseTextProcessor.find_text(doc, "chiến sĩ", case_sensitive=True)
        self.assertEqual(len(matches_cs), 1)

        # Replace all
        new_doc, count = VietnameseTextProcessor.replace_text(doc, "Chiến sĩ", "Bộ đội")
        self.assertEqual(count, 2)
        self.assertIn("Bộ đội thi đua", new_doc)

    def test_13_document_project_advanced_lifecycle(self):
        """Kiểm tra Save As, Rename, Duplicate và Recent Projects."""
        proj = project_manager.create_document_project(
            name="Dự thảo 01",
            raw_text="Văn bản gốc ban đầu.",
        )
        pid = project_manager.save_document_project(proj)

        # Rename
        ok_rename = project_manager.rename_document_project(pid, "Dự thảo 01 - Đã duyệt")
        self.assertTrue(ok_rename)
        loaded = project_manager.load_document_project(pid)
        self.assertEqual(loaded["name"], "Dự thảo 01 - Đã duyệt")

        # Duplicate
        cloned = project_manager.duplicate_document_project(pid)
        self.assertIsNotNone(cloned)
        self.assertIn("(Bản sao)", cloned["name"])
        self.assertNotEqual(cloned["id"], pid)

        # Save As
        save_as_id = project_manager.save_as_document_project(loaded, "Dự thảo Phiên bản Mới")
        self.assertTrue(save_as_id.startswith("documents_"))
        self.assertNotEqual(save_as_id, pid)

        # Recent
        recent = project_manager.get_recent_document_projects(limit=5)
        self.assertGreaterEqual(len(recent), 2)

        # Cleanup
        project_manager.delete_document_project(pid)
        project_manager.delete_document_project(cloned["id"])
        project_manager.delete_document_project(save_as_id)

    def test_14_corrupted_project_recovery(self):
        """Kiểm tra phục hồi và cách ly tệp dự án hỏng mà không gây crash ứng dụng."""
        proj_dir = project_manager.create_project_schema("documents", "Dự án Hỏng")
        pid = project_manager.save_document_project(proj_dir)

        # Ghi đè file JSON bằng nội dung sai cú pháp
        p_file = get_projects_dir("documents") / f"{pid}.json"
        p_file.write_text("{ corrupt json data ::::", encoding="utf-8")

        # Nạp lại: phải trả về None và không raise Exception crash
        loaded = project_manager.load_document_project(pid)
        self.assertIsNone(loaded)

        # Cleanup test files
        for f in get_projects_dir("documents").glob(f"{pid}*"):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass

    def test_15_existing_projects_compatibility(self):
        """Kiểm tra dự án Audio, Broadcast và Schedule hoàn toàn độc lập và không bị ảnh hưởng."""
        audio_projs = project_manager.list_projects("audio")
        broadcast_projs = project_manager.list_projects("broadcast")
        sched_projs = project_manager.list_projects("schedules")

        self.assertIsInstance(audio_projs, list)
        self.assertIsInstance(broadcast_projs, list)
        self.assertIsInstance(sched_projs, list)

    def test_16_ui_dialogs_integration(self):
        """Kiểm tra giao diện TextProcessorDialog, FindReplaceDialog, DocumentProjectDialog và PageSynthesize."""
        from PySide6.QtWidgets import QApplication, QPushButton, QTextEdit
        app = QApplication.instance() or QApplication([])

        from gui.dialog_text_processor import TextProcessorDialog
        from gui.dialog_find_replace import FindReplaceDialog
        from gui.dialog_document_project import DocumentProjectDialog
        from gui.pages.page_synthesize import PageSynthesize

        editor = QTextEdit()
        editor.setPlainText("Văn bản kiểm tra giao diện.")

        dlg_tp = TextProcessorDialog("Văn bản mẫu ngày 22/12/1944.")
        self.assertIsNotNone(dlg_tp.txt_preview)
        self.assertIsNotNone(dlg_tp.btn_apply)
        dlg_tp.close()

        dlg_fr = FindReplaceDialog(editor)
        self.assertIsNotNone(dlg_fr.edit_find)
        self.assertIsNotNone(dlg_fr.btn_replace_all)
        dlg_fr.close()

        dlg_proj = DocumentProjectDialog()
        self.assertIsNotNone(dlg_proj.table)
        self.assertIsNotNone(dlg_proj.btn_open)
        dlg_proj.close()

        # PageSynthesize button checks
        page = PageSynthesize()
        buttons = page.findChildren(QPushButton)
        btn_texts = [b.text() for b in buttons]

        self.assertIn("⚙️ Chuẩn Hóa", btn_texts)
        self.assertIn("🔍 Tìm/Thay Thế", btn_texts)
        self.assertIn("📁 Dự Án", btn_texts)
        self.assertIn("📂 Nhập tài liệu", btn_texts)
        self.assertIn("📋 Dán từ Clipboard", btn_texts)


if __name__ == "__main__":
    unittest.main()
