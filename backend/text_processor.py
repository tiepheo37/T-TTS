"""backend/text_processor.py — XỬ LÝ VÀ CHUẨN HÓA VĂN BẢN TIẾNG VIỆT CHO TTS
=============================================================================
Module chuyên biệt xử lý văn bản tiếng Việt cho T-TTS v3.1.0 (Sprint 2):
1. Chuẩn hóa Unicode tiếng Việt NFC, khoảng trắng, dấu câu, phát hiện ký tự lạ.
2. Bộ đọc số tiếng Việt đa ngữ cảnh (nguyên, thập phân, âm, phần trăm, tiền tệ,
   thứ tự, số điện thoại, số hiệu văn bản, số hiệu đơn vị quân sự).
3. Cơ chế bảo vệ mã hiệu và số không mơ hồ (K-54, AK-47, F-35, B-52, Su-30...).
4. Phân đoạn văn bản thông minh (Smart Chunking) tôn trọng ranh giới câu và đoạn.
5. Thống kê ký tự, từ, đoạn, thời lượng đọc và số segments dự kiến.
6. Tìm kiếm & Thay thế (Find & Replace) hỗ trợ Preview và Regex.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
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


def digits_to_individual_words(digit_str: str) -> str:
    """Đọc từng chữ số riêng lẻ (ví dụ số điện thoại hoặc mã hiệu)."""
    return " ".join(DIGITS[int(d)] for d in digit_str if d.isdigit())


# =============================================================================
# 2. TỪ VIẾT TẮT QUÂN SỰ, CHÍNH TRỊ & ĐƠN VỊ TÁC CHIẾN
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

# Các mã quân sự và vũ khí KHÔNG được chuyển đổi thành số thông thường
PROTECTED_MILITARY_CODES = [
    r"\bAK-\d+\b",
    r"\bK-\d+\b",
    r"\bB-\d+\b",
    r"\bF-\d+\b",
    r"\bT-\d+\b",
    r"\bMiG-\d+\b",
    r"\bSu-\d+\b",
    r"\bM-\d+\b",
    r"\bBM-\d+\b",
    r"\bPKMS?\b",
    r"\bRPG-\d+\b",
    r"\bS-\d+\b",
]


# =============================================================================
# 3. CẤU HÌNH XỬ LÝ VĂN BẢN (TEXT PROCESSING CONFIG)
# =============================================================================
@dataclass
class TextProcessingConfig:
    enable_nfc: bool = True
    normalize_whitespace: bool = True
    normalize_punctuation: bool = True
    expand_acronyms: bool = True
    normalize_dates: bool = True
    normalize_times: bool = True
    normalize_percentages: bool = True
    normalize_currencies: bool = True
    normalize_decimals: bool = True
    normalize_negative_numbers: bool = True
    normalize_ordinals: bool = True
    normalize_phone_numbers: bool = True
    normalize_document_numbers: bool = True
    normalize_military_units: bool = True
    strip_header_footer: bool = False
    max_chunk_chars: int = 350
    min_chunk_chars: int = 40

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> TextProcessingConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# =============================================================================
# 4. BỘ XỬ LÝ VĂN BẢN CHÍNH (VIETNAMESE TEXT PROCESSOR)
# =============================================================================
class VietnameseTextProcessor:
    """Bộ tiền xử lý văn bản tiếng Việt phục vụ TTS tối ưu và chuẩn xác."""

    @classmethod
    def clean_unicode(cls, text: str) -> str:
        """Đưa văn bản về dạng chuẩn NFC và chuẩn hóa các ký tự đặc biệt."""
        if not text:
            return ""
        # 1. NFC normalization
        normalized = unicodedata.normalize("NFC", text)
        # 2. Chuẩn hóa ngoặc kép, gạch ngang
        normalized = normalized.replace("“", '"').replace("”", '"').replace("«", '"').replace("»", '"')
        normalized = normalized.replace("‘", "'").replace("’", "'")
        normalized = normalized.replace("–", "-").replace("—", "-")
        # 3. Loại bỏ khoảng trắng thừa
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n\s*\n+", "\n\n", normalized)
        return normalized.strip()

    @classmethod
    def normalize_punctuation(cls, text: str) -> str:
        """Chuẩn hóa dấu câu: khoảng cách trước/sau dấu câu."""
        if not text:
            return ""
        # Bỏ khoảng trắng trước dấu câu
        res = re.sub(r"\s+([.,;:!?])", r"\1", text)
        # Đảm bảo có khoảng trắng sau dấu câu nếu tiếp tục là chữ
        res = re.sub(r"([.,;:!?])(?=[^\s\d.,;:!?])", r"\1 ", res)
        # Chuẩn hóa dấu chấm lửng
        res = re.sub(r"\.{3,}", "...", res)
        return res

    @classmethod
    def detect_unusual_characters(cls, text: str) -> List[str]:
        """Phát hiện các ký tự lạ hoặc lỗi font nằm ngoài bảng mã tiếng Việt phổ biến."""
        unusual = set()
        for ch in text:
            code = ord(ch)
            # Cho phép ASCII tiêu chuẩn, tiếng Việt Unicode, dấu câu thông dụng
            if code < 32 and ch not in ("\n", "\r", "\t"):
                unusual.add(f"U+{code:04X} (Control)")
            elif code > 0x2000 and code not in (0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026, 0x20AB):
                cat = unicodedata.category(ch)
                if cat.startswith("C") or cat.startswith("S"):
                    unusual.add(f"{ch} (U+{code:04X})")
        return sorted(list(unusual))

    @classmethod
    def expand_acronyms(cls, text: str) -> str:
        """Mở rộng các từ viết tắt quân sự, chính trị, danh xưng."""
        result = text
        for pattern, replacement in MILITARY_ACRONYMS.items():
            result = re.sub(pattern, replacement, result)
        return result

    @classmethod
    def normalize_military_units(cls, text: str) -> str:
        """Chuẩn hóa số hiệu đơn vị quân sự (f324, e1, d4, c1)."""
        # Sư đoàn: f324, F324 -> Sư đoàn 324
        def _rep_su(m: re.Match) -> str:
            num = m.group(1)
            return f"Sư đoàn {num}"

        text = re.sub(r"\b[fF](\d{2,3})\b", _rep_su, text)

        # Trung đoàn: e1, E102 -> Trung đoàn 1, Trung đoàn 102
        def _rep_trung(m: re.Match) -> str:
            num = m.group(1)
            return f"Trung đoàn {num}"

        text = re.sub(r"\b[eE](\d{1,3})\b", _rep_trung, text)

        # Tiểu đoàn: d1, d4 -> Tiểu đoàn 1, Tiểu đoàn 4
        def _rep_tieu(m: re.Match) -> str:
            num = m.group(1)
            return f"Tiểu đoàn {num}"

        text = re.sub(r"\b[dD](\d{1,2})\b", _rep_tieu, text)

        # Đại đội: c1, c12 -> Đại đội 1, Đại đội 12
        def _rep_daidoi(m: re.Match) -> str:
            num = m.group(1)
            return f"Đại đội {num}"

        text = re.sub(r"\b[cC](\d{1,2})\b", _rep_daidoi, text)

        return text

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

        text = re.sub(r"\b(\d{1,2}):(\d{2})\b", _replace_time_colon, text)

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

        text = re.sub(r"\b(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?:VNĐ|VND|đồng|đ)\b", _replace_currency, text, flags=re.IGNORECASE)

        # Tiền đô la: $100 hoặc 100 USD
        def _replace_dollar(match: re.Match) -> str:
            raw_num = match.group(1).replace(".", "").replace(",", "")
            try:
                num = int(raw_num)
                return f"{number_to_vietnamese_words(num)} đô la"
            except ValueError:
                return match.group(0)

        text = re.sub(r"\$\s*(\d{1,3}(?:[.,]\d{3})*|\d+)\b|\b(\d+)\s*USD\b", lambda m: _replace_dollar(m), text)
        return text

    @classmethod
    def normalize_decimals_and_negatives(cls, text: str) -> str:
        """Chuẩn hóa số âm (-5) và số thập phân (3,5 hoặc 3.5 kèm đơn vị)."""
        # Số âm có dấu trừ đi liền hoặc cách 1 khoảng trắng
        def _rep_neg(m: re.Match) -> str:
            val = int(m.group(1))
            return f"âm {number_to_vietnamese_words(val)}"

        text = re.sub(r"(?<=\s)-\s*(\d+)(?=\s|[.,;!?]|$)", _rep_neg, text)

        # Số thập phân đi kèm đơn vị: 3,5 kg, 1,2 mét, 4.5 lít
        def _rep_decimal(m: re.Match) -> str:
            int_p, dec_p = m.group(1), m.group(2)
            try:
                return f"{number_to_vietnamese_words(int(int_p))} phẩy {number_to_vietnamese_words(int(dec_p))}"
            except ValueError:
                return m.group(0)

        text = re.sub(r"\b(\d+)[.,](\d+)(?=\s*(?:kg|g|tấn|tạ|mét|m|km|cm|mm|lít|l|ha|độ|giờ|phút|giây))\b", _rep_decimal, text, flags=re.IGNORECASE)
        return text

    @classmethod
    def normalize_ordinals(cls, text: str) -> str:
        """Chuẩn hóa số thứ tự: thứ 1 -> thứ nhất, hạng 1 -> hạng nhất..."""
        ordinal_map = {
            "1": "nhất",
            "2": "hai",
            "3": "ba",
            "4": "tư",
            "5": "năm",
            "6": "sáu",
            "7": "bảy",
            "8": "tám",
            "9": "chín",
            "10": "mười",
        }

        def _rep_ord(m: re.Match) -> str:
            prefix = m.group(1)
            num = m.group(2)
            word = ordinal_map.get(num, number_to_vietnamese_words(int(num)))
            return f"{prefix} {word}"

        return re.sub(r"\b(thứ|hạng|lần thứ|giai đoạn)\s*(\d+)\b", _rep_ord, text, flags=re.IGNORECASE)

    @classmethod
    def normalize_phone_numbers(cls, text: str) -> str:
        """Chuẩn hóa số điện thoại Việt Nam (10 chữ số bắt đầu bằng 0)."""
        # Ví dụ: 0912.345.678 hoặc 0912 345 678 hoặc 0987654321
        def _rep_phone(m: re.Match) -> str:
            digits = re.sub(r"\D", "", m.group(0))
            if len(digits) == 10 and digits.startswith("0"):
                g1 = digits_to_individual_words(digits[:4])
                g2 = digits_to_individual_words(digits[4:7])
                g3 = digits_to_individual_words(digits[7:])
                return f"{g1}, {g2}, {g3}"
            return m.group(0)

        return re.sub(r"\b0\d{3}[.\s]?\d{3}[.\s]?\d{3}\b", _rep_phone, text)

    @classmethod
    def normalize_document_numbers(cls, text: str) -> str:
        """Chuẩn hóa số hiệu công văn, văn bản chỉ thị (Số 123/QĐ-BQP)."""
        def _rep_doc(m: re.Match) -> str:
            num = m.group(1)
            symbol = m.group(2)
            # Đọc số
            num_words = digits_to_individual_words(num) if len(num) > 3 else number_to_vietnamese_words(int(num))
            # Thay thế ký hiệu viết tắt phổ biến trong văn bản quân sự
            sym_clean = symbol.replace("QĐ-BQP", "Quyết định Bộ Quốc phòng")
            sym_clean = sym_clean.replace("CT-TM", "Chỉ thị Bộ Tổng tham mưu")
            sym_clean = sym_clean.replace("QĐ-BCH", "Quyết định Ban chỉ huy")
            sym_clean = sym_clean.replace("KH-BTL", "Kế hoạch Bộ tư lệnh")
            return f"Số {num_words} trên {sym_clean}"

        return re.sub(r"\bSố\s*(\d+)/([A-ZĐa-zđ-]+)\b", _rep_doc, text)

    @classmethod
    def full_normalize(
        cls,
        text: str,
        config: Optional[TextProcessingConfig] = None,
    ) -> str:
        """Tiến hành toàn bộ chu trình chuẩn hóa văn bản tiếng Việt theo cấu hình."""
        cfg = config or TextProcessingConfig()
        if not text:
            return ""

        # Tạm thời bảo vệ các mã vũ khí/quân sự không bị can thiệp
        protected_tokens: Dict[str, str] = {}
        processed = text
        for idx, pattern in enumerate(PROTECTED_MILITARY_CODES):
            matches = list(re.finditer(pattern, processed))
            for m in matches:
                matched_str = m.group(0)
                token = f"__PROTECTED_CODE_{idx}_{len(protected_tokens)}__"
                protected_tokens[token] = matched_str
                processed = processed.replace(matched_str, token, 1)

        # 1. Unicode NFC & Punctuation
        if cfg.enable_nfc:
            processed = cls.clean_unicode(processed)
        if cfg.normalize_punctuation:
            processed = cls.normalize_punctuation(processed)

        # 2. Mở rộng từ viết tắt
        if cfg.expand_acronyms:
            processed = cls.expand_acronyms(processed)

        # 3. Đơn vị quân sự
        if cfg.normalize_military_units:
            processed = cls.normalize_military_units(processed)

        # 4. Số hiệu văn bản
        if cfg.normalize_document_numbers:
            processed = cls.normalize_document_numbers(processed)

        # 5. Ngày tháng & Thời gian
        if cfg.normalize_dates:
            processed = cls.normalize_dates(processed)
        if cfg.normalize_times:
            processed = cls.normalize_times(processed)

        # 6. Phần trăm & Tiền tệ
        if cfg.normalize_percentages or cfg.normalize_currencies:
            processed = cls.normalize_percentages_and_currencies(processed)

        # 7. Số thứ tự
        if cfg.normalize_ordinals:
            processed = cls.normalize_ordinals(processed)

        # 8. Số thập phân & Số âm
        if cfg.normalize_decimals or cfg.normalize_negative_numbers:
            processed = cls.normalize_decimals_and_negatives(processed)

        # 9. Số điện thoại
        if cfg.normalize_phone_numbers:
            processed = cls.normalize_phone_numbers(processed)

        # Khôi phục các mã hiệu quân sự đã bảo vệ
        for token, original_code in protected_tokens.items():
            processed = processed.replace(token, original_code)

        return processed.strip()

    @classmethod
    def smart_split_paragraphs(
        cls,
        text: str,
        max_chunk_chars: int = 350,
        min_chunk_chars: int = 40,
    ) -> List[str]:
        """Phân đoạn văn bản thành các câu hoặc khối nhỏ tối ưu cho TTS."""
        text = cls.clean_unicode(text)
        if not text:
            return []

        raw_paras = [p.strip() for p in text.split("\n") if p.strip()]
        chunks: List[str] = []

        sentence_endings = re.compile(r"([.!?;\n]+)")

        for para in raw_paras:
            if len(para) <= max_chunk_chars:
                chunks.append(para)
                continue

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
    def calculate_statistics(
        cls,
        text: str,
        words_per_minute: float = 160.0,
        max_chunk_chars: int = 350,
    ) -> Dict[str, Any]:
        """Tính toán các chỉ số thống kê chi tiết của văn bản."""
        cleaned = cls.clean_unicode(text)
        words = len(cleaned.split()) if cleaned else 0
        chars = len(cleaned)
        paras = len([p for p in cleaned.split("\n\n") if p.strip()]) if cleaned else 0
        duration_minutes = (words / words_per_minute) if words > 0 else 0.0
        duration_seconds = duration_minutes * 60.0

        chunks = cls.smart_split_paragraphs(cleaned, max_chunk_chars=max_chunk_chars)

        return {
            "char_count": chars,
            "word_count": words,
            "paragraph_count": max(1, paras) if chars > 0 else 0,
            "estimated_minutes": round(duration_minutes, 1),
            "estimated_seconds": round(duration_seconds, 1),
            "estimated_segments": len(chunks),
        }

    # =========================================================================
    # 5. TÌM KIẾM & THAY THẾ (FIND & REPLACE)
    # =========================================================================
    @classmethod
    def find_text(
        cls,
        text: str,
        query: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> List[Tuple[int, int]]:
        """Tìm tất cả các vị trí xuất hiện (start, end) của query trong text."""
        if not text or not query:
            return []

        matches: List[Tuple[int, int]] = []
        flags = 0 if case_sensitive else re.IGNORECASE

        if use_regex:
            try:
                pattern = re.compile(query, flags)
                for m in pattern.finditer(text):
                    matches.append((m.start(), m.end()))
            except re.error:
                return []
        else:
            pattern = re.compile(re.escape(query), flags)
            for m in pattern.finditer(text):
                matches.append((m.start(), m.end()))

        return matches

    @classmethod
    def replace_text(
        cls,
        text: str,
        query: str,
        replacement: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
        max_replace: int = 0,
    ) -> Tuple[str, int]:
        """Thay thế query bằng replacement và trả về (text_mới, số_lần_thay_thế)."""
        if not text or not query:
            return text, 0

        flags = 0 if case_sensitive else re.IGNORECASE
        count = max_replace if max_replace > 0 else 0

        if use_regex:
            try:
                new_text, n = re.subn(query, replacement, text, count=count, flags=flags)
                return new_text, n
            except re.error:
                return text, 0
        else:
            pattern = re.compile(re.escape(query), flags)
            new_text, n = pattern.subn(replacement, text, count=count)
            return new_text, n


# Bí danh chuẩn hóa cho hệ thống
TextProcessor = VietnameseTextProcessor
