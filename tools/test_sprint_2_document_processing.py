"""tools/test_sprint_2_document_processing.py
=========================================
Automated test suite for Sprint 2 (Document Processing & Document Project):
1. Number to Vietnamese words converter (cardinal, compound, special cases).
2. Date and Time normalization (DD/MM/YYYY, HH:MM, h format).
3. Acronym expansion (Military, Government, Rank abbreviations).
4. Percentage & Currency normalization.
5. Smart chunking & sentence-boundary preservation.
6. Document text statistics calculation.
7. DocumentProject schema, creation, persistence, loading, listing, and cleanup.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.text_processor import (
    VietnameseTextProcessor,
    number_to_vietnamese_words,
)
from backend.project_manager import project_manager


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
        text = "Tỷ lệ sẵn sàng chiến đấu đạt 100%. Kinh phí hỗ trợ là 500.000 VNĐ."
        res = VietnameseTextProcessor.normalize_percentages_and_currencies(text)
        self.assertIn("một trăm phần trăm", res)
        self.assertIn("năm trăm nghìn đồng", res)

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

        # Ensure no chunk exceeds reasonable limits and all chunks end properly
        for c in chunks:
            self.assertTrue(len(c) <= 200, f"Đoạn quá dài ({len(c)} ký tự): {c}")
            self.assertFalse(c.endswith(" "), "Đoạn không được kết thúc bằng khoảng trắng thừa.")

        # Reconstructed content should preserve all words
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

        # 1. Tạo project schema
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

        # 2. Lưu project ra đĩa
        saved_id = project_manager.save_document_project(proj)
        self.assertEqual(saved_id, pid)

        # 3. Nạp lại project từ đĩa
        loaded = project_manager.load_document_project(pid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["name"], "Chỉ thị Phòng thủ 2026")
        self.assertEqual(loaded["data"]["voice_id"], "v-nam-qd-1")
        self.assertEqual(len(loaded["data"]["segments"]), proj["data"]["total_segments"])

        # 4. Liệt kê danh sách dự án
        all_docs = project_manager.list_document_projects()
        doc_ids = [d["id"] for d in all_docs]
        self.assertIn(pid, doc_ids)

        # 5. Xóa project và dọn dẹp
        deleted = project_manager.delete_project("documents", pid)
        self.assertTrue(deleted)
        self.assertIsNone(project_manager.load_document_project(pid))


if __name__ == "__main__":
    unittest.main()
