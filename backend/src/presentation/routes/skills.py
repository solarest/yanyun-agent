"""表现层 - Skills API 路由（ZIP 上传模式）"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status

from src.application.dtos.skill_dto import (
    SkillListResponseDTO,
    SkillResponseDTO,
    SkillStepDTO,
)
from src.application.use_cases.skill_upload import SkillUploadError, SkillUploadService
from src.domain.entities.skill_def import SkillDef
from src.domain.repositories.skill_repository import ISkillRepository
from src.presentation.dependencies import (
    get_skill_repository,
    get_skill_upload_service,
)

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _to_response(skill: SkillDef) -> SkillResponseDTO:
    """领域实体 → 响应 DTO"""
    return SkillResponseDTO(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        content=skill.content,
        file_path=skill.file_path,
        trigger_keywords=skill.trigger_keywords,
        steps=[
            SkillStepDTO(
                name=s.name,
                description=s.description,
                tool_name=s.tool_name,
            )
            for s in skill.steps
        ],
        category=skill.category,
        enabled=skill.enabled,
        created_at=skill.created_at.isoformat() if skill.created_at else "",
        updated_at=skill.updated_at.isoformat() if skill.updated_at else None,
    )


@router.post(
    "/upload",
    response_model=SkillResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="上传 ZIP 创建 Skill",
)
async def upload_skill(
    file: UploadFile = File(..., description="Skill ZIP 文件"),
    upload_service: SkillUploadService = Depends(get_skill_upload_service),
) -> SkillResponseDTO:
    """上传 ZIP 文件创建新 Skill。

    ZIP 根目录必须包含 SKILL.md，其中第一个 # 标题作为名称，
    第一段文本作为描述。
    """
    # 验证文件类型
    if file.content_type and file.content_type not in (
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_FILE_TYPE", "message": "请上传 ZIP 文件"}},
        )

    zip_bytes = await file.read()
    try:
        skill = await upload_service.upload(zip_bytes)
    except SkillUploadError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "UPLOAD_FAILED", "message": str(e)}},
        )

    return _to_response(skill)


@router.put(
    "/{skill_id}/upload",
    response_model=SkillResponseDTO,
    summary="重新上传 ZIP 更新 Skill",
)
async def reupload_skill(
    skill_id: str,
    file: UploadFile = File(..., description="新的 Skill ZIP 文件"),
    upload_service: SkillUploadService = Depends(get_skill_upload_service),
) -> SkillResponseDTO:
    """重新上传 ZIP 更新已有 Skill 的内容和文件。"""
    zip_bytes = await file.read()
    try:
        skill = await upload_service.reupload(skill_id, zip_bytes)
    except SkillUploadError as e:
        status_code = status.HTTP_400_BAD_REQUEST
        if "不存在" in str(e):
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(
            status_code=status_code,
            detail={"error": {"code": "UPLOAD_FAILED", "message": str(e)}},
        )

    return _to_response(skill)


@router.get(
    "",
    response_model=SkillListResponseDTO,
    summary="获取 Skill 列表",
)
async def list_skills(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str = Query(None, description="按分类筛选"),
    enabled: bool = Query(None, description="按启用状态筛选"),
    skill_repo: ISkillRepository = Depends(get_skill_repository),
) -> SkillListResponseDTO:
    """获取 Skill 列表（分页 + 筛选）"""
    offset = (page - 1) * page_size
    skills, total = await skill_repo.list_all(
        limit=page_size,
        offset=offset,
        category=category,
        enabled=enabled,
    )
    return SkillListResponseDTO(
        data=[_to_response(s) for s in skills],
        total=total,
    )


@router.get(
    "/enabled",
    response_model=SkillListResponseDTO,
    summary="获取所有启用的 Skills",
)
async def list_enabled_skills(
    skill_repo: ISkillRepository = Depends(get_skill_repository),
) -> SkillListResponseDTO:
    """获取所有启用的 Skills（对话选择用）"""
    skills = await skill_repo.get_enabled()
    return SkillListResponseDTO(
        data=[_to_response(s) for s in skills],
        total=len(skills),
    )


@router.get(
    "/{skill_id}",
    response_model=SkillResponseDTO,
    summary="获取 Skill 详情",
)
async def get_skill(
    skill_id: str,
    skill_repo: ISkillRepository = Depends(get_skill_repository),
) -> SkillResponseDTO:
    """获取 Skill 详情"""
    skill = await skill_repo.get_by_id(skill_id)
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "SKILL_NOT_FOUND", "message": f"Skill '{skill_id}' 不存在"}},
        )
    return _to_response(skill)


@router.delete(
    "/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除 Skill",
)
async def delete_skill(
    skill_id: str,
    upload_service: SkillUploadService = Depends(get_skill_upload_service),
) -> None:
    """删除 Skill 及其磁盘文件"""
    deleted = await upload_service.delete_with_files(skill_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "SKILL_NOT_FOUND", "message": f"Skill '{skill_id}' 不存在"}},
        )


@router.patch(
    "/{skill_id}/toggle",
    response_model=SkillResponseDTO,
    summary="切换 Skill 启用状态",
)
async def toggle_skill(
    skill_id: str,
    skill_repo: ISkillRepository = Depends(get_skill_repository),
) -> SkillResponseDTO:
    """切换 Skill 启用/禁用状态"""
    skill = await skill_repo.get_by_id(skill_id)
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "SKILL_NOT_FOUND", "message": f"Skill '{skill_id}' 不存在"}},
        )

    skill.toggle_enabled()
    skill = await skill_repo.update(skill)
    return _to_response(skill)
