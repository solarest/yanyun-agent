"""应用层 - Agent DTO 单元测试"""

import pytest
from pydantic import ValidationError

from src.application.dtos.agent_dto import (
    CreateAgentDTO,
    UpdateAgentDTO,
    UpdateAgentConfigDTO,
    AgentResponseDTO,
    AgentConfigResponseDTO,
)


class TestCreateAgentDTO:
    """CreateAgentDTO 验证测试"""

    def test_valid_minimal(self) -> None:
        dto = CreateAgentDTO(name="Test Agent")
        assert dto.name == "Test Agent"
        assert dto.description == ""
        assert dto.vibes == []
        assert dto.identity_md is None

    def test_valid_full(self) -> None:
        dto = CreateAgentDTO(
            name="Agent",
            description="A test agent",
            avatar_style="robot",
            avatar_id="rob_01",
            vibes=["Professional", "Friendly"],
            identity_md="# Identity",
        )
        assert dto.vibes == ["Professional", "Friendly"]
        assert dto.identity_md == "# Identity"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateAgentDTO(name="")

    def test_name_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateAgentDTO(name="x" * 101)

    def test_description_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateAgentDTO(name="ok", description="x" * 501)

    def test_vibes_max_three(self) -> None:
        with pytest.raises(ValidationError, match="最多只能选择 3 个"):
            CreateAgentDTO(name="ok", vibes=["A", "B", "C", "D"])

    def test_config_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CreateAgentDTO(name="ok", identity_md="x" * 50001)

    def test_config_at_max_length_ok(self) -> None:
        dto = CreateAgentDTO(name="ok", identity_md="x" * 50000)
        assert len(dto.identity_md) == 50000  # type: ignore[arg-type]


class TestUpdateAgentDTO:
    """UpdateAgentDTO 验证测试"""

    def test_all_none(self) -> None:
        dto = UpdateAgentDTO()
        assert dto.name is None
        assert dto.description is None

    def test_partial_update(self) -> None:
        dto = UpdateAgentDTO(name="New Name")
        assert dto.name == "New Name"
        assert dto.description is None

    def test_vibes_too_many(self) -> None:
        with pytest.raises(ValidationError, match="最多只能选择 3 个"):
            UpdateAgentDTO(vibes=["A", "B", "C", "D"])


class TestUpdateAgentConfigDTO:
    """UpdateAgentConfigDTO 验证测试"""

    def test_valid_single_field(self) -> None:
        dto = UpdateAgentConfigDTO(identity_md="new identity")
        assert dto.identity_md == "new identity"
        assert dto.soul_md is None

    def test_all_none_rejected(self) -> None:
        with pytest.raises(ValidationError, match="至少需要提供一个"):
            UpdateAgentConfigDTO()

    def test_config_too_long(self) -> None:
        with pytest.raises(ValidationError):
            UpdateAgentConfigDTO(soul_md="x" * 50001)

    def test_multiple_fields(self) -> None:
        dto = UpdateAgentConfigDTO(
            identity_md="id", soul_md="soul", bootstrap_md="boot"
        )
        assert dto.identity_md == "id"
        assert dto.soul_md == "soul"
        assert dto.bootstrap_md == "boot"


class TestAgentResponseDTO:
    """AgentResponseDTO 序列化测试"""

    def test_serialization(self) -> None:
        dto = AgentResponseDTO(
            id="abc",
            name="Test",
            description="desc",
            avatar_style="pixel_art",
            avatar_id="px_01",
            vibes=["Professional"],
            identity_md="",
            soul_md="",
            agents_md="",
            bootstrap_md="",
            memory_md="",
            tools_md="",
            user_md="",
            config_version=1,
            created_at="2024-01-01T00:00:00",
            updated_at=None,
        )
        data = dto.model_dump()
        assert data["id"] == "abc"
        assert data["vibes"] == ["Professional"]
        assert data["updated_at"] is None


class TestAgentConfigResponseDTO:
    """AgentConfigResponseDTO 序列化测试"""

    def test_serialization(self) -> None:
        dto = AgentConfigResponseDTO(
            identity_md="id",
            soul_md="soul",
            agents_md="agents",
            bootstrap_md="boot",
            memory_md="",
            tools_md="tools",
            user_md="user",
            config_version=3,
        )
        data = dto.model_dump()
        assert data["config_version"] == 3
        assert data["memory_md"] == ""
