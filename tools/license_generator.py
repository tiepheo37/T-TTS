"""license_generator.py — CÔNG CỤ CẤP BẢN QUYỀN OFFLINE DÀNH CHO NHÀ PHÁT TRIỂN T-TTS v1.0.1
==========================================================================================
Công cụ độc lập dành riêng cho Developer để:
1. Khởi tạo và quản lý cặp khóa số Ed25519 (Private Key & Public Key).
2. Tạo mã bản quyền có chữ ký số cho từng máy Windows của khách hàng.
3. Hỗ trợ chính xác 3 thời hạn:
   - 1 ngày  (KEY-1D  - 24 giờ)
   - 7 ngày  (KEY-7D  - 168 giờ)
   - 30 ngày (KEY-30D - 720 giờ)
4. Xuất key dạng chuỗi văn bản (dễ sao chép) hoặc tệp giấy phép (.lic).
5. Kiểm tra và xác thực tính hợp lệ của key đã cấp.

LƯU Ý BẢO MẬT:
- Tệp khóa riêng `master_private.pem` PHẢI ĐƯỢC SAO LƯU VÀ BẢO MẬT TUYỆT ĐỐI.
- KHÔNG BAO GIỜ đóng gói công cụ này hoặc tệp khóa riêng vào bộ cài đặt của người dùng!
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import uuid
from pathlib import Path

# Đảm bảo mã hóa UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("[LỖI] Chưa cài đặt thư viện 'cryptography'. Vui lòng chạy:")
    print("      pip install cryptography")
    sys.exit(1)

# Khóa Master Ed25519 chuẩn của Developer (khớp chính xác 100% với backend T-TTS v1.0.1)
DEFAULT_MASTER_PRIVATE_KEY_PEM = (
    b"-----BEGIN PRIVATE KEY-----\n"
    b"MC4CAQAwBQYDK2VwBCIEIEobGGUvDqwqmsx7Zasc5ysVmegO0hkIAQxzxliWrNcv\n"
    b"-----END PRIVATE KEY-----\n"
)
DEFAULT_MASTER_PUBLIC_KEY_PEM = (
    b"-----BEGIN PUBLIC KEY-----\n"
    b"MCowBQYDK2VwAyEANK/Fn9eXs78hKfVOGhLPtIW6IOJevBdjY8Et8CIvdtQ=\n"
    b"-----END PUBLIC KEY-----\n"
)


def _get_base_tools_dir() -> Path:
    """Xác định vị trí thư mục tools thực tế trên ổ cứng (kể cả khi chạy file .exe qua PyInstaller)."""
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir, exe_dir / "tools", exe_dir.parent / "tools"])
    script_dir = Path(__file__).resolve().parent
    candidates.extend([script_dir, script_dir / "tools", script_dir.parent / "tools"])
    cwd = Path.cwd().resolve()
    candidates.extend([cwd / "tools", cwd])

    for c in candidates:
        if (c / "keys" / "master_private.pem").exists():
            return c

    for c in candidates:
        if "_MEI" not in str(c):
            return c

    return candidates[0]


TOOLS_DIR = _get_base_tools_dir()
KEYS_DIR = TOOLS_DIR / "keys"
PRIVATE_KEY_PATH = KEYS_DIR / "master_private.pem"
PUBLIC_KEY_PATH = KEYS_DIR / "master_public.pem"

VALID_PLANS = {
    "1d": {"plan": "KEY-1D", "hours": 24, "name": "1 Ngày (24 giờ)"},
    "7d": {"plan": "KEY-7D", "hours": 168, "name": "7 Ngày (168 giờ)"},
    "30d": {"plan": "KEY-30D", "hours": 720, "name": "30 Ngày (720 giờ)"},
}


def ensure_keys_dir() -> None:
    """Tạo thư mục chứa khóa nếu chưa có và đảm bảo luôn có tệp khóa master chuẩn."""
    try:
        KEYS_DIR.mkdir(parents=True, exist_ok=True)
        if not PRIVATE_KEY_PATH.exists():
            PRIVATE_KEY_PATH.write_bytes(DEFAULT_MASTER_PRIVATE_KEY_PEM)
        if not PUBLIC_KEY_PATH.exists():
            PUBLIC_KEY_PATH.write_bytes(DEFAULT_MASTER_PUBLIC_KEY_PEM)
    except Exception:
        pass


def generate_master_keypair(force: bool = False) -> tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """Tạo mới cặp khóa Ed25519 cho nhà phát triển."""
    ensure_keys_dir()
    if PRIVATE_KEY_PATH.exists() and not force:
        raise FileExistsError(
            f"Khóa riêng đã tồn tại tại {PRIVATE_KEY_PATH}. "
            "Dùng cờ --force nếu bạn thực sự muốn ghi đè (CẢNH BÁO: Tất cả key cũ đã phát hành sẽ không còn dùng được!)."
        )

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    PRIVATE_KEY_PATH.write_bytes(priv_bytes)
    PUBLIC_KEY_PATH.write_bytes(pub_bytes)

    # Lấy chuỗi raw public key dạng base64 để nhúng vào backend
    raw_pub = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pub_b64 = base64.b64encode(raw_pub).decode("ascii")

    print("\n" + "=" * 70)
    print("✅ ĐÃ KHỞI TẠO THÀNH CÔNG CẶP KHÓA MASTER ED25519")
    print("=" * 70)
    print(f"1. Khóa riêng (PRIVATE KEY): {PRIVATE_KEY_PATH}")
    print(f"   -> [BẢO MẬT] Giữ bí mật tuyệt đối, không chia sẻ cho bất kỳ ai.")
    print(f"2. Khóa công khai (PUBLIC KEY): {PUBLIC_KEY_PATH}")
    print(f"3. Chuỗi Public Key Raw Base64 để nhúng vào backend:")
    print(f"\n   EMBEDDED_PUBLIC_KEY = \"{pub_b64}\"\n")
    print("=" * 70 + "\n")

    return private_key, public_key


def load_private_key() -> ed25519.Ed25519PrivateKey:
    """Nạp khóa riêng của developer. Tự động khôi phục nếu tệp bị thiếu."""
    ensure_keys_dir()
    if PRIVATE_KEY_PATH.exists():
        try:
            return serialization.load_pem_private_key(
                PRIVATE_KEY_PATH.read_bytes(),
                password=None,
            )
        except Exception:
            pass

    # Luôn đảm bảo nạp đúng Master Key chuẩn khớp với backend
    return serialization.load_pem_private_key(
        DEFAULT_MASTER_PRIVATE_KEY_PEM,
        password=None,
    )


def load_public_key() -> ed25519.Ed25519PublicKey:
    """Nạp khóa công khai."""
    ensure_keys_dir()
    if PUBLIC_KEY_PATH.exists():
        try:
            return serialization.load_pem_public_key(PUBLIC_KEY_PATH.read_bytes())
        except Exception:
            pass
    return serialization.load_pem_public_key(DEFAULT_MASTER_PUBLIC_KEY_PEM)


def create_license_key(
    machine_id: str,
    duration_code: str,
    note: str = "",
    custom_lic_id: str | None = None,
) -> dict:
    """Tạo giấy phép có chữ ký số cho Machine ID và thời hạn quy định.

    duration_code: '1d', '7d', hoặc '30d'
    """
    code = duration_code.strip().lower()
    if code not in VALID_PLANS:
        raise ValueError(
            f"Thời hạn không hợp lệ: '{duration_code}'. "
            f"Chỉ chấp nhận đúng 3 thời hạn: {', '.join(VALID_PLANS.keys())} (1d, 7d, 30d)."
        )

    clean_mid = machine_id.strip().upper()
    if not clean_mid:
        raise ValueError("Mã máy (Machine ID) không được để trống.")

    private_key = load_private_key()
    plan_info = VALID_PLANS[code]

    lic_id = custom_lic_id or str(uuid.uuid4())
    issued_at = int(time.time())

    # Cấu trúc payload chuẩn hoá
    payload = {
        "v": 1,
        "lid": lic_id,
        "mid": clean_mid,
        "plan": plan_info["plan"],
        "hours": plan_info["hours"],
        "iat": issued_at,
    }
    if note:
        payload["note"] = note.strip()

    # Chuyển payload sang chuỗi JSON canonical (có thứ tự cố định không cách thừa)
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    # Ký số Ed25519
    signature = private_key.sign(canonical_bytes)

    # Mã hoá base64 urlsafe
    payload_b64 = base64.urlsafe_b64encode(canonical_bytes).decode("ascii").rstrip("=")
    sig_b64 = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")

    # Định dạng key hoàn chỉnh: TTTS-LIC1-<payload_b64>.<sig_b64>
    key_string = f"TTTS-LIC1-{payload_b64}.{sig_b64}"

    return {
        "key_string": key_string,
        "license_id": lic_id,
        "machine_id": clean_mid,
        "plan": plan_info["plan"],
        "duration_hours": plan_info["hours"],
        "duration_name": plan_info["name"],
        "issued_at": issued_at,
        "issued_at_readable": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(issued_at)),
        "note": note,
    }


def verify_license_key(key_string: str, public_key: ed25519.Ed25519PublicKey | None = None) -> dict:
    """Xác minh tính toàn vẹn và chữ ký số của key.

    Trả về dict payload nếu hợp lệ, raise Exception nếu sai.
    """
    raw = key_string.strip()
    if not raw.startswith("TTTS-LIC1-"):
        raise ValueError("Định dạng key không hợp lệ. Phải bắt đầu bằng 'TTTS-LIC1-'.")

    token = raw[len("TTTS-LIC1-"):]
    if "." not in token:
        raise ValueError("Định dạng token bị hỏng hoặc thiếu phần chữ ký số.")

    payload_b64, sig_b64 = token.split(".", 1)

    # Bổ sung padding cho base64 urlsafe nếu cần
    def _pad_b64(s: str) -> bytes:
        missing = len(s) % 4
        if missing:
            s += "=" * (4 - missing)
        return base64.urlsafe_b64decode(s.encode("ascii"))

    try:
        canonical_bytes = _pad_b64(payload_b64)
        signature_bytes = _pad_b64(sig_b64)
    except Exception as e:
        raise ValueError(f"Không thể giải mã dữ liệu Base64 trong key: {e}")

    if public_key is None:
        public_key = load_public_key()

    # Kiểm tra chữ ký Ed25519
    try:
        public_key.verify(signature_bytes, canonical_bytes)
    except Exception:
        raise ValueError("Chữ ký số Ed25519 KHÔNG HỢP LỆ! Key đã bị sửa đổi hoặc tạo bởi khóa riêng khác.")

    try:
        payload = json.loads(canonical_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Dữ liệu JSON trong giấy phép bị lỗi cấu trúc: {e}")

    return payload


def interactive_menu():
    """Giao diện dòng lệnh tương tác cho Developer."""
    while True:
        print("\n" + "=" * 65)
        print("  🇻🇳 T-TTS v1.0.1 — CÔNG CỤ CẤP BẢN QUYỀN OFFLINE (DEVELOPER)")
        print("=" * 65)
        print("1. Tạo mới cặp khóa Master Ed25519 (Private & Public Key)")
        print("2. Cấp key mới cho người dùng (1 ngày / 7 ngày / 30 ngày)")
        print("3. Kiểm tra / Xem thông tin một key đã cấp")
        print("4. Thoát")
        print("-" * 65)
        choice = input("Lựa chọn của bạn [1-4]: ").strip()

        if choice == "1":
            try:
                generate_master_keypair(force=False)
            except FileExistsError as fee:
                print(f"\n[CẢNH BÁO] {fee}")
                overwrite = input("Bạn có CHẮC CHẮN muốn tạo lại và ghi đè khóa không? (nhập 'yes' để xác nhận): ").strip()
                if overwrite.lower() == "yes":
                    generate_master_keypair(force=True)
                else:
                    print("Đã hủy tạo lại khóa.")
            except Exception as e:
                print(f"[LỖI] {e}")

        elif choice == "2":
            if not PRIVATE_KEY_PATH.exists():
                print(f"\n[LỖI] Chưa có khóa riêng. Vui lòng chọn mục 1 để tạo cặp khóa trước!")
                continue

            mid = input("\nNhập Mã Máy (Machine ID do người dùng gửi): ").strip()
            if not mid:
                print("[LỖI] Mã máy không được để trống!")
                continue

            print("\nChọn thời hạn cấp phép:")
            print("  1. 1 Ngày  (KEY-1D  - 24 giờ)")
            print("  2. 7 Ngày  (KEY-7D  - 168 giờ)")
            print("  3. 30 Ngày (KEY-30D - 720 giờ)")
            dur_sel = input("Chọn thời hạn [1/2/3 hoặc 1d/7d/30d]: ").strip().lower()

            dur_map = {"1": "1d", "2": "7d", "3": "30d", "1d": "1d", "7d": "7d", "30d": "30d"}
            dur_code = dur_map.get(dur_sel)
            if not dur_code:
                print("[LỖI] Lựa chọn thời hạn không hợp lệ!")
                continue

            note = input("Ghi chú khách hàng (tuỳ chọn, ví dụ: 'Anh Nam - Dùng thử'): ").strip()

            try:
                res = create_license_key(mid, dur_code, note=note)
                print("\n" + "=" * 70)
                print("🎉 CẤP BẢN QUYỀN THÀNH CÔNG!")
                print("=" * 70)
                print(f"Mã giấy phép (License ID): {res['license_id']}")
                print(f"Mã máy được cấp (MID):     {res['machine_id']}")
                print(f"Gói bản quyền:             {res['plan']} ({res['duration_name']})")
                print(f"Thời điểm cấp:             {res['issued_at_readable']}")
                if res['note']:
                    print(f"Ghi chú:                   {res['note']}")
                print("-" * 70)
                print("CHUỖI KEY BẢN QUYỀN ĐỂ GỬI CHO KHÁCH HÀNG (SAO CHÉP DÒNG DƯỚI):")
                print(f"\n{res['key_string']}\n")
                print("=" * 70)

                # Tuỳ chọn xuất file .lic
                save_file = input("Lưu key ra tệp .lic để gửi cho người dùng? (y/n) [mặc định y]: ").strip().lower()
                if save_file in ("", "y", "yes"):
                    out_dir = TOOLS_DIR / "exported_licenses"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    safe_mid = res['machine_id'].replace("-", "_")
                    lic_file = out_dir / f"license_{safe_mid}_{res['plan']}.lic"
                    lic_file.write_text(res['key_string'], encoding="utf-8")
                    print(f"Đã lưu tệp giấy phép tại: {lic_file}")
            except Exception as e:
                print(f"[LỖI] Không thể tạo key: {e}")

        elif choice == "3":
            key_input = input("\nDán chuỗi key hoặc đường dẫn tệp .lic cần kiểm tra:\n").strip()
            if not key_input:
                continue

            if os.path.isfile(key_input):
                key_input = Path(key_input).read_text(encoding="utf-8").strip()

            try:
                info = verify_license_key(key_input)
                print("\n" + "=" * 65)
                print("✅ KẾT QUẢ XÁC MINH: CHỮ KÝ HỢP LỆ!")
                print("=" * 65)
                print(f"Mã giấy phép (License ID): {info.get('lid')}")
                print(f"Mã máy (Machine ID):       {info.get('mid')}")
                print(f"Loại gói:                  {info.get('plan')}")
                print(f"Thời hạn cấp:              {info.get('hours')} giờ")
                iat = info.get('iat')
                if iat:
                    print(f"Thời điểm tạo:             {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(iat))}")
                if info.get('note'):
                    print(f"Ghi chú:                   {info.get('note')}")
                print("=" * 65)
            except Exception as e:
                print(f"\n❌ XÁC MINH THẤT BẠI: {e}")

        elif choice == "4":
            print("Tạm biệt!")
            break
        else:
            print("Lựa chọn không hợp lệ, vui lòng chọn từ 1 đến 4.")


def main():
    parser = argparse.ArgumentParser(description="T-TTS v1.0.1 Developer License Generator")
    parser.add_argument("--gen-keys", action="store_true", help="Khởi tạo cặp khóa Ed25519 mới")
    parser.add_argument("--force", action="store_true", help="Ghi đè khóa cũ nếu đã tồn tại")
    parser.add_argument("--create", action="store_true", help="Tạo key bản quyền mới")
    parser.add_argument("--machine", type=str, help="Mã máy (Machine ID) của khách hàng")
    parser.add_argument("--duration", type=str, choices=["1d", "7d", "30d"], help="Thời hạn (1d, 7d, 30d)")
    parser.add_argument("--note", type=str, default="", help="Ghi chú người dùng")
    parser.add_argument("--out", type=str, help="Đường dẫn tệp để xuất key ra đĩa")
    parser.add_argument("--verify", type=str, help="Xác minh một chuỗi key hoặc tệp .lic")

    args = parser.parse_args()

    if args.gen_keys:
        generate_master_keypair(force=args.force)
        return

    if args.verify:
        key_content = args.verify
        if os.path.isfile(key_content):
            key_content = Path(key_content).read_text(encoding="utf-8").strip()
        try:
            info = verify_license_key(key_content)
            print("VALID KEY:", json.dumps(info, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"INVALID KEY: {e}")
            sys.exit(1)
        return

    if args.create:
        if not args.machine or not args.duration:
            print("[LỖI] Khi dùng --create, bạn phải chỉ định cả --machine và --duration (1d/7d/30d).")
            sys.exit(1)
        res = create_license_key(args.machine, args.duration, note=args.note)
        print(res["key_string"])
        if args.out:
            Path(args.out).write_text(res["key_string"], encoding="utf-8")
            print(f"[OK] Đã ghi ra tệp: {args.out}", file=sys.stderr)
        return

    # Nếu không có cờ tham số, mở menu tương tác
    interactive_menu()


if __name__ == "__main__":
    main()
