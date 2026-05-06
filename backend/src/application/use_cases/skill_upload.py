"""应用层 - Skill ZIP 上传用例"""

from datetime import datetime
from uuid import uuid4

from src.domain.entities.skill_def import SkillDef
from src.domain.repositories.skill_repository import ISkillRepository
from src.domain.services.skill_md_parser import parse_skill_md
from src.infrastructure.storage.skill_storage_service import (
    SkillStorageService,
    SkillStorageError,
)


class SkillUploadError(Exception):
    """Skill 上传业务错误"""


class SkillUploadService:
    """Skill ZIP 上传服务

    编排流程：ZIP 验证/存储 → 解析 SKILL.md → 持久化到数据库
    """

    def __init__(
        self,
        skill_repo: ISkillRepository,
        storage_service: SkillStorageService,
    ) -> None:
        self.skill_repo = skill_repo
        self.storage_service = storage_service

    async def upload(self, zip_bytes: bytes) -> SkillDef:
        """上传 ZIP 创建新 Skill。

        Returns:
            SkillDef: 创建成功的 Skill 实体

        Raises:
            SkillUploadError: 业务错误（ZIP 无效、名称冲突等）
        """
        # 1. 验证并解压 ZIP
        try:
            dir_name, skill_md_content = self.storage_service.save_zip(
                zip_bytes)
        except SkillStorageError as e:
            raise SkillUploadError(str(e))

        # 2. 解析 SKILL.md
        name, description = parse_skill_md(skill_md_content)
        if not name:
            # 清理已解压的文件
            self.storage_service.remove(dir_name)
            raise SkillUploadError(
                "SKILL.md 中未找到有效的标题（# 标题），请检查文件格式"
            )

        # 3. 名称唯一性校验
        existing = await self.skill_repo.get_by_name(name)
        if existing is not None:
            self.storage_service.remove(dir_name)
            raise SkillUploadError(f"Skill 名称 '{name}' 已存在")

        # 4. 构建实体并持久化
        skill = SkillDef(
            id=str(uuid4()),
            name=name,
            description=description,
            content=skill_md_content,
            file_path=dir_name,
            trigger_keywords=[],
            steps=[],
            category="general",
            enabled=True,
            created_at=datetime.now(),
        )

        skill = await self.skill_repo.add(skill)
        return skill

    async def reupload(self, skill_id: str, zip_bytes: bytes) -> SkillDef:
        """重新上传 ZIP 更新已有 Skill。

        Returns:
            SkillDef: 更新后的 Skill 实体

        Raises:
            SkillUploadError: 业务错误
        """
        # 1. 获取已有 Skill
        skill = await self.skill_repo.get_by_id(skill_id)
        if skill is None:
            raise SkillUploadError(f"Skill '{skill_id}' 不存在")

        # 2. 验证并替换文件
        old_dir = skill.file_path
        try:
            new_dir_name, skill_md_content = self.storage_service.replace_zip(
                old_dir, zip_bytes
            )
        except SkillStorageError as e:
            raise SkillUploadError(str(e))

        # 3. 解析 SKILL.md
        name, description = parse_skill_md(skill_md_content)
        if not name:
            self.storage_service.remove(new_dir_name)
            raise SkillUploadError(
                "SKILL.md 中未找到有效的标题（# 标题），请检查文件格式"
            )

        # 4. 名称唯一性校验（如果名称变了）
        if name != skill.name:
            existing = await self.skill_repo.get_by_name(name)
            if existing is not None:
                self.storage_service.remove(new_dir_name)
                raise SkillUploadError(f"Skill 名称 '{name}' 已存在")

        # 5. 更新实体
        skill.name = name
        skill.description = description
        skill.content = skill_md_content
        skill.file_path = new_dir_name
        skill.updated_at = datetime.now()

        skill = await self.skill_repo.update(skill)
        return skill

    async def delete_with_files(self, skill_id: str) -> bool:
        """删除 Skill 及其磁盘文件。

        Returns:
            bool: 是否成功删除
        """
        skill = await self.skill_repo.get_by_id(skill_id)
        if skill is None:
            return False

        # 删除磁盘文件
        if skill.file_path:
            self.storage_service.remove(skill.file_path)

        # 删除数据库记录
        return await self.skill_repo.remove(skill_id)
