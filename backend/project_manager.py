"""backend/project_manager.py — QUẢN LÝ DỰ ÁN CHO AUDIO STUDIO, BROADCAST 2.0 & SCHEDULE STUDIO
=============================================================================
Quản lý lưu, tải, liệt kê và xóa dự án dạng JSON có cấu trúc rõ ràng.
Hoàn toàn độc lập với history.json và các tệp dữ liệu cũ.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import init_storage

_STORAGE = init_storage()
DATA_DIR: Path = _STORAGE["data_dir"]


def get_projects_dir(project_type: str) -> Path:
    """Trả về thư mục lưu trữ dự án theo loại (audio, broadcast, schedule)."""
    p_dir = DATA_DIR / "projects" / project_type.strip().lower()
    p_dir.mkdir(parents=True, exist_ok=True)
    return p_dir


class ProjectManager:
    """Điều phối lưu trữ và quản lý dự án cho các Studio mới."""

    @staticmethod
    def create_project_schema(
        project_type: str,
        name: str,
        data: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Tạo đối tượng dự án chuẩn hóa theo schema định sẵn."""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        pid = project_id or f"{project_type}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        return {
            "id": pid,
            "name": name.strip() or f"Dự án {project_type.capitalize()}",
            "type": project_type.strip().lower(),
            "created_at": now_str,
            "updated_at": now_str,
            "version": "1.0",
            "data": data or {},
        }

    @staticmethod
    def save_project(project_type: str, project_dict: Dict[str, Any]) -> str:
        """Lưu hoặc cập nhật dự án ra tệp JSON."""
        ptype = project_type.strip().lower()
        p_dir = get_projects_dir(ptype)

        pid = project_dict.get("id")
        if not pid:
            pid = f"{ptype}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            project_dict["id"] = pid

        project_dict["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if "created_at" not in project_dict:
            project_dict["created_at"] = project_dict["updated_at"]

        clean_dict = {k: v for k, v in project_dict.items() if not k.startswith("_")}
        file_path = p_dir / f"{pid}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(clean_dict, f, ensure_ascii=False, indent=2)

        return pid

    @staticmethod
    def load_project(project_type: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Tải dữ liệu dự án từ tệp JSON."""
        ptype = project_type.strip().lower()
        file_path = get_projects_dir(ptype) / f"{project_id}.json"
        if not file_path.is_file():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            try:
                print(f"[ProjectManager] Error loading project '{project_id}': {e}")
            except Exception:
                pass
            try:
                corrupt_backup = file_path.with_suffix(f".corrupted_{int(time.time())}")
                file_path.rename(corrupt_backup)
            except Exception:
                pass
            return None

    @staticmethod
    def list_projects(project_type: str) -> List[Dict[str, Any]]:
        """Liệt kê toàn bộ dự án thuộc một loại cụ thể, sắp xếp theo thời gian cập nhật mới nhất."""
        ptype = project_type.strip().lower()
        p_dir = get_projects_dir(ptype)
        projects = []
        for f in p_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    projects.append({
                        "id": data.get("id", f.stem),
                        "name": data.get("name", f.stem),
                        "type": data.get("type", ptype),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "version": data.get("version", "1.0"),
                    })
            except Exception:
                continue

        projects.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return projects

    @staticmethod
    def delete_project(project_type: str, project_id: str) -> bool:
        """Xóa một dự án."""
        ptype = project_type.strip().lower()
        file_path = get_projects_dir(ptype) / f"{project_id}.json"
        if file_path.is_file():
            try:
                file_path.unlink()
                return True
            except Exception:
                return False
        return False

    # -------------------------------------------------------------------------
    # HỖ TRỢ DỰ ÁN TÀI LIỆU VĂN BẢN (DOCUMENT-TO-SPEECH PROJECTS) — V3.1.0
    # -------------------------------------------------------------------------
    @classmethod
    def create_document_project(
        cls,
        name: str,
        raw_text: str,
        source_path: Optional[str] = None,
        voice_id: str = "v-nam-1",
        speed: float = 1.0,
        fmt: str = "wav",
    ) -> Dict[str, Any]:
        """Khởi tạo dự án chuyển đổi tài liệu sang giọng nói."""
        from .text_processor import VietnameseTextProcessor

        normalized = VietnameseTextProcessor.full_normalize(raw_text)
        chunks = VietnameseTextProcessor.smart_split_paragraphs(normalized)
        stats = VietnameseTextProcessor.calculate_statistics(normalized)

        segments = []
        for idx, chunk in enumerate(chunks):
            segments.append({
                "index": idx,
                "text": chunk,
                "status": "pending",  # pending | synthesizing | completed | error
                "audio_path": None,
                "duration": 0.0,
                "error": None,
            })

        project_data = {
            "source_path": str(source_path) if source_path else None,
            "raw_text": raw_text,
            "normalized_text": normalized,
            "voice_id": voice_id,
            "speed": speed,
            "format": fmt,
            "statistics": stats,
            "segments": segments,
            "total_segments": len(segments),
            "completed_segments": 0,
            "merged_audio_path": None,
        }

        schema = cls.create_project_schema(
            project_type="documents",
            name=name,
            data=project_data,
        )
        return schema

    @classmethod
    def save_document_project(cls, project_dict: Dict[str, Any]) -> str:
        """Lưu dự án tài liệu vào thư mục data/projects/documents/."""
        return cls.save_project("documents", project_dict)

    @classmethod
    def save_as_document_project(cls, project_dict: Dict[str, Any], new_name: str) -> str:
        """Lưu dự án tài liệu thành một bản mới với tên và ID khác (Save As)."""
        new_dict = dict(project_dict)
        new_pid = f"documents_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        new_dict["id"] = new_pid
        new_dict["name"] = new_name.strip()
        new_dict["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        new_dict["updated_at"] = new_dict["created_at"]
        return cls.save_project("documents", new_dict)

    @classmethod
    def rename_document_project(cls, project_id: str, new_name: str) -> bool:
        """Đổi tên dự án tài liệu."""
        proj = cls.load_document_project(project_id)
        if not proj:
            return False
        proj["name"] = new_name.strip()
        cls.save_document_project(proj)
        return True

    @classmethod
    def duplicate_document_project(cls, project_id: str) -> Optional[Dict[str, Any]]:
        """Nhân bản dự án tài liệu."""
        proj = cls.load_document_project(project_id)
        if not proj:
            return None
        clone_name = f"{proj.get('name', 'Dự án')} (Bản sao)"
        new_pid = cls.save_as_document_project(proj, clone_name)
        return cls.load_document_project(new_pid)

    @classmethod
    def delete_document_project(cls, project_id: str, delete_audio: bool = False) -> bool:
        """Xóa dự án tài liệu (tùy chọn xóa kèm tệp âm thanh liên kết)."""
        proj = cls.load_document_project(project_id)
        if delete_audio and proj:
            data = proj.get("data", {})
            # Xóa các segment audio nếu người dùng yêu cầu
            for seg in data.get("segments", []):
                ap = seg.get("audio_path")
                if ap and Path(ap).is_file():
                    try:
                        Path(ap).unlink()
                    except Exception:
                        pass
            merged = data.get("merged_audio_path")
            if merged and Path(merged).is_file():
                try:
                    Path(merged).unlink()
                except Exception:
                    pass
        return cls.delete_project("documents", project_id)

    @classmethod
    def get_recent_document_projects(cls, limit: int = 10) -> List[Dict[str, Any]]:
        """Lấy danh sách các dự án tài liệu gần đây nhất."""
        all_docs = cls.list_document_projects()
        return all_docs[:limit]

    @classmethod
    def load_document_project(cls, project_id: str) -> Optional[Dict[str, Any]]:
        """Tải dự án tài liệu theo ID."""
        return cls.load_project("documents", project_id)

    @classmethod
    def list_document_projects(cls) -> List[Dict[str, Any]]:
        """Liệt kê toàn bộ dự án tài liệu hiện có."""
        return cls.list_projects("documents")


project_manager = ProjectManager()
