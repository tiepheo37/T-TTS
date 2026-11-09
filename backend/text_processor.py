"""backend/text_processor.py — XỬ LÝ VÀ CHUẨN HÓA VĂN BẢN TIẾNG VIỆT CHO TTS
=============================================================================
Module chuyên biệt xử lý văn bản tiếng Việt cho T-TTS v3.1.0:
1. Chuẩn hóa Unicode tiếng Việt (NFC).
2. Đọc số tiếng Việt (số đếm, số thập phân, phần trăm, tiền tệ).
3. Đọc ngày tháng năm, giờ phút.
4. Mở rộng từ viết tắt quân sự, chính trị và xã hội phổ biến.
5. Phân đoạn văn bản thông minh (Smart Chunking) tôn trọng ranh giới câu.
6. Thống kê từ, ký tự và ước tính thời lượng phát thanh.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# 1. BẢNG TỪ ĐỌC SỐ TIẾNG VIỆT
# =============================================================================
DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _read_two_digits(val: int) -> str:
    """Đọc số có 2 chữ số (10 - 99)."""
    tens = val // 10
    units = val % 10

    if tens == 1:
        res = "mười"
    else:
        res = f"{DIGITS[tens]} mươi"

    if units == 1:
        res += " mốt" if tens > 1 else " một"
    elif units == 4:
        res += " tư" if tens > 1 else " bốn"
    elif units == 5:
        res += " lăm"
    elif units > 0:
        res += f" {DIGITS[units]}"

    return res


def _read_three_digits(val: int, has_higher: bool = False) -> str:
    """Đọc cụm 3 chữ số (0 - 999)."""
    hundreds = val // 100
    remainder = val % 100

    parts = []
    if hundreds > 0 or has_higher:
        parts.append(f"{DIGITS[hundreds]} trăm")

    if remainder > 0:
        if remainder < 10:
            if hundreds > 0 or has_higher:
                parts.append("lẻ")
            parts.append(DIGITS[remainder])
        else:
            parts.append(_read_two_digits(remainder))
    elif hundreds == 0 and not has_higher:
        parts.append("không")

    return " ".join(parts)


def number_to_vietnamese_words(n: int) -> str:
    """Chuyển đổi số nguyên thành chuỗi chữ tiếng Việt hoàn chỉnh."""
    if n == 0:
        return "không"
    if n < 0:
        return f"âm {number_to_vietnamese_words(abs(n))}"

    scales = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ"]
    groups = []
    temp = n
    while temp > 0:
        groups.append(temp % 1000)
        temp //= 1000

    words = []
    for i in reversed(range(len(groups))):
        val = groups[i]
        if val > 0:
            has_higher = (i < len(groups) - 1) and any(groups[i + 1:])
            group_str = _read_three_digits(val, has_higher=has_higher)
            scale = scales[i]
            if scale:
                words.append(f"{group_str} {scale}")
            else:
                words.append(group_str)

    return " ".join(words).strip()


# =============================================================================
# 2. TỪ VIẾT TẮT QUÂN SỰ & CHÍNH TRỊ VIỆT NAM
# =============================================================================
MILITARY_ACRONYMS = {
    r"\bQĐNDVN\b": "Quân đội nhân dân Việt Nam",
    r"\bQĐND\b": "Quân đội nhân dân",
    r"\bCAND\b": "Công an nhân dân",
    r"\bBTL\b": "Bộ tư lệnh",
    r"\bBCH\b": "Ban chỉ huy",
    r"\bBCHQS\b": "Ban chỉ huy quân sự",
    r"\bQK\b": "Quân khu",
    r"\bQC\b": "Quân chủng",
    r"\bBC\b": "Binh chủng",
    r"\bĐ/c\b": "Đồng chí",
    r"\bđ/c\b": "đồng chí",
    r"\bĐc\b": "Đồng chí",
    r"\bđc\b": "đồng chí",
    r"\bUBND\b": "Ủy ban nhân dân",
    r"\bHĐND\b": "Hội đồng nhân dân",
    r"\bCHXHCNVN\b": "Cộng hòa xã hội chủ nghĩa Việt Nam",
    r"\bTW\b": "Trung ương",
    r"\bT\.Ư\b": "Trung ương",
    r"\bVN\b": "Việt Nam",
    r"\bTP\.\b": "Thành phố ",
    r"\bTp\.\b": "Thành phố ",
    r"\bTX\.\b": "Thị xã ",
    r"\bTT\.\b": "Thị trấn ",
    r"\bNXB\b": "Nhà xuất bản",
    r"\bPGS\.TS\b": "Phó giáo sư Tiến sĩ",
    r"\bGS\.TS\b": "Giáo sư Tiến sĩ",
    r"\bThS\b": "Thạc sĩ",
    r"\bTS\b": "Tiến sĩ",
}


# =============================================================================
# 3. CHUẨN HÓA VĂN BẢN (NORMALIZATION)
# =============================================================================
class VietnameseTextProcessor:
    """Bộ tiền xử lý văn bản tiếng Việt phục vụ TTS tối ưu."""

    @classmethod
    def clean_unicode(cls, text: str) -> str:
        """Đưa văn bản về dạng chuẩn NFC và chuẩn hóa các ký tự đặc biệt."""
        if not text:
            return ""
        # 1. NFC normalization
        normalized = unicodedata.normalize("NFC", text)
        # 2. Chuẩn hóa ngoặc kép, gạch ngang
        normalized = normalized.replace("“", '"').replace("”", '"').replace("«", '"').replace("»", '"')
        normalized = normalized.replace("–", "-").replace("—", "-")
        # 3. Loại bỏ khoảng trắng thừa
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n\s*\n+", "\n\n", normalized)
        return normalized.strip()

    @classmethod
    def expand_acronyms(cls, text: str) -> str:
        """Mở rộng các từ viết tắt quân sự, chính trị, danh xưng."""
        result = text
        for pattern, replacement in MILITARY_ACRONYMS.items():
            result = re.sub(pattern, replacement, result)
        return result

    @classmethod
    def normalize_dates(cls, text: str) -> str:
        """Chuẩn hóa ngày/tháng/năm sang chữ tiếng Việt."""
        # Khớp định dạng DD/MM/YYYY hoặc DD-MM-YYYY
        def _replace_full_date(match: re.Match) -> str:
            d, m, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if 1 <= d <= 31 and 1 <= m <= 12 and 1000 <= y <= 9999:
                return f"ngày {number_to_vietnamese_words(d)} tháng {number_to_vietnamese_words(m)} năm {number_to_vietnamese_words(y)}"
            return match.group(0)

        pattern_full = r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"
        text = re.sub(pattern_full, _replace_full_date, text)

        # Khớp định dạng MM/YYYY
        def _replace_month_year(match: re.Match) -> str:
            m, y = int(match.group(1)), int(match.group(2))
            if 1 <= m <= 12 and 1000 <= y <= 9999:
                return f"tháng {number_to_vietnamese_words(m)} năm {number_to_vietnamese_words(y)}"
            return match.group(0)

        pattern_my = r"\btháng\s*(\d{1,2})[/-](\d{4})\b"
        text = re.sub(pattern_my, _replace_month_year, text, flags=re.IGNORECASE)

        return text

    @classmethod
    def normalize_times(cls, text: str) -> str:
        """Chuẩn hóa giờ phút (ví dụ: 08:30 hoặc 8h30)."""
        def _replace_time_colon(match: re.Match) -> str:
            h, m = int(match.group(1)), int(match.group(2))
            if 0 <= h <= 23 and 0 <= m <= 59:
                h_words = number_to_vietnamese_words(h)
                if m == 0:
                    return f"{h_words} giờ đúng"
                elif m == 30:
                    return f"{h_words} giờ rưỡi"
                return f"{h_words} giờ {number_to_vietnamese_words(m)} phút"
            return match.group(0)

        # 08:30
        text = re.sub(r"\b(\d{1,2}):(\d{2})\b", _replace_time_colon, text)

        # 8h30 hoặc 8h
        def _replace_time_h(match: re.Match) -> str:
            h = int(match.group(1))
            m_str = match.group(2)
            if 0 <= h <= 23:
                h_words = number_to_vietnamese_words(h)
                if m_str:
                    m = int(m_str)
                    if 0 <= m <= 59:
                        if m == 30:
                            return f"{h_words} giờ rưỡi"
                        return f"{h_words} giờ {number_to_vietnamese_words(m)} phút"
                else:
                    return f"{h_words} giờ"
            return match.group(0)

        text = re.sub(r"\b(\d{1,2})h(\d{2})?\b", _replace_time_h, text, flags=re.IGNORECASE)
        return text

    @classmethod
    def normalize_percentages_and_currencies(cls, text: str) -> str:
        """Chuẩn hóa phần trăm (%) và đơn vị tiền tệ."""
        # Phần trăm: 50% hoặc 50,5%
        def _replace_percent(match: re.Match) -> str:
            num_part = match.group(1)
            # Check decimal
            if "," in num_part or "." in num_part:
                sep = "," if "," in num_part else "."
                int_p, dec_p = num_part.split(sep, 1)
                try:
                    num_words = f"{number_to_vietnamese_words(int(int_p))} phẩy {number_to_vietnamese_words(int(dec_p))}"
                except ValueError:
                    num_words = num_part
            else:
                try:
                    num_words = number_to_vietnamese_words(int(num_part))
                except ValueError:
                    num_words = num_part
            return f"{num_words} phần trăm"

        text = re.sub(r"\b(\d+(?:[.,]\d+)?)\s*%", _replace_percent, text)

        # Tiền tệ: 500.000 VNĐ / đ
        def _replace_currency(match: re.Match) -> str:
            raw_num = match.group(1).replace(".", "").replace(",", "")
            try:
                num = int(raw_num)
                return f"{number_to_vietnamese_words(num)} đồng"
            except ValueError:
                return match.group(0)

        text = re.sub(r"\b(\d{1,3}(?:[.,]\d{3})+)\s*(?:VNĐ|VND|đồng|đ)\b", _replace_currency, text, flags=re.IGNORECASE)
        return text

    @classmethod
    def normalize_standalone_numbers(cls, text: str) -> str:
        """Đọc các số nguyên đứng độc lập (chưa kèm đơn vị) sang chữ."""
        def _replace_digits(match: re.Match) -> str:
            raw = match.group(0)
            # Bỏ qua nếu có vẻ là mã hiệu như K-54 hoặc F-35
            try:
                num = int(raw.replace(".", "").replace(",", ""))
                return number_to_vietnamese_words(num)
            except ValueError:
                return raw

        # Chỉ thay thế các cụm số nguyên đứng tách biệt
        return re.sub(r"\b\d{1,3}(?:[.,]\d{3})*\b|\b\d+\b", _replace_digits, text)

    @classmethod
    def full_normalize(
        cls,
        text: str,
        expand_acronyms: bool = True,
        normalize_numbers: bool = True,
        normalize_dates_times: bool = True,
    ) -> str:
        """Tiến hành toàn bộ chu trình chuẩn hóa văn bản tiếng Việt."""
        res = cls.clean_unicode(text)
        if expand_acronyms:
            res = cls.expand_acronyms(res)
        if normalize_dates_times:
            res = cls.normalize_dates(res)
            res = cls.normalize_times(res)
        if normalize_numbers:
            res = cls.normalize_percentages_and_currencies(res)
            # res = cls.normalize_standalone_numbers(res)  # Optional if user desires total conversion
        return res

    @classmethod
    def smart_split_paragraphs(
        cls,
        text: str,
        max_chunk_chars: int = 350,
        min_chunk_chars: int = 40,
    ) -> List[str]:
        """Phân đoạn văn bản thành các câu hoặc khối nhỏ tối ưu cho TTS.

        Quy tắc:
        1. Phân chia theo đoạn tự nhiên (newline).
        2. Nếu một đoạn dài vượt quá `max_chunk_chars`, ngắt theo dấu ngắt câu (. ! ? ;).
        3. Nếu một câu vẫn quá dài, ngắt tại dấu phẩy (,) hoặc khoảng trắng gần nhất.
        4. Không bao giờ ngắt ngang giữa một từ tiếng Việt.
        """
        text = cls.clean_unicode(text)
        if not text:
            return []

        # Tách theo đoạn tự nhiên trước
        raw_paras = [p.strip() for p in text.split("\n") if p.strip()]
        chunks: List[str] = []

        sentence_endings = re.compile(r"([.!?;\n]+)")

        for para in raw_paras:
            if len(para) <= max_chunk_chars:
                chunks.append(para)
                continue

            # Phân tách thành các câu
            parts = sentence_endings.split(para)
            sentences = []
            for i in range(0, len(parts) - 1, 2):
                sent = (parts[i] + parts[i + 1]).strip()
                if sent:
                    sentences.append(sent)
            if len(parts) % 2 == 1 and parts[-1].strip():
                sentences.append(parts[-1].strip())

            current_chunk = ""
            for s in sentences:
                if not current_chunk:
                    current_chunk = s
                elif len(current_chunk) + len(s) + 1 <= max_chunk_chars:
                    current_chunk += " " + s
                else:
                    chunks.append(current_chunk.strip())
                    current_chunk = s

            if current_chunk:
                # Nếu câu đơn lẻ vẫn dài hơn max_chunk_chars, ngắt theo dấu phẩy
                if len(current_chunk) > max_chunk_chars:
                    comma_parts = current_chunk.split(",")
                    sub_chunk = ""
                    for cp in comma_parts:
                        piece = cp.strip()
                        if not piece:
                            continue
                        if not sub_chunk:
                            sub_chunk = piece
                        elif len(sub_chunk) + len(piece) + 2 <= max_chunk_chars:
                            sub_chunk += ", " + piece
                        else:
                            chunks.append(sub_chunk.strip())
                            sub_chunk = piece
                    if sub_chunk:
                        chunks.append(sub_chunk.strip())
                else:
                    chunks.append(current_chunk.strip())

        return [c for c in chunks if c.strip()]

    @classmethod
    def calculate_statistics(cls, text: str, words_per_minute: float = 160.0) -> Dict[str, Any]:
        """Tính toán các chỉ số thống kê của văn bản."""
        cleaned = cls.clean_unicode(text)
        words = len(cleaned.split()) if cleaned else 0
        chars = len(cleaned)
        duration_minutes = (words / words_per_minute) if words > 0 else 0.0
        duration_seconds = duration_minutes * 60.0

        return {
            "char_count": chars,
            "word_count": words,
            "estimated_minutes": round(duration_minutes, 1),
            "estimated_seconds": round(duration_seconds, 1),
        }
