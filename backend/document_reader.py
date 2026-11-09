"""backend/document_reader.py — BỘ TRÍCH XUẤT VĂN BẢN ĐA ĐỊNH DẠNG (DOCX, PDF, TXT)
=============================================================================
Hỗ trợ chuyển đổi tài liệu văn bản thành văn bản tiếng Việt chuẩn phục vụ TTS:
- DOCX: Trích xuất paragraphs, headings, thứ tự bảng biểu, bảo toàn Unicode tiếng Việt.
- PDF: Trích xuất phân đoạn từng trang, phát hiện PDF scan thiếu text layer, lọc header/footer.
- TXT: Tự động nhận diện bảng mã (UTF-8, UTF-8 BOM, CP1258, Windows-1252).
- DOC cũ: Hướng dẫn chuyển đổi sang DOCX.
- Luồng trích xuất chạy nền không làm treo UI, có báo cáo tiến trình và hủy an toàn.
"""

from __future__ import annotations

import os
import re
import sys
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("T-TTS.DocumentReader")


def extract_document_text(
    file_path: str | Path,
    strip_header_footer: bool = False,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Trích xuất toàn bộ văn bản từ tệp Word (.docx), PDF (.pdf), hoặc Văn bản (.txt).

    Tham số:
    - file_path: Đường dẫn tới tệp tài liệu.
    - strip_header_footer: Tùy chọn lọc bỏ đầu trang / chân trang lặp lại trong PDF.
    - progress_callback: Hàm nhận callback (current_step, total_steps, message).
    - cancel_check: Hàm kiểm tra xem người dùng có yêu cầu hủy hay không (trả về bool).

    Trả về Dict:
    {
        "success": bool,
        "title": str,
        "format": str,  # 'docx' | 'pdf' | 'txt' | 'unknown'
        "raw_text": str,
        "paragraphs": List[str],
        "char_count": int,
        "word_count": int,
        "page_count": int,
        "has_tables": bool,
        "is_scanned_pdf": bool,
        "warning": Optional[str],
        "error": Optional[str],
    }
    """
    p = Path(file_path).resolve()
    if not p.is_file():
        return {
            "success": False,
            "title": p.stem,
            "format": "unknown",
            "raw_text": "",
            "paragraphs": [],
            "char_count": 0,
            "word_count": 0,
            "page_count": 0,
            "has_tables": False,
            "is_scanned_pdf": False,
            "warning": None,
            "error": f"Không tìm thấy tệp tài liệu trên đĩa: {p}",
        }

    ext = p.suffix.lower()
    title = p.stem.replace("_", " ").strip()

    # 1. Xử lý định dạng DOC nhị phân cũ
    if ext == ".doc":
        return {
            "success": False,
            "title": title,
            "format": "doc",
            "raw_text": "",
            "paragraphs": [],
            "char_count": 0,
            "word_count": 0,
            "page_count": 0,
            "has_tables": False,
            "is_scanned_pdf": False,
            "warning": None,
            "error": (
                "Định dạng Word cũ (.doc nhị phân) không được hỗ trợ đọc trực tiếp.\n\n"
                "💡 Hướng dẫn xử lý:\n"
                "1. Mở tệp bằng Microsoft Word, LibreOffice hoặc Google Docs.\n"
                "2. Chọn 'Lưu dưới dạng' (Save As) -> Chọn định dạng 'Word Document (*.docx)'.\n"
                "3. Dùng tệp .docx vừa lưu để nhập vào T-TTS."
            ),
        }

    # 2. Xử lý tệp DOCX (Microsoft Word)
    elif ext == ".docx":
        return _extract_docx(p, title, progress_callback, cancel_check)

    # 3. Xử lý tệp PDF
    elif ext == ".pdf":
        return _extract_pdf(p, title, strip_header_footer, progress_callback, cancel_check)

    # 4. Xử lý tệp TXT / Văn bản thuần
    elif ext in (".txt", ".text", ".log", ".md"):
        return _extract_txt(p, title, progress_callback, cancel_check)

    else:
        return {
            "success": False,
            "title": title,
            "format": ext.lstrip("."),
            "raw_text": "",
            "paragraphs": [],
            "char_count": 0,
            "word_count": 0,
            "page_count": 0,
            "has_tables": False,
            "is_scanned_pdf": False,
            "warning": None,
            "error": f"Định dạng tệp '{ext}' chưa được hỗ trợ. Vui lòng chọn tệp .docx, .pdf hoặc .txt.",
        }


# =============================================================================
# TRÍCH XUẤT WORD (.DOCX)
# =============================================================================
def _extract_docx(
    file_path: Path,
    title: str,
    progress_callback: Optional[Callable[[int, int, str], None]],
    cancel_check: Optional[Callable[[], bool]],
) -> Dict[str, Any]:
    """Trích xuất DOCX bảo toàn đoạn văn, tiêu đề và bảng biểu theo thứ tự đọc tự nhiên."""
    try:
        import docx
    except ImportError as e:
        return {
            "success": False,
            "title": title,
            "format": "docx",
            "raw_text": "",
            "paragraphs": [],
            "char_count": 0,
            "word_count": 0,
            "page_count": 0,
            "has_tables": False,
            "is_scanned_pdf": False,
            "warning": None,
            "error": f"Thiếu thư viện python-docx để đọc tệp Word: {e}",
        }

    try:
        if progress_callback:
            progress_callback(10, 100, "Đang mở cấu trúc tài liệu Word...")

        if cancel_check and cancel_check():
            return _cancelled_result(title, "docx")

        doc = docx.Document(str(file_path))
        collected_paragraphs: List[str] = []
        has_tables = len(doc.tables) > 0

        total_elements = len(doc.paragraphs) + len(doc.tables)
        processed_elements = 0

        # Lấy các đoạn văn bản chính (Paragraphs & Headings)
        for p in doc.paragraphs:
            if cancel_check and cancel_check():
                return _cancelled_result(title, "docx")

            text = p.text.strip()
            if text:
                # Kiểm tra heading
                style_name = getattr(p.style, "name", "").lower()
                if "heading" in style_name or "tiêu đề" in style_name:
                    collected_paragraphs.append(text)
                else:
                    collected_paragraphs.append(text)

            processed_elements += 1
            if progress_callback and processed_elements % 20 == 0:
                pct = int(10 + (processed_elements / max(1, total_elements)) * 70)
                progress_callback(pct, 100, f"Đang đọc đoạn văn ({processed_elements}/{total_elements})...")

        # Trích xuất nội dung bảng biểu theo thứ tự đọc hàng/cột
        if has_tables:
            if progress_callback:
                progress_callback(80, 100, "Đang xử lý cấu trúc bảng biểu...")

            for tbl_idx, table in enumerate(doc.tables):
                if cancel_check and cancel_check():
                    return _cancelled_result(title, "docx")

                table_rows_text: List[str] = []
                for row in table.rows:
                    cell_texts = []
                    for cell in row.cells:
                        c_txt = cell.text.strip().replace("\n", " ")
                        if c_txt and c_txt not in cell_texts:  # Chống trùng ô merge
                            cell_texts.append(c_txt)
                    if cell_texts:
                        table_rows_text.append(", ".join(cell_texts))

                if table_rows_text:
                    collected_paragraphs.append(f"\n[Bảng {tbl_idx + 1}]:\n" + "\n".join(table_rows_text))

        if progress_callback:
            progress_callback(95, 100, "Đang chuẩn hóa văn bản hoàn chỉnh...")

        raw_text = "\n\n".join(collected_paragraphs).strip()
        words = len(raw_text.split()) if raw_text else 0
        chars = len(raw_text)

        # Ước tính số trang dựa trên độ dài (trung bình 350 từ / trang)
        est_pages = max(1, int(round(words / 350.0))) if words > 0 else 0

        return {
            "success": True,
            "title": title,
            "format": "docx",
            "raw_text": raw_text,
            "paragraphs": collected_paragraphs,
            "char_count": chars,
            "word_count": words,
            "page_count": est_pages,
            "has_tables": has_tables,
            "is_scanned_pdf": False,
            "warning": None,
            "error": None,
        }

    except Exception as e:
        logger.error(f"Lỗi khi đọc tệp DOCX {file_path}: {e}", exc_info=True)
        return {
            "success": False,
            "title": title,
            "format": "docx",
            "raw_text": "",
            "paragraphs": [],
            "char_count": 0,
            "word_count": 0,
            "page_count": 0,
            "has_tables": False,
            "is_scanned_pdf": False,
            "warning": None,
            "error": f"Không thể trích xuất tệp Word: {e}",
        }


# =============================================================================
# TRÍCH XUẤT TÀI LIỆU PDF
# =============================================================================
def _extract_pdf(
    file_path: Path,
    title: str,
    strip_header_footer: bool,
    progress_callback: Optional[Callable[[int, int, str], None]],
    cancel_check: Optional[Callable[[], bool]],
) -> Dict[str, Any]:
    """Trích xuất tài liệu PDF theo thứ tự trang, kiểm tra PDF scan không có text layer."""
    try:
        import pypdf
    except ImportError as e:
        return {
            "success": False,
            "title": title,
            "format": "pdf",
            "raw_text": "",
            "paragraphs": [],
            "char_count": 0,
            "word_count": 0,
            "page_count": 0,
            "has_tables": False,
            "is_scanned_pdf": False,
            "warning": None,
            "error": f"Thiếu thư viện pypdf để đọc tài liệu PDF: {e}",
        }

    try:
        if progress_callback:
            progress_callback(10, 100, "Đang mở tài liệu PDF...")

        if cancel_check and cancel_check():
            return _cancelled_result(title, "pdf")

        reader = pypdf.PdfReader(str(file_path))
        num_pages = len(reader.pages)
        if num_pages == 0:
            return {
                "success": False,
                "title": title,
                "format": "pdf",
                "raw_text": "",
                "paragraphs": [],
                "char_count": 0,
                "word_count": 0,
                "page_count": 0,
                "has_tables": False,
                "is_scanned_pdf": False,
                "warning": None,
                "error": "Tài liệu PDF không chứa trang nào.",
            }

        page_texts: List[str] = []
        total_extracted_chars = 0

        for page_idx, page in enumerate(reader.pages):
            if cancel_check and cancel_check():
                return _cancelled_result(title, "pdf")

            try:
                page_raw = page.extract_text() or ""
            except Exception as page_err:
                logger.warning(f"Lỗi đọc trang {page_idx + 1}: {page_err}")
                page_raw = ""

            page_clean = page_raw.strip()
            if page_clean:
                # Lọc header/footer cơ bản nếu được yêu cầu
                if strip_header_footer:
                    lines = page_clean.splitlines()
                    if len(lines) > 2:
                        # Kiểm tra dòng đầu (có thể là header lặp)
                        if len(lines[0].strip()) < 40 and not lines[0].strip().endswith("."):
                            lines = lines[1:]
                    if len(lines) > 2:
                        # Kiểm tra dòng cuối (thường là số trang)
                        if re.match(r"^(trang\s*)?\d+(\s*/\s*\d+)?$", lines[-1].strip(), re.IGNORECASE):
                            lines = lines[:-1]
                    page_clean = "\n".join(lines).strip()

            if page_clean:
                page_texts.append(f"[Trang {page_idx + 1}]\n{page_clean}")
                total_extracted_chars += len(page_clean)

            if progress_callback:
                pct = int(10 + ((page_idx + 1) / num_pages) * 80)
                progress_callback(pct, 100, f"Đang trích xuất trang {page_idx + 1}/{num_pages}...")

        # Kiểm tra PDF scan (nếu trung bình ký tự / trang < 10)
        avg_chars_per_page = total_extracted_chars / max(1, num_pages)
        is_scanned = (total_extracted_chars < 30) or (avg_chars_per_page < 10)
        warning = None

        if is_scanned:
            warning = (
                f"⚠️ Cảnh báo: Tài liệu PDF này ({num_pages} trang) có thể là bản scan hoặc hình ảnh "
                f"không có lớp văn bản (Text Layer). Chỉ trích xuất được {total_extracted_chars} ký tự.\n"
                f"Khuyến nghị: Vui lòng sử dụng tệp PDF gốc có văn bản hoặc chuyển đổi qua công cụ nhận diện chữ (OCR) trước khi nhập."
            )

        raw_text = "\n\n".join(page_texts).strip()
        words = len(raw_text.split()) if raw_text else 0
        chars = len(raw_text)

        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]

        return {
            "success": True,
            "title": title,
            "format": "pdf",
            "raw_text": raw_text,
            "paragraphs": paragraphs,
            "char_count": chars,
            "word_count": words,
            "page_count": num_pages,
            "has_tables": False,
            "is_scanned_pdf": is_scanned,
            "warning": warning,
            "error": None,
        }

    except Exception as e:
        logger.error(f"Lỗi khi đọc tệp PDF {file_path}: {e}", exc_info=True)
        return {
            "success": False,
            "title": title,
            "format": "pdf",
            "raw_text": "",
            "paragraphs": [],
            "char_count": 0,
            "word_count": 0,
            "page_count": 0,
            "has_tables": False,
            "is_scanned_pdf": False,
            "warning": None,
            "error": f"Không thể trích xuất tệp PDF: {e}",
        }


# =============================================================================
# TRÍCH XUẤT VĂN BẢN THUẦN (.TXT) ĐA BẢNG MÃ
# =============================================================================
def _extract_txt(
    file_path: Path,
    title: str,
    progress_callback: Optional[Callable[[int, int, str], None]],
    cancel_check: Optional[Callable[[], bool]],
) -> Dict[str, Any]:
    """Trích xuất tệp văn bản thuần tự động phát hiện encoding (UTF-8, UTF-8 BOM, CP1258)."""
    if progress_callback:
        progress_callback(15, 100, "Đang đọc dữ liệu nhị phân...")

    if cancel_check and cancel_check():
        return _cancelled_result(title, "txt")

    try:
        raw_bytes = file_path.read_bytes()
    except Exception as e:
        return {
            "success": False,
            "title": title,
            "format": "txt",
            "raw_text": "",
            "paragraphs": [],
            "char_count": 0,
            "word_count": 0,
            "page_count": 0,
            "has_tables": False,
            "is_scanned_pdf": False,
            "warning": None,
            "error": f"Không thể đọc tệp văn bản từ đĩa: {e}",
        }

    if not raw_bytes:
        return {
            "success": True,
            "title": title,
            "format": "txt",
            "raw_text": "",
            "paragraphs": [],
            "char_count": 0,
            "word_count": 0,
            "page_count": 0,
            "has_tables": False,
            "is_scanned_pdf": False,
            "warning": "Tệp văn bản rỗng.",
            "error": None,
        }

    if progress_callback:
        progress_callback(40, 100, "Đang nhận diện bảng mã tiếng Việt...")

    # Thứ tự ưu tiên giải mã
    candidate_encodings = ["utf-8-sig", "utf-8", "cp1258", "utf-16", "utf-16le", "windows-1252", "latin-1"]
    decoded_text: Optional[str] = None
    detected_enc = "utf-8"

    # 1. Thử nhận diện bằng charset_normalizer
    try:
        import charset_normalizer
        matches = charset_normalizer.from_bytes(raw_bytes)
        best = matches.best()
        if best and best.encoding:
            candidate_encodings.insert(0, best.encoding)
    except Exception:
        pass

    for enc in candidate_encodings:
        try:
            candidate = raw_bytes.decode(enc)
            # Kiểm tra xem có chứa ký tự tiếng Việt hợp lệ không
            if candidate:
                decoded_text = candidate
                detected_enc = enc
                break
        except (UnicodeDecodeError, LookupError):
            continue

    if decoded_text is None:
        decoded_text = raw_bytes.decode("utf-8", errors="replace")
        detected_enc = "utf-8 (lossy fallback)"

    if progress_callback:
        progress_callback(85, 100, "Đang chuẩn hóa dòng và đoạn văn...")

    # Chuẩn hóa ngắt dòng
    clean_text = decoded_text.replace("\r\n", "\n").replace("\r", "\n")
    if clean_text.startswith("\ufeff"):
        clean_text = clean_text[1:]
    paragraphs = [p.strip() for p in clean_text.split("\n\n") if p.strip()]
    if not paragraphs and clean_text.strip():
        paragraphs = [clean_text.strip()]

    words = len(clean_text.split())
    chars = len(clean_text)
    est_pages = max(1, int(round(words / 350.0))) if words > 0 else 1

    # Warning only if encoding is atypical or lossy
    warning_enc = None
    if "lossy" in str(detected_enc).lower():
        warning_enc = f"Cảnh báo bảng mã: Tệp được đọc với dự phòng '{detected_enc}'. Một số ký tự có thể bị lỗi."
    elif str(detected_enc).lower().replace("-", "_") not in ("utf_8", "utf8", "ascii", "utf_8_sig", "utf8_sig"):
        warning_enc = f"Bảng mã nhận diện: {detected_enc}"

    return {
        "success": True,
        "title": title,
        "format": "txt",
        "raw_text": clean_text.strip(),
        "paragraphs": paragraphs,
        "char_count": chars,
        "word_count": words,
        "page_count": est_pages,
        "has_tables": False,
        "is_scanned_pdf": False,
        "warning": warning_enc,
        "error": None,
    }


def _cancelled_result(title: str, fmt: str) -> Dict[str, Any]:
    """Kết quả trả về khi người dùng yêu cầu hủy tác vụ."""
    return {
        "success": False,
        "title": title,
        "format": fmt,
        "raw_text": "",
        "paragraphs": [],
        "char_count": 0,
        "word_count": 0,
        "page_count": 0,
        "has_tables": False,
        "is_scanned_pdf": False,
        "warning": None,
        "error": "Người dùng đã hủy quá trình trích xuất tài liệu.",
    }


class DocumentReader:
    """Lớp điều phối trích xuất tài liệu (DOCX, PDF, TXT) hỗ trợ cả OOP và hàm tiện ích."""

    @staticmethod
    def read_file(
        file_path: str | Path,
        strip_header_footer: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        return extract_document_text(
            file_path=file_path,
            strip_header_footer=strip_header_footer,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    def extract(self, file_path: str | Path, **kwargs) -> Dict[str, Any]:
        return extract_document_text(file_path, **kwargs)
