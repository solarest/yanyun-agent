"""表现层 - Memory API 路由"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.memory.dto import (
    MemoryCreateDTO,
    MemoryListResponseDTO,
    MemoryResponseDTO,
    MemorySearchRequestDTO,
    MemorySearchResponseDTO,
    MemoryUpdateDTO,
)
from src.application.memory.management import MemoryManagementUseCase
from src.domain.memory.entity import MemoryEntry
from src.domain.memory.query import MemorySearchResult
from src.presentation.dependencies import get_memory_use_case

router = APIRouter(prefix="/api/agents/{agent_id}/memories", tags=["memory"])


def _to_response(entry: MemoryEntry) -> MemoryResponseDTO:
    """领域实体 → 响应 DTO"""
    return MemoryResponseDTO(
        id=entry.id,
        agent_id=entry.agent_id,
        content=entry.content,
        category=entry.category.value,
        tags=entry.tags,
        importance=entry.importance,
        source_session_id=entry.source_session_id,
        access_count=entry.access_count,
        last_accessed_at=entry.last_accessed_at.isoformat()
        if entry.last_accessed_at else None,
        created_at=entry.created_at.isoformat()
        if entry.created_at else "",
        updated_at=entry.updated_at.isoformat()
        if entry.updated_at else None,
    )


def _to_search_response(result: MemorySearchResult) -> MemorySearchResponseDTO:
    """搜索结果 → 响应 DTO"""
    entry = result.entry
    return MemorySearchResponseDTO(
        id=entry.id,
        agent_id=entry.agent_id,
        content=entry.content,
        category=entry.category.value,
        tags=entry.tags,
        importance=entry.importance,
        score=round(result.score, 4),
        created_at=entry.created_at.isoformat()
        if entry.created_at else "",
    )


@router.post(
    "",
    response_model=MemoryResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="创建记忆",
)
async def create_memory(
    agent_id: str,
    body: MemoryCreateDTO,
    use_case: MemoryManagementUseCase = Depends(get_memory_use_case),
) -> MemoryResponseDTO:
    """为指定 Agent 创建一条新记忆"""
    entry = await use_case.add_memory(
        agent_id=agent_id,
        content=body.content,
        category=body.category,
        tags=body.tags,
        importance=body.importance,
        source_session_id=body.source_session_id,
    )
    return _to_response(entry)


@router.get(
    "",
    response_model=MemoryListResponseDTO,
    summary="获取记忆列表",
)
async def list_memories(
    agent_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    use_case: MemoryManagementUseCase = Depends(get_memory_use_case),
) -> MemoryListResponseDTO:
    """获取指定 Agent 的记忆列表（分页）"""
    entries, total = await use_case.list_memories(
        agent_id=agent_id,
        page=page,
        page_size=page_size,
    )
    return MemoryListResponseDTO(
        data=[_to_response(e) for e in entries],
        total=total,
    )


@router.post(
    "/search",
    response_model=list[MemorySearchResponseDTO],
    summary="搜索记忆",
)
async def search_memories(
    agent_id: str,
    body: MemorySearchRequestDTO,
    use_case: MemoryManagementUseCase = Depends(get_memory_use_case),
) -> list[MemorySearchResponseDTO]:
    """搜索 Agent 的记忆（文本匹配 + 筛选）"""
    results = await use_case.search_memories(
        agent_id=agent_id,
        query=body.query,
        category=body.category,
        tags=body.tags,
        min_importance=body.min_importance,
        limit=body.limit,
    )
    return [_to_search_response(r) for r in results]


@router.get(
    "/{memory_id}",
    response_model=MemoryResponseDTO,
    summary="获取记忆详情",
)
async def get_memory(
    agent_id: str,
    memory_id: str,
    use_case: MemoryManagementUseCase = Depends(get_memory_use_case),
) -> MemoryResponseDTO:
    """获取单条记忆详情"""
    entry = await use_case.get_memory(memory_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "MEMORY_NOT_FOUND",
                    "message": f"Memory '{memory_id}' not found",
                }
            },
        )
    return _to_response(entry)


@router.put(
    "/{memory_id}",
    response_model=MemoryResponseDTO,
    summary="更新记忆",
)
async def update_memory(
    agent_id: str,
    memory_id: str,
    body: MemoryUpdateDTO,
    use_case: MemoryManagementUseCase = Depends(get_memory_use_case),
) -> MemoryResponseDTO:
    """更新记忆内容和属性"""
    entry = await use_case.update_memory(
        memory_id=memory_id,
        content=body.content,
        category=body.category,
        tags=body.tags,
        importance=body.importance,
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "MEMORY_NOT_FOUND",
                    "message": f"Memory '{memory_id}' not found",
                }
            },
        )
    return _to_response(entry)


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除记忆",
)
async def delete_memory(
    agent_id: str,
    memory_id: str,
    use_case: MemoryManagementUseCase = Depends(get_memory_use_case),
) -> None:
    """删除单条记忆"""
    deleted = await use_case.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "MEMORY_NOT_FOUND",
                    "message": f"Memory '{memory_id}' not found",
                }
            },
        )
