"""gui/pages/page_guide.py — TAB 8: HƯỚNG DẪN SỬ DỤNG T-TTS v2.0
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

from backend.version import APP_VERSION, APP_NAME


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

        title = QLabel(f"📖 HƯỚNG DẪN SỬ DỤNG PHẦN MỀM {APP_NAME} v{APP_VERSION}")
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
            "3. THU ÂM TRỰC TIẾP QUA MICRO HOẶC CHỌN TỆP ĐỂ NHÂN BẢN GIỌNG",
            "• <b>Thu âm trực tiếp:</b> Chọn tab <i>Thu Âm Trực Tiếp Qua Micro</i>, bấm <b>Bắt đầu thu âm</b> và đọc to câu xác nhận mẫu (từ 5 đến 15 giây). Sau khi dừng, bạn có thể bấm <b>Nghe lại bản ghi</b> để kiểm tra chất lượng trước khi nhân bản.<br>"
            "• <b>Tải tệp có sẵn:</b> Chọn tab <i>Tải Lên Tệp Âm Thanh Có Sẵn</i>, nạp file WAV/MP3 từ điện thoại hoặc máy ghi âm.<br>"
            "• Đặt tên giọng và bấm <b>BẮT ĐẦU NHÂN BẢN GIỌNG NÓI</b>. Sau khi hoàn tất, giọng đọc cá nhân sẽ xuất hiện ngay lập tức trong toàn bộ hệ thống."
        )
        layout.addWidget(c3)

        # MỤC 4: XỬ LÝ HÀNG LOẠT VÀ CHUYỂN VÀO BẢN TIN
        c4 = self._create_section_card(
            "4. QUY TRÌNH XỬ LÝ HÀNG LOẠT & CHUYỂN VÀO BẢN TIN",
            "• Dán danh sách các câu/đoạn văn bản vào tab <b>Xử Lý Hàng Loạt</b> (hoặc nạp nhiều file .txt).<br>"
            "• Bấm <b>BẮT ĐẦU XỬ LÝ HÀNG LOẠT</b> để hệ thống tự động xuất các tệp âm thanh độc lập.<br>"
            "• Sau khi hoàn thành, bạn có 2 lựa chọn xuất sắc:<br>"
            "  - Bấm <b>💾 Tải tệp nén .ZIP</b> để lưu toàn bộ các tệp âm thanh về máy.<br>"
            "  - Bấm <b>📻 Chuyển vào Bản Tin</b> để đưa toàn bộ các đoạn vừa đọc sang tab <b>Bản Tin Phát Thanh</b> để ghép nhạc và xuất chương trình hoàn chỉnh."
        )
        layout.addWidget(c4)

        # MỤC 5: TẠO BẢN TIN PHÁT THANH HOÀN CHỈNH
        c5 = self._create_section_card(
            "5. TẠO BẢN TIN PHÁT THANH & GHÉP NHẠC HIỆU, NHẠC NỀN",
            "• Tại tab <b>Bản Tin Phát Thanh</b>, bạn có thể sắp xếp các phân đoạn theo thứ tự phát thanh chuẩn mực.<br>"
            "• Thêm nhạc hiệu mở đầu (Jingle Intro), nhạc hiệu chuyển mục, bài hát nhạc nền chạy ngầm (Background Music).<br>"
            "• Âm lượng nhạc nền được tự động tinh chỉnh dịu nhẹ để không lấn át giọng phát thanh viên.<br>"
            "• Tùy chỉnh thời gian nghỉ giữa các đoạn (0.5s - 2.0s) và bấm <b>XUẤT BẢN TIN PHÁT THANH HOÀN CHỈNH</b> để nhận một tệp WAV/MP3 duy nhất."
        )
        layout.addWidget(c5)

        # MỤC 6: KỊCH BẢN PODCAST & HỘI THOẠI ĐA NHÂN VẬT
        c6 = self._create_section_card(
            "6. KỊCH BẢN PODCAST & HỘI THOẠI ĐA NHÂN VẬT",
            "• Dành cho các chương trình phỏng vấn, kịch truyền thanh, đối thoại giữa nhiều nhân vật.<br>"
            "• Mỗi câu thoại được gán cho một nhân vật riêng với giọng đọc độc lập (Bắc, Trung, Nam hoặc giọng nhân bản).<br>"
            "• Có nút <b>▶ Nghe thử</b> từng câu thoại riêng biệt và nút <b>📑 Kịch bản mẫu</b> để thử nghiệm nhanh chóng.<br>"
            "• Bấm <b>GHÉP THÀNH AUDIO HỘI THOẠI / PODCAST</b> để tổng hợp toàn bộ kịch bản thành một tệp âm thanh đồng nhất."
        )
        layout.addWidget(c6)

        # MỤC 7: BẢN QUYỀN OFFLINE
        c7 = self._create_section_card(
            "7. BẢN QUYỀN OFFLINE & KÍCH HOẠT THỜI HẠN",
            "• Phần mềm cấp key hoàn toàn offline dựa trên mã phần cứng máy tính (Machine ID).<br>"
            "• Hỗ trợ 6 gói thời hạn linh hoạt: <b>1 Ngày, 7 Ngày, 30 Ngày, 6 Tháng, 1 Năm và Vĩnh Viễn</b>.<br>"
            "• Thời hạn của key bắt đầu tính từ lần đầu tiên kích hoạt thành công trên máy bạn.<br>"
            "• Tác giả phần mềm: <b>Nguyễn Văn Tiệp</b>."
        )
        layout.addWidget(c7)

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
