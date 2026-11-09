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
            print(f"Lỗi khi tải dự án '{project_id}': {e}")
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


project_manager = ProjectManager()
