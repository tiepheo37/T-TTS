"""tools/key_generator_gui.py — ỨNG DỤNG GIAO DIỆN CẤP KEY & QUẢN LÝ BẢN QUYỀN T-TTS v1.0.1
========================================================================================
Bộ công cụ chuyên nghiệp nội bộ dành riêng cho Nhà phát triển (Developer):
1. CẤP KEY CHO KHÁCH HÀNG:
   - Tự động trích xuất thông minh Mã Máy (Machine ID) từ tin nhắn của khách (Zalo/Facebook/SMS).
   - Quản lý thông tin từng khách hàng (Họ tên, Số điện thoại/Zalo, Ghi chú dự án).
   - Chọn chính xác 3 thời hạn: 1 Ngày (24h), 7 Ngày (168h), 30 Ngày (720h) tính từ lúc kích hoạt.
   - Ký số chuẩn mã hóa Ed25519 tuyệt đối an toàn, bảo vệ chống sửa đổi.
   - Tạo sẵn MẪU TIN NHẮN ĐẸP để gửi ngay cho khách qua Zalo/Facebook chỉ với 1 click.
   - Xuất tệp giấy phép (.lic) đính kèm tên khách hàng.

2. QUẢN LÝ LỊCH SỬ CẤP KEY:
   - Lưu trữ tự động toàn bộ danh sách khách hàng đã cấp vào tệp `tools/keys_history.json`.
   - Bảng tra cứu trực quan: Tìm kiếm theo Tên khách, Số điện thoại, Mã máy.
   - Sao chép lại Key hoặc Tin nhắn gửi khách bất kỳ lúc nào mà không cần tạo lại.
   - Thống kê nhanh số lượng key đã cấp theo từng gói (1D, 7D, 30D).

3. KIỂM TRA & GIẢI MÃ KEY (KEY INSPECTOR):
   - Soát tính hợp lệ của bất kỳ chuỗi key nào do khách gửi lại để kiểm tra.
   - Phát hiện ngay nếu key bị sửa đổi ký tự hoặc không phải do developer phát hành.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Cải thiện độ sắc nét giao diện trên màn hình độ phân giải cao (High-DPI) Windows
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

try:
    from tools.license_generator import (
        VALID_PLANS,
        create_license_key,
        ensure_keys_dir,
        generate_master_keypair,
        load_private_key,
        load_public_key,
        verify_license_key,
        PRIVATE_KEY_PATH,
        PUBLIC_KEY_PATH,
        _get_base_tools_dir,
    )
except ImportError:
    from license_generator import (
        VALID_PLANS,
        create_license_key,
        ensure_keys_dir,
        generate_master_keypair,
        load_private_key,
        load_public_key,
        verify_license_key,
        PRIVATE_KEY_PATH,
        PUBLIC_KEY_PATH,
        _get_base_tools_dir,
    )

# Đường dẫn thư mục thực tế trên đĩa (tránh thư mục tạm _MEI của PyInstaller)
TOOLS_DIR = _get_base_tools_dir()
ROOT_DIR = TOOLS_DIR.parent
HISTORY_FILE = TOOLS_DIR / "keys_history.json"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# ==============================================================================
# QUẢN LÝ LỊCH SỬ CẤP KEY CHO KHÁCH (CUSTOMER HISTORY STORAGE)
# ==============================================================================
def load_history() -> list[dict]:
    """Tải lịch sử cấp key từ file JSON."""
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save_history(records: list[dict]) -> None:
    """Lưu danh sách lịch sử cấp key vào file JSON."""
    try:
        HISTORY_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[CẢNH BÁO] Không thể lưu lịch sử cấp key: {e}")


def add_history_record(rec: dict) -> None:
    """Thêm một bản ghi mới lên đầu danh sách."""
    records = load_history()
    records.insert(0, rec)
    save_history(records)


def delete_history_record(record_id: str) -> None:
    """Xóa một bản ghi khỏi lịch sử."""
    records = [r for r in load_history() if r.get("id") != record_id]
    save_history(records)


CONFIG_FILE = TOOLS_DIR / "key_generator_config.json"


def load_config() -> dict:
    """Tải cấu hình công cụ cấp key (ví dụ: thư mục lưu file mặc định)."""
    default_export = TOOLS_DIR / "exported_licenses"
    if not CONFIG_FILE.exists():
        return {"export_dir": str(default_export)}
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(cfg, dict):
            if "export_dir" not in cfg:
                cfg["export_dir"] = str(default_export)
            return cfg
    except Exception:
        pass
    return {"export_dir": str(default_export)}


def save_config(cfg: dict) -> None:
    """Lưu cấu hình công cụ cấp key."""
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[CẢNH BÁO] Không thể lưu cấu hình: {e}")


def extract_machine_id(raw_text: str) -> str:
    """Trích xuất thông minh Mã Máy từ chuỗi tin nhắn bất kỳ của khách."""
    if not raw_text:
        return ""
    # Tìm mẫu chuẩn TTTS-XXXX-XXXX-XXXX-XXXX
    m = re.search(r"TTTS-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}", raw_text, re.IGNORECASE)
    if m:
        return m.group(0).upper()

    # Nếu khách chỉ gửi 16 ký tự hexa hoặc cách nhau bằng dấu cách/gạch nối
    clean = re.sub(r"[^0-9A-Fa-f]", "", raw_text).upper()
    if len(clean) == 16:
        return f"TTTS-{clean[0:4]}-{clean[4:8]}-{clean[8:12]}-{clean[12:16]}"

    # Mặc định trả về chuỗi viết hoa bỏ khoảng trắng đầu cuối
    return raw_text.strip().upper()


# ==============================================================================
# LỚP ỨNG DỤNG GIAO DIỆN ĐỒ HỌA CHÍNH (KEY GENERATOR APP)
# ==============================================================================
class KeyGeneratorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("T-TTS v1.0.1 — CÔNG CỤ CẤP BẢN QUYỀN & QUẢN LÝ KHÁCH HÀNG")
        self.geometry("920x820")
        self.minsize(850, 720)
        self.configure(bg="#F4F6F0")

        # Thiết lập icon nếu có
        icon_path = ROOT_DIR / "app_icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        self.config = load_config()
        self.export_dir_var = tk.StringVar(value=self.config.get("export_dir", str(TOOLS_DIR / "exported_licenses")))
        self.duration_var = tk.StringVar(value="7d")
        self.last_generated_key = ""
        self.last_license_info = {}
        self.last_customer_name = ""
        self.last_customer_contact = ""

        self._apply_styles()
        self._build_header()
        self._build_notebook()
        self._build_status_bar()

        # Nạp trạng thái ban đầu
        self._check_keys_status()
        self._refresh_history_table()

    def _apply_styles(self):
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        # Màu sắc chủ đạo (quân đội / cờ đỏ sao vàng sang trọng)
        self.c_army_dark = "#1F3D16"
        self.c_army_head = "#162E10"
        self.c_flag_red = "#DA251D"
        self.c_star_yellow = "#FFDD00"
        self.c_bg = "#F4F6F0"
        self.c_card = "#FFFFFF"
        self.c_border = "#D2D8CF"

        self.style.configure("TLabel", background=self.c_bg, font=("Segoe UI", 10))
        self.style.configure("TNotebook", background=self.c_bg, borderwidth=0)
        self.style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=(16, 8))
        self.style.map("TNotebook.Tab",
            background=[("selected", "#FFFFFF"), ("!selected", "#E2E8DF")],
            foreground=[("selected", self.c_army_dark), ("!selected", "#555555")]
        )

    def _build_header(self):
        # Header banner chính
        header_frame = tk.Frame(self, bg=self.c_army_head, height=75)
        header_frame.pack(fill="x", side="top")

        title_lbl = tk.Label(
            header_frame,
            text="🇻🇳 T-TTS v1.0.1 — HỆ THỐNG CẤP BẢN QUYỀN KHÁCH HÀNG",
            bg=self.c_army_head,
            fg="#FFFFFF",
            font=("Times New Roman", 16, "bold"),
        )
        title_lbl.pack(anchor="w", padx=24, pady=(8, 2))

        sub_lbl = tk.Label(
            header_frame,
            text="CÔNG CỤ NỘI BỘ DÀNH CHO DEVELOPER · MÃ HÓA CHỮ KÝ ED25519 · HOẠT ĐỘNG 100% OFFLINE",
            bg=self.c_army_head,
            fg=self.c_star_yellow,
            font=("Segoe UI", 9, "bold"),
        )
        sub_lbl.pack(anchor="w", padx=24, pady=(0, 8))

        # Đường viền cờ đỏ
        border_line = tk.Frame(self, bg=self.c_flag_red, height=3)
        border_line.pack(fill="x", side="top")

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=12)

        # Tab 1: Cấp key cho khách
        self.tab_generate = tk.Frame(self.notebook, bg=self.c_bg)
        self.notebook.add(self.tab_generate, text="⚡ Cấp Key Cho Khách")
        self._build_tab_generate()

        # Tab 2: Lịch sử quản lý khách đã cấp
        self.tab_history = tk.Frame(self.notebook, bg=self.c_bg)
        self.notebook.add(self.tab_history, text="📜 Lịch Sử Đã Cấp Cho Khách")
        self._build_tab_history()

        # Tab 3: Soát & Kiểm tra tính hợp lệ của key
        self.tab_inspector = tk.Frame(self.notebook, bg=self.c_bg)
        self.notebook.add(self.tab_inspector, text="🔍 Kiểm Tra & Soát Key")
        self._build_tab_inspector()

    # ==========================================================================
    # TAB 1: CẤP KEY CHO KHÁCH HÀNG
    # ==========================================================================
    def _build_tab_generate(self):
        container = tk.Frame(self.tab_generate, bg=self.c_bg)
        container.pack(fill="both", expand=True, padx=12, pady=8)

        # 1. KHUNG THÔNG TIN KHÁCH HÀNG & MÃ MÁY
        card_cust = tk.LabelFrame(
            container,
            text=" 1. Thông Tin Khách Hàng & Thiết Bị Cấp Phép ",
            bg=self.c_card,
            fg=self.c_army_dark,
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=10,
        )
        card_cust.pack(fill="x", pady=(0, 8))

        # Dòng: Tên khách hàng & SĐT/Zalo
        cust_row = tk.Frame(card_cust, bg=self.c_card)
        cust_row.pack(fill="x", pady=(0, 6))

        # Cột trái: Tên khách hàng
        col_left = tk.Frame(cust_row, bg=self.c_card)
        col_left.pack(side="left", fill="x", expand=True, padx=(0, 10))
        tk.Label(col_left, text="Họ tên Khách / Đơn vị nhận key:", bg=self.c_card, fg="#222222", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.cust_name_entry = tk.Entry(col_left, font=("Segoe UI", 10), bg="#FAFAFA", relief="solid", bd=1)
        self.cust_name_entry.pack(fill="x", pady=(2, 0), ipady=3)
        self.cust_name_entry.insert(0, "Khách hàng dùng thử")

        # Cột phải: Số điện thoại / Zalo
        col_right = tk.Frame(cust_row, bg=self.c_card)
        col_right.pack(side="left", fill="x", expand=True)
        tk.Label(col_right, text="Số điện thoại / Zalo (tùy chọn):", bg=self.c_card, fg="#555555", font=("Segoe UI", 9)).pack(anchor="w")
        self.cust_contact_entry = tk.Entry(col_right, font=("Segoe UI", 10), bg="#FAFAFA", relief="solid", bd=1)
        self.cust_contact_entry.pack(fill="x", pady=(2, 0), ipady=3)

        # Dòng: Mã máy (Machine ID)
        mid_row = tk.Frame(card_cust, bg=self.c_card)
        mid_row.pack(fill="x", pady=(4, 2))
        tk.Label(mid_row, text="Mã Máy Tính của khách (Machine ID):", bg=self.c_card, fg="#222222", font=("Segoe UI", 9, "bold")).pack(side="left")

        self.mid_status_lbl = tk.Label(mid_row, text="• Hãy dán mã máy do khách gửi", bg=self.c_card, fg="#888888", font=("Segoe UI", 8, "italic"))
        self.mid_status_lbl.pack(side="left", padx=8)

        mid_input_frame = tk.Frame(card_cust, bg=self.c_card)
        mid_input_frame.pack(fill="x", pady=(2, 6))

        self.mid_entry = tk.Entry(
            mid_input_frame,
            font=("Consolas", 12, "bold"),
            bg="#FAFAFA",
            fg=self.c_army_dark,
            relief="solid",
            bd=1,
        )
        self.mid_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.mid_entry.bind("<KeyRelease>", self._on_mid_change)

        btn_smart_paste = tk.Button(
            mid_input_frame,
            text="📋 Dán & Tự trích xuất",
            bg=self.c_army_dark,
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            cursor="hand2",
            command=self._smart_paste_machine_id,
        )
        btn_smart_paste.pack(side="left", padx=(8, 0))

        # Dòng: Thời hạn cấp phép (Radiobuttons)
        tk.Label(card_cust, text="Chọn thời hạn cấp phép (Tính từ thời điểm khách kích hoạt lần đầu):", bg=self.c_card, fg="#222222", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 2))

        dur_frame = tk.Frame(card_cust, bg=self.c_card)
        dur_frame.pack(fill="x", pady=(0, 6))

        tk.Radiobutton(dur_frame, text="⚡ 1 Ngày (24h)", variable=self.duration_var, value="1d", bg=self.c_card, fg="#333333", font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="left", padx=(0, 12))
        tk.Radiobutton(dur_frame, text="🌟 7 Ngày (168h)", variable=self.duration_var, value="7d", bg=self.c_card, fg=self.c_army_dark, font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="left", padx=(0, 12))
        tk.Radiobutton(dur_frame, text="💎 30 Ngày (720h)", variable=self.duration_var, value="30d", bg=self.c_card, fg="#333333", font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="left", padx=(0, 12))
        tk.Radiobutton(dur_frame, text="📅 6 Tháng (Lịch)", variable=self.duration_var, value="6m", bg=self.c_card, fg="#1E40AF", font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="left", padx=(0, 12))
        tk.Radiobutton(dur_frame, text="👑 Vĩnh Viễn", variable=self.duration_var, value="perm", bg=self.c_card, fg="#991B1B", font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="left")

        # Dòng: Thư mục lưu file key xuất ra
        export_row = tk.Frame(card_cust, bg=self.c_card)
        export_row.pack(fill="x", pady=(4, 6))

        tk.Label(export_row, text="Thư mục lưu file key xuất ra:", bg=self.c_card, fg="#222222", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        export_input_frame = tk.Frame(export_row, bg=self.c_card)
        export_input_frame.pack(fill="x", pady=(2, 0))

        self.export_dir_entry = tk.Entry(
            export_input_frame,
            textvariable=self.export_dir_var,
            font=("Segoe UI", 9),
            bg="#FAFAFA",
            relief="solid",
            bd=1,
        )
        self.export_dir_entry.pack(side="left", fill="x", expand=True, ipady=3)

        btn_browse_dir = tk.Button(
            export_input_frame,
            text="📁 Chọn Thư Mục Lưu...",
            bg="#374151",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=10,
            cursor="hand2",
            command=self._choose_export_dir,
        )
        btn_browse_dir.pack(side="left", padx=(8, 0))

        # Ghi chú nội bộ
        tk.Label(card_cust, text="Ghi chú nội bộ (Mục đích cấp):", bg=self.c_card, fg="#666666", font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))
        self.note_entry = tk.Entry(card_cust, font=("Segoe UI", 9), bg="#FAFAFA", relief="solid", bd=1)
        self.note_entry.pack(fill="x", pady=(1, 2), ipady=2)
        self.note_entry.insert(0, "Cấp key trải nghiệm tính năng giọng đọc T-TTS v1.0.1")

        # NÚT BẤM CHÍNH: TẠO KEY
        btn_generate = tk.Button(
            container,
            text="🚀 TẠO MÃ BẢN QUYỀN CHO KHÁCH (GENERATE KEY)",
            bg=self.c_flag_red,
            fg=self.c_star_yellow,
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            pady=7,
            cursor="hand2",
            activebackground="#b71c1c",
            activeforeground="#FFFFFF",
            command=self._generate_key,
        )
        btn_generate.pack(fill="x", pady=(2, 8))

        # 2. KHUNG KẾT QUẢ & CÁC NÚT GỬI KHÁCH
        card_out = tk.LabelFrame(
            container,
            text=" 2. Kết Quả Mã Bản Quyền & Mẫu Gửi Khách Hàng ",
            bg=self.c_card,
            fg=self.c_army_dark,
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=10,
        )
        card_out.pack(fill="both", expand=True)

        self.key_text = tk.Text(
            card_out,
            height=3,
            font=("Consolas", 10),
            bg="#FAFAFA",
            fg="#111111",
            relief="solid",
            bd=1,
            wrap="char",
        )
        self.key_text.pack(fill="x", pady=(2, 6))

        # Khóa không cho gõ chỉnh sửa trực tiếp vào ô chứa key để tránh sai lệch ký tự
        def _on_key_press(event):
            if (event.state & 4) and event.keysym.lower() in ("c", "a"):
                return
            return "break"
        self.key_text.bind("<Key>", _on_key_press)

        # Thông tin tóm tắt key vừa tạo
        self.info_lbl = tk.Label(
            card_out,
            text="Chưa có key nào được tạo. Hãy nhập thông tin khách và bấm nút 'Tạo Mã Bản Quyền'.",
            bg=self.c_card,
            fg="#666666",
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
        )
        self.info_lbl.pack(fill="x", pady=(0, 8))

        # Các nút thao tác gửi khách
        action_bar = tk.Frame(card_out, bg=self.c_card)
        action_bar.pack(fill="x", pady=(2, 0))

        self.btn_copy_message = tk.Button(
            action_bar,
            text="✉️ Sao Chép Tin Nhắn Zalo/SMS Gửi Khách",
            bg="#0D47A1",
            fg="#FFFFFF",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=14,
            pady=6,
            cursor="hand2",
            state="disabled",
            command=self._copy_customer_message,
        )
        self.btn_copy_message.pack(side="left", padx=(0, 8))

        self.btn_copy_key_only = tk.Button(
            action_bar,
            text="📋 Chỉ Sao Chép Key",
            bg=self.c_army_dark,
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            state="disabled",
            command=self._copy_key_only,
        )
        self.btn_copy_key_only.pack(side="left", padx=(0, 8))

        self.btn_save_lic = tk.Button(
            action_bar,
            text="💾 Lưu File Giấy Phép (.lic)",
            bg="#424242",
            fg="#FFFFFF",
            font=("Segoe UI", 9),
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
            state="disabled",
            command=self._save_lic_file,
        )
        self.btn_save_lic.pack(side="left")

    # ==========================================================================
    # TAB 2: QUẢN LÝ LỊCH SỬ CẤP KEY
    # ==========================================================================
    def _build_tab_history(self):
        container = tk.Frame(self.tab_history, bg=self.c_bg)
        container.pack(fill="both", expand=True, padx=12, pady=10)

        # Thanh tìm kiếm & bộ đếm
        top_bar = tk.Frame(container, bg=self.c_bg)
        top_bar.pack(fill="x", pady=(0, 8))

        tk.Label(top_bar, text="🔍 Tìm kiếm khách:", bg=self.c_bg, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        self.search_entry = tk.Entry(top_bar, font=("Segoe UI", 10), width=28)
        self.search_entry.pack(side="left", ipady=2)
        self.search_entry.bind("<KeyRelease>", lambda e: self._filter_history())

        btn_clear_search = tk.Button(top_bar, text="✕", bg="#E0E0E0", relief="flat", padx=6, command=self._clear_search)
        btn_clear_search.pack(side="left", padx=(4, 16))

        self.stats_lbl = tk.Label(top_bar, text="Tổng số: 0 key", bg=self.c_bg, fg=self.c_army_dark, font=("Segoe UI", 9, "bold"))
        self.stats_lbl.pack(side="right")

        # Bảng Treeview hiển thị danh sách
        table_frame = tk.Frame(container, bg="#FFFFFF", relief="solid", bd=1)
        table_frame.pack(fill="both", expand=True)

        columns = ("created_at", "cust_name", "cust_contact", "mid", "plan", "note")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("created_at", text="Ngày Cấp")
        self.tree.heading("cust_name", text="Tên Khách Hàng")
        self.tree.heading("cust_contact", text="SĐT / Zalo")
        self.tree.heading("mid", text="Mã Máy Tính (Machine ID)")
        self.tree.heading("plan", text="Thời Hạn")
        self.tree.heading("note", text="Ghi Chú")

        self.tree.column("created_at", width=130, anchor="center")
        self.tree.column("cust_name", width=160, anchor="w")
        self.tree.column("cust_contact", width=110, anchor="center")
        self.tree.column("mid", width=210, anchor="center")
        self.tree.column("plan", width=90, anchor="center")
        self.tree.column("note", width=160, anchor="w")

        # Scrollbar cho bảng
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_history_select)

        # Các nút thao tác trên bản ghi đã chọn
        hist_act_bar = tk.Frame(container, bg=self.c_bg)
        hist_act_bar.pack(fill="x", pady=(10, 0))

        self.btn_hist_copy_msg = tk.Button(
            hist_act_bar,
            text="✉️ Sao Chép Lại Tin Nhắn Gửi Khách",
            bg="#0D47A1",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            state="disabled",
            command=self._hist_copy_message,
        )
        self.btn_hist_copy_msg.pack(side="left", padx=(0, 8))

        self.btn_hist_copy_key = tk.Button(
            hist_act_bar,
            text="📋 Sao Chép Lại Key",
            bg=self.c_army_dark,
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            state="disabled",
            command=self._hist_copy_key,
        )
        self.btn_hist_copy_key.pack(side="left", padx=(0, 8))

        self.btn_hist_export_lic = tk.Button(
            hist_act_bar,
            text="💾 Xuất File .lic",
            bg="#424242",
            fg="#FFFFFF",
            font=("Segoe UI", 9),
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            state="disabled",
            command=self._hist_export_lic,
        )
        self.btn_hist_export_lic.pack(side="left", padx=(0, 8))

        self.btn_hist_delete = tk.Button(
            hist_act_bar,
            text="🗑️ Xóa Bản Ghi",
            bg="#C62828",
            fg="#FFFFFF",
            font=("Segoe UI", 9),
            relief="flat",
            padx=12,
            pady=5,
            cursor="hand2",
            state="disabled",
            command=self._hist_delete_record,
        )
        self.btn_hist_delete.pack(side="right")

    # ==========================================================================
    # TAB 3: SOÁT & KIỂM TRA TÍNH HỢP LỆ CỦA KEY (INSPECTOR)
    # ==========================================================================
    def _build_tab_inspector(self):
        container = tk.Frame(self.tab_inspector, bg=self.c_bg)
        container.pack(fill="both", expand=True, padx=12, pady=10)

        card_check = tk.LabelFrame(
            container,
            text=" Soát Tính Hợp Lệ Của Mã Bản Quyền Bất Kỳ ",
            bg=self.c_card,
            fg=self.c_army_dark,
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=12,
        )
        card_check.pack(fill="both", expand=True)

        tk.Label(card_check, text="Dán chuỗi key cần kiểm tra vào đây:", bg=self.c_card, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        self.inspect_entry = tk.Text(card_check, height=4, font=("Consolas", 10), bg="#FAFAFA", relief="solid", bd=1)
        self.inspect_entry.pack(fill="x", pady=(0, 8))

        btn_inspect = tk.Button(
            card_check,
            text="🔍 Kiểm Tra & Xác Thực Chữ Ký Số Ed25519",
            bg=self.c_army_dark,
            fg="#FFFFFF",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=14,
            pady=6,
            cursor="hand2",
            command=self._inspect_custom_key,
        )
        btn_inspect.pack(anchor="w", pady=(0, 10))

        self.inspect_result_lbl = tk.Label(
            card_check,
            text="Kết quả kiểm tra sẽ hiển thị ở đây.",
            bg=self.c_card,
            fg="#666666",
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
        )
        self.inspect_result_lbl.pack(fill="both", expand=True)

    # ==========================================================================
    # STATUS BAR
    # ==========================================================================
    def _build_status_bar(self):
        status_bar = tk.Frame(self, bg="#E2E8DF", height=28)
        status_bar.pack(fill="x", side="bottom")

        self.key_status_lbl = tk.Label(
            status_bar,
            text="Đang kiểm tra khóa Ed25519...",
            bg="#E2E8DF",
            fg="#333333",
            font=("Segoe UI", 8),
        )
        self.key_status_lbl.pack(side="left", padx=16, pady=4)

    # ==========================================================================
    # LOGIC VÀ XỬ LÝ SỰ KIỆN
    # ==========================================================================
    def _check_keys_status(self):
        try:
            load_private_key()
            self.key_status_lbl.configure(
                text="✅ Khóa Master Ed25519: Đã nạp thành công & Đồng bộ 100% với bản quyền T-TTS v1.0.1",
                fg="#2E7D32",
            )
        except Exception as e:
            self.key_status_lbl.configure(
                text=f"⚠️ Lỗi nạp khóa Ed25519: {e}",
                fg="#C62828",
            )

    def _on_mid_change(self, event=None):
        val = self.mid_entry.get().strip().upper()
        if re.match(r"^TTTS-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}$", val):
            self.mid_status_lbl.configure(text="🟢 Mã máy chuẩn hợp lệ (16 ký tự Hexa)", fg="#2E7D32")
        elif val:
            self.mid_status_lbl.configure(text="🟡 Lưu ý: Chưa chuẩn dạng TTTS-XXXX-XXXX-XXXX-XXXX", fg="#E65100")
        else:
            self.mid_status_lbl.configure(text="• Hãy dán mã máy do khách gửi", fg="#888888")

    def _smart_paste_machine_id(self):
        try:
            raw = self.clipboard_get()
            extracted = extract_machine_id(raw)
            if extracted:
                self.mid_entry.delete(0, tk.END)
                self.mid_entry.insert(0, extracted)
                self._on_mid_change()
            else:
                messagebox.showwarning("Không Tìm Thấy Mã Máy", "Bộ nhớ tạm (Clipboard) không chứa nội dung văn bản.")
        except Exception as e:
            messagebox.showwarning("Lỗi Bộ Nhớ Tạm", f"Không thể đọc clipboard: {e}")

    def _format_customer_message(self, name: str, contact: str, mid: str, plan_name: str, key: str) -> str:
        """Tạo mẫu tin nhắn hoàn chỉnh, lịch sự gửi khách qua Zalo/Facebook."""
        contact_str = f" ({contact})" if contact else ""
        return (
            f"Chào bạn {name},\n"
            f"Bộ phận hỗ trợ T-TTS gửi bạn thông tin kích hoạt bản quyền trải nghiệm phần mềm:\n"
            f"==================================================\n"
            f"👤 Người nhận: {name}{contact_str}\n"
            f"💻 Mã máy tính: {mid}\n"
            f"⏱️ Gói trải nghiệm: {plan_name} (Bắt đầu tính từ thời điểm kích hoạt)\n"
            f"==================================================\n"
            f"🔑 MÃ KÍCH HOẠT (KEY):\n"
            f"{key}\n"
            f"==================================================\n"
            f"📖 HƯỚNG DẪN KÍCH HOẠT:\n"
            f"1. Khởi động phần mềm T-TTS trên máy tính của bạn.\n"
            f"2. Bấm vào mục 'Bản quyền & Giấy phép' (hoặc bảng thông báo hiện lên).\n"
            f"3. Dán toàn bộ mã kích hoạt ở trên vào ô và bấm 'Kích hoạt ngay'.\n"
            f"4. Ứng dụng sẽ tự động mở khóa 100% đầy đủ chức năng offline.\n\n"
            f"Chúc bạn có trải nghiệm tuyệt vời cùng phần mềm T-TTS!"
        )

    def _generate_key(self):
        mid = self.mid_entry.get().strip().upper()
        if not mid:
            messagebox.showwarning("Thiếu Mã Máy", "Vui lòng nhập hoặc dán Mã Máy (Machine ID) do khách hàng gửi!")
            self.mid_entry.focus()
            return

        cust_name = self.cust_name_entry.get().strip() or "Khách hàng dùng thử"
        cust_contact = self.cust_contact_entry.get().strip()
        dur = self.duration_var.get()
        note = self.note_entry.get().strip()

        try:
            full_note = f"{cust_name} - {note}" if note else cust_name
            res = create_license_key(mid, dur, note=full_note)
            self.last_generated_key = res["key_string"]
            self.last_license_info = res
            self.last_customer_name = cust_name
            self.last_customer_contact = cust_contact

            # Hiển thị vào ô Text (chế độ chỉ đọc)
            self.key_text.delete("1.0", tk.END)
            self.key_text.insert(tk.END, self.last_generated_key)
            self.key_text.tag_add(tk.SEL, "1.0", tk.END)

            # Cập nhật thông tin chi tiết
            plan_name = res["duration_name"]
            info_str = (
                f"✅ ĐÃ CẤP THÀNH CÔNG CHO: {cust_name}\n"
                f"• Gói: {res['plan']} ({plan_name}) — Thời hạn bắt đầu tính từ lúc khách kích hoạt\n"
                f"• Mã máy cấp: {res['machine_id']}\n"
                f"• License ID: {res['license_id']}\n"
                f"• Ngày cấp: {res['issued_at_readable']}"
            )
            self.info_lbl.configure(text=info_str, fg="#2E7D32")

            # Bật các nút hành động
            self.btn_copy_message.configure(state="normal")
            self.btn_copy_key_only.configure(state="normal")
            self.btn_save_lic.configure(state="normal")

            # Tự động lưu vào lịch sử quản lý khách hàng
            rec = {
                "id": res["license_id"],
                "created_at": res["issued_at_readable"],
                "cust_name": cust_name,
                "cust_contact": cust_contact,
                "mid": mid,
                "plan": res["plan"],
                "duration_name": plan_name,
                "duration_hours": res["duration_hours"],
                "note": note,
                "key_string": self.last_generated_key,
            }
            add_history_record(rec)
            self._refresh_history_table()

            # Tự động sao chép tin nhắn đầy đủ vào clipboard Windows
            formatted_msg = self._format_customer_message(cust_name, cust_contact, mid, plan_name, self.last_generated_key)
            self.clipboard_clear()
            self.clipboard_append(formatted_msg)
            self.update_idletasks()

            messagebox.showinfo(
                "Cấp Key Thành Công!",
                f"🎉 Đã cấp key thành công cho khách hàng: {cust_name}!\n\n"
                f"Mẫu tin nhắn hoàn chỉnh (kèm mã key và hướng dẫn kích hoạt) đã được TỰ ĐỘNG SAO CHÉP.\n\n"
                f"Bạn có thể mở Zalo/Facebook và bấm Ctrl+V để gửi ngay cho khách hàng.",
            )
        except Exception as e:
            messagebox.showerror("Lỗi Cấp Key", f"Không thể tạo key: {e}")

    def _copy_customer_message(self):
        if not self.last_generated_key or not self.last_license_info:
            return
        plan_name = self.last_license_info.get("duration_name", "Dùng thử")
        mid = self.last_license_info.get("machine_id", "")
        msg = self._format_customer_message(self.last_customer_name, self.last_customer_contact, mid, plan_name, self.last_generated_key)
        self.clipboard_clear()
        self.clipboard_append(msg)
        self.update_idletasks()
        messagebox.showinfo("Đã Sao Chép Tin Nhắn", "✅ Đã sao chép tin nhắn đầy đủ gửi khách vào bộ nhớ đệm (Clipboard)!")

    def _copy_key_only(self):
        if not self.last_generated_key:
            return
        self.clipboard_clear()
        self.clipboard_append(self.last_generated_key)
        self.update_idletasks()
        self.key_text.tag_add(tk.SEL, "1.0", tk.END)
        messagebox.showinfo("Đã Sao Chép Key", "✅ Đã sao chép riêng chuỗi mã key vào bộ nhớ đệm!")

    def _choose_export_dir(self):
        cur = self.export_dir_var.get()
        new_dir = filedialog.askdirectory(
            initialdir=cur if os.path.isdir(cur) else str(TOOLS_DIR),
            title="Chọn thư mục lưu file key",
        )
        if new_dir:
            self.export_dir_var.set(new_dir)
            self.config["export_dir"] = new_dir
            save_config(self.config)

    def _save_lic_file(self):
        if not self.last_generated_key or not self.last_license_info:
            return

        cust_safe = re.sub(r"[^\w\s-]", "", self.last_customer_name).strip().replace(" ", "_") or "khach"
        plan = self.last_license_info.get("plan", "KEY")
        default_name = f"license_{cust_safe}_{plan}.lic"
        initial_dir = self.export_dir_var.get()
        if not os.path.isdir(initial_dir):
            try:
                Path(initial_dir).mkdir(parents=True, exist_ok=True)
            except Exception:
                initial_dir = str(TOOLS_DIR)

        out_path = filedialog.asksaveasfilename(
            title="Lưu tệp giấy phép T-TTS cho khách",
            initialdir=initial_dir,
            initialfile=default_name,
            defaultextension=".lic",
            filetypes=[("T-TTS License File (*.lic)", "*.lic"), ("Text File (*.txt)", "*.txt"), ("Tất cả (*.*)", "*.*")],
        )
        if out_path:
            p = Path(out_path)
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(self.last_generated_key, encoding="utf-8")
                # Ghi nhớ thư mục lưu
                self.export_dir_var.set(str(p.parent))
                self.config["export_dir"] = str(p.parent)
                save_config(self.config)
                messagebox.showinfo("Đã Lưu File Key", f"✅ Đã lưu tệp giấy phép thành công tại:\n{out_path}")
            except Exception as e:
                messagebox.showerror("Lỗi Lưu", f"Không thể lưu file: {e}")

    # ==========================================================================
    # QUẢN LÝ LỊCH SỬ CẤP KEY (TAB 2)
    # ==========================================================================
    def _refresh_history_table(self):
        self._filter_history()

    def _filter_history(self):
        query = getattr(self, "search_entry", None)
        keyword = (query.get().strip().lower() if query else "")

        for row in self.tree.get_children():
            self.tree.delete(row)

        records = load_history()
        count = 0
        c_1d, c_7d, c_30d, c_6m, c_perm = 0, 0, 0, 0, 0

        for r in records:
            p = r.get("plan", "")
            if p == "KEY-1D":
                c_1d += 1
            elif p == "KEY-7D":
                c_7d += 1
            elif p == "KEY-30D":
                c_30d += 1
            elif p == "KEY-6M":
                c_6m += 1
            elif p == "KEY-PERM":
                c_perm += 1

            # Lọc theo từ khóa
            match = True
            if keyword:
                combined = f"{r.get('cust_name', '')} {r.get('cust_contact', '')} {r.get('mid', '')} {r.get('note', '')}".lower()
                if keyword not in combined:
                    match = False

            if match:
                count += 1
                self.tree.insert(
                    "",
                    "end",
                    iid=r.get("id"),
                    values=(
                        r.get("created_at", ""),
                        r.get("cust_name", ""),
                        r.get("cust_contact", ""),
                        r.get("mid", ""),
                        r.get("plan", ""),
                        r.get("note", ""),
                    ),
                )

        self.stats_lbl.configure(text=f"Tổng: {len(records)} key  |  1D: {c_1d}  ·  7D: {c_7d}  ·  30D: {c_30d}  ·  6M: {c_6m}  ·  Vĩnh viễn: {c_perm}  |  Đang hiển thị: {count}")

    def _clear_search(self):
        self.search_entry.delete(0, tk.END)
        self._filter_history()

    def _on_history_select(self, event=None):
        sel = self.tree.selection()
        state = "normal" if sel else "disabled"
        self.btn_hist_copy_msg.configure(state=state)
        self.btn_hist_copy_key.configure(state=state)
        self.btn_hist_export_lic.configure(state=state)
        self.btn_hist_delete.configure(state=state)

    def _get_selected_history_record(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        rec_id = sel[0]
        for r in load_history():
            if r.get("id") == rec_id:
                return r
        return None

    def _hist_copy_message(self):
        r = self._get_selected_history_record()
        if not r:
            return
        msg = self._format_customer_message(
            r.get("cust_name", "Khách hàng"),
            r.get("cust_contact", ""),
            r.get("mid", ""),
            r.get("duration_name", r.get("plan", "Dùng thử")),
            r.get("key_string", ""),
        )
        self.clipboard_clear()
        self.clipboard_append(msg)
        self.update_idletasks()
        messagebox.showinfo("Đã Sao Chép Tin Nhắn", f"✅ Đã sao chép tin nhắn gửi cho khách '{r.get('cust_name')}'!")

    def _hist_copy_key(self):
        r = self._get_selected_history_record()
        if not r or not r.get("key_string"):
            return
        self.clipboard_clear()
        self.clipboard_append(r["key_string"])
        self.update_idletasks()
        messagebox.showinfo("Đã Sao Chép Key", "✅ Đã sao chép chuỗi mã key vào bộ nhớ đệm!")

    def _hist_export_lic(self):
        r = self._get_selected_history_record()
        if not r or not r.get("key_string"):
            return
        cust_safe = re.sub(r"[^\w\s-]", "", r.get("cust_name", "khach")).strip().replace(" ", "_") or "khach"
        plan = r.get("plan", "KEY")
        default_name = f"license_{cust_safe}_{plan}.lic"
        initial_dir = self.export_dir_var.get()
        if not os.path.isdir(initial_dir):
            try:
                Path(initial_dir).mkdir(parents=True, exist_ok=True)
            except Exception:
                initial_dir = str(TOOLS_DIR)

        out_path = filedialog.asksaveasfilename(
            title=f"Xuất file license cho khách {r.get('cust_name')}",
            initialdir=initial_dir,
            initialfile=default_name,
            defaultextension=".lic",
            filetypes=[("T-TTS License File (*.lic)", "*.lic"), ("Text File (*.txt)", "*.txt"), ("Tất cả (*.*)", "*.*")],
        )
        if out_path:
            p = Path(out_path)
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(r["key_string"], encoding="utf-8")
                self.export_dir_var.set(str(p.parent))
                self.config["export_dir"] = str(p.parent)
                save_config(self.config)
                messagebox.showinfo("Thành Công", f"✅ Đã lưu file tại:\n{out_path}")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể lưu file: {e}")

    def _hist_delete_record(self):
        r = self._get_selected_history_record()
        if not r:
            return
        ans = messagebox.askyesno(
            "Xác nhận xóa",
            f"Bạn có chắc muốn xóa bản ghi cấp key cho khách '{r.get('cust_name')}' ({r.get('mid')}) không?\n\n"
            f"(Lưu ý: Thao tác này chỉ xóa khỏi lịch sử lưu trữ trên tool, không làm mất hiệu lực key của khách).",
        )
        if ans:
            delete_history_record(r.get("id"))
            self._refresh_history_table()
            self._on_history_select()

    # ==========================================================================
    # SOÁT & KIỂM TRA KEY (TAB 3)
    # ==========================================================================
    def _inspect_custom_key(self):
        raw = self.inspect_entry.get("1.0", tk.END).strip()
        raw = re.sub(r"\s+", "", raw)
        if not raw:
            messagebox.showwarning("Thiếu Dữ Liệu", "Vui lòng nhập chuỗi key bản quyền cần kiểm tra!")
            return

        try:
            payload = verify_license_key(raw)
            plan_name = VALID_PLANS.get(payload.get("plan", "").lower().replace("key-", "")).get("name", payload.get("plan"))
            iat_readable = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(payload.get("iat", 0)))

            res_text = (
                f"✅ KẾT QUẢ XÁC MINH: CHỮ KÝ SỐ ED25519 HỢP LỆ (CHUẨN 100%)\n"
                f"==========================================================\n"
                f"• Trạng thái chữ ký: CHÍNH HÃNG DO NHÀ PHÁT TRIỂN KÝ SỐ\n"
                f"• Gói bản quyền: {payload.get('plan')} ({plan_name})\n"
                f"• Thời lượng: {payload.get('hours')} giờ tính từ lúc kích hoạt\n"
                f"• Cấp riêng cho Mã Máy: {payload.get('mid')}\n"
                f"• License ID: {payload.get('lid')}\n"
                f"• Ngày giờ phát hành: {iat_readable}\n"
                f"• Ghi chú đi kèm: {payload.get('note', '(Không có)')}\n"
                f"• Phiên bản định dạng: v{payload.get('v', 1)}\n"
            )
            self.inspect_result_lbl.configure(text=res_text, fg="#1B5E20")
        except Exception as e:
            err_text = (
                f"❌ KẾT QUẢ XÁC MINH: KEY KHÔNG HỢP LỆ HOẶC BỊ SỬA ĐỔI!\n"
                f"==========================================================\n"
                f"Chi tiết lỗi: {e}\n\n"
                f"Khuyến nghị: Yêu cầu khách hàng sao chép lại toàn bộ chuỗi key mà bạn đã gửi, "
                f"tránh sao chép thiếu ký tự hoặc bị phần mềm gõ tiếng Việt làm sai lệch."
            )
            self.inspect_result_lbl.configure(text=err_text, fg="#B71C1C")


def main():
    app = KeyGeneratorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
