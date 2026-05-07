"""基础设施层 - Skill 文件存储服务

负责 ZIP 文件的验证、解压、存储和清理。
"""

import shutil
import zipfile
from pathlib import Path
from typing import Optional
from uuid import uuid4

# 安全限制
MAX_ZIP_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_EXTRACTED_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_FILE_COUNT = 200

# 存储根目录（项目根目录/storage/skills/）
# backend/src/infrastructure/storage -> 项目根
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
SKILLS_STORAGE_ROOT = _PROJECT_ROOT / "storage" / "skills"


class SkillStorageError(Exception):
    """Skill 存储相关错误"""


class SkillStorageService:
    """Skill ZIP 文件存储服务"""

    def __init__(self, storage_root: Optional[Path] = None) -> None:
        self.storage_root = storage_root or SKILLS_STORAGE_ROOT
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def save_zip(self, zip_bytes: bytes) -> tuple[str, str]:
        """验证并解压 ZIP，返回 (skill_dir_name, skill_md_content)。

        Returns:
            tuple: (目录名称, SKILL.md 文件内容)

        Raises:
            SkillStorageError: 验证失败或解压错误
        """
        # 1. 大小检查
        if len(zip_bytes) > MAX_ZIP_SIZE:
            raise SkillStorageError(
                f"ZIP 文件过大（{len(zip_bytes) / 1024 / 1024:.1f} MB），"
                f"最大允许 {MAX_ZIP_SIZE / 1024 / 1024:.0f} MB"
            )

        # 2. 验证 ZIP 格式
        import io

        buf = io.BytesIO(zip_bytes)
        if not zipfile.is_zipfile(buf):
            raise SkillStorageError("上传的文件不是有效的 ZIP 格式")

        buf.seek(0)
        try:
            zf = zipfile.ZipFile(buf, "r")
        except zipfile.BadZipFile:
            raise SkillStorageError("ZIP 文件已损坏")

        with zf:
            # 3. 安全检查：路径穿越 + zip bomb + 文件数量
            infos = zf.infolist()
            if len(infos) > MAX_FILE_COUNT:
                raise SkillStorageError(
                    f"ZIP 包含过多文件（{len(infos)}），最大允许 {MAX_FILE_COUNT}"
                )

            total_size = 0
            for info in infos:
                # 路径穿越检测
                if info.filename.startswith("/") or ".." in info.filename:
                    raise SkillStorageError(
                        f"ZIP 包含不安全的路径: {info.filename}"
                    )
                total_size += info.file_size

            if total_size > MAX_EXTRACTED_SIZE:
                raise SkillStorageError(
                    f"解压后体积过大（{total_size / 1024 / 1024:.1f} MB），"
                    f"最大允许 {MAX_EXTRACTED_SIZE / 1024 / 1024:.0f} MB"
                )

            # 4. 查找 SKILL.md（根目录）
            skill_md_content = self._find_skill_md(zf)

            # 5. 解压到唯一目录
            dir_name = str(uuid4())
            target_dir = self.storage_root / dir_name
            target_dir.mkdir(parents=True, exist_ok=True)

            try:
                zf.extractall(target_dir)
            except Exception as e:
                # 清理已创建的目录
                shutil.rmtree(target_dir, ignore_errors=True)
                raise SkillStorageError(f"解压失败: {e}")

        return dir_name, skill_md_content

    def replace_zip(self, old_dir_name: str, zip_bytes: bytes) -> tuple[str, str]:
        """替换已有 Skill 的 ZIP 文件。

        先保存新的，成功后删除旧的。
        """
        new_dir_name, skill_md_content = self.save_zip(zip_bytes)
        # 删除旧目录
        self.remove(old_dir_name)
        return new_dir_name, skill_md_content

    def remove(self, dir_name: str) -> None:
        """删除 Skill 存储目录"""
        if not dir_name:
            return
        target_dir = self.storage_root / dir_name
        if target_dir.exists() and target_dir.is_dir():
            # 安全检查：确保在 storage_root 下
            try:
                target_dir.resolve().relative_to(self.storage_root.resolve())
            except ValueError:
                return
            shutil.rmtree(target_dir, ignore_errors=True)

    def get_skill_path(self, dir_name: str) -> Path:
        """获取 Skill 存储目录的完整路径"""
        return self.storage_root / dir_name

    def _find_skill_md(self, zf: zipfile.ZipFile) -> str:
        """在 ZIP 中查找根目录的 SKILL.md 文件"""
        # 优先精确匹配根目录 SKILL.md
        for name in zf.namelist():
            # 根目录文件：没有 / 或者只有一层
            parts = name.split("/")
            basename = parts[-1] if parts[-1] else (
                parts[-2] if len(parts) > 1 else "")

            # 精确匹配：SKILL.md 在根目录或一级目录根
            if basename.upper() == "SKILL.MD":
                # 确保只在根层级或压缩时带的单层目录根
                depth = len([p for p in parts if p])
                if depth <= 2:  # "SKILL.md" 或 "folder/SKILL.md"
                    content = zf.read(name).decode("utf-8", errors="replace")
                    return content

        raise SkillStorageError(
            "ZIP 根目录中未找到 SKILL.md 文件。"
            "请确保 ZIP 包的根目录包含 SKILL.md"
        )
