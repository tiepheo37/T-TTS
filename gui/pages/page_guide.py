"""gui/pages/page_guide.py — TAB 8: HƯỚNG DẪN SỬ DỤNG T-TTS v1.0.1
===================================================================
Hướng dẫn sử dụng toàn diện, trực quan bằng giao diện native:
- Hướng dẫn nhập văn bản và chèn thẻ nghỉ đọc tự nhiên.
- Hướng dẫn thu âm file mẫu để nhân bản giọng đạt chất lượng cao nhất.
- Hướng dẫn xử lý hàng loạt tài liệu lớn.
- Hướng dẫn kích hoạt bản quyền offline và chuyển đổi máy.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
    QScrollArea,
)


class PageGuide(QWidget):
    """Trang Hướng Dẫn Sử Dụng."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        title = QLabel("📖 HƯỚNG DẪN SỬ DỤNG PHẦN MỀM T-TTS v1.0.1")
        title.setProperty("class", "CardTitle")
        title.setStyleSheet("color: #22D3EE; font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # MỤC 1: TẠO GIỌNG NÓI CƠ BẢN
        c1 = self._create_section_card(
            "1. TẠO GIỌNG NÓI TIẾNG VIỆT CHẤT LƯỢNG CAO",
            "• <b>Bước 1:</b> Tại tab <b>Tạo Giọng Nói</b>, dán hoặc nhập văn bản tiếng Việt có dấu đầy đủ vào ô soạn thảo.<br>"
            "• <b>Bước 2:</b> Chọn giọng đọc phù hợp từ danh sách 25 giọng chuẩn allowlist (chia theo Nam/Nữ, vùng miền Bắc/Nam, phong cách truyền cảm, thời sự, kể chuyện).<br>"
            "• <b>Bước 3:</b> Điều chỉnh tốc độ đọc nếu cần (mặc định 1.00x; văn bản thời sự khuyên dùng 1.05x - 1.15x; truyện đọc diễn cảm khuyên dùng 0.90x - 1.00x).<br>"
            "• <b>Bước 4:</b> Bấm <b>TẠO GIỌNG NÓI</b>. Sau khi hoàn tất, bạn có thể nghe thử trực tiếp hoặc bấm <b>Mở thư mục</b> để lấy file WAV/MP3."
        )
        layout.addWidget(c1)

        # MỤC 2: CHÈN THẺ NGẮT NGHỈ TỰ NHIÊN
        c2 = self._create_section_card(
            "2. CÁCH CHÈN THẺ NGẮT NGHỈ [PAUSE]",
            "Để câu nói có nhịp điệu ngắt nghỉ chân thực giống phát thanh viên, bạn có thể chèn trực tiếp thẻ:<br>"
            "• <code>[pause:0.3s]</code>: Ngắt nghỉ ngắn (tương đương dấu phẩy).<br>"
            "• <code>[pause:0.5s]</code>: Ngắt nghỉ câu (tương đương dấu chấm).<br>"
            "• <code>[pause:1.0s]</code>: Ngắt nghỉ chuyển đoạn văn bản.<br>"
            "<i>Ví dụ:</i> Chào mừng các bạn đã đến với kênh [pause:0.5s] Hôm nay chúng ta cùng theo dõi tin tức sau [pause:0.8s]..."
        )
        layout.addWidget(c2)

        # MỤC 3: NHÂN BẢN GIỌNG NÓI TỐI ƯU
        c3 = self._create_section_card(
            "3. BÍ QUYẾT NHÂN BẢN GIỌNG NÓI ĐẠT CHẤT LƯỢNG CAO",
            "• Chuẩn bị một đoạn âm thanh mẫu (WAV hoặc MP3) dài từ <b>5 đến 15 giây</b>.<br>"
            "• Giọng nói trong file mẫu cần rõ tiếng, tròn vành rõ chữ, không có tiếng ồn nền (tiếng quạt, tiếng còi xe) và tuyệt đối không có nhạc nền.<br>"
            "• Vào tab <b>Nhân Bản Giọng</b>, chọn file âm thanh mẫu và nhập tên định danh.<br>"
            "• VieNeu-TTS v3 Turbo sẽ tự động khử ồn và tạo vector đặc trưng. Sau khi nhân bản xong, giọng sẽ tự động xuất hiện ở tab Tạo Giọng Nói."
        )
        layout.addWidget(c3)

        # MỤC 4: XỬ LÝ HÀNG LOẠT SÁCH NÓI / BÁO CÁO
        c4 = self._create_section_card(
            "4. QUY TRÌNH XỬ LÝ HÀNG LOẠT (BATCH TTS)",
            "• Khi bạn có một danh sách các câu thông báo hoặc các chương sách cần đọc:<br>"
            "• Vào tab <b>Xử Lý Hàng Loạt</b>, dán toàn bộ danh sách (mỗi dòng một câu/đoạn).<br>"
            "• Bấm <b>BẮT ĐẦU XỬ LÝ HÀNG LOẠT</b>. Hệ thống xử lý độc lập từng dòng, có thanh tiến độ trực quan.<br>"
            "• Nếu một dòng xảy ra lỗi, hệ thống vẫn tiếp tục đọc các dòng còn lại bình thường."
        )
        layout.addWidget(c4)

        # MỤC 5: BẢN QUYỀN OFFLINE
        c5 = self._create_section_card(
            "5. BẢN QUYỀN OFFLINE & KÍCH HOẠT THỜI HẠN",
            "• Phần mềm cấp key hoàn toàn offline dựa trên mã phần cứng máy tính (Machine ID).<br>"
            "• Hỗ trợ 5 gói thời hạn: <b>1 Ngày, 7 Ngày, 30 Ngày, 6 Tháng và Vĩnh Viễn</b>.<br>"
            "• Thời hạn của key bắt đầu tính từ lần đầu tiên kích hoạt thành công trên máy bạn.<br>"
            "• Khi hết hạn, toàn bộ file âm thanh, lịch sử và giọng nhân bản của bạn vẫn được lưu nguyên vẹn."
        )
        layout.addWidget(c5)

        layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

    def _create_section_card(self, title_text: str, content_html: str) -> QFrame:
        card = QFrame()
        card.setProperty("class", "CardFrame")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(6)

        t = QLabel(title_text)
        t.setProperty("class", "CardTitle")
        cl.addWidget(t)

        c = QLabel(content_html)
        c.setWordWrap(True)
        c.setStyleSheet("color: #CBD5E1; font-size: 12px; line-height: 1.6;")
        cl.addWidget(c)
        return card
