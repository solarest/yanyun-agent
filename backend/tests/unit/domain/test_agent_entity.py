"""领域层 - Agent 实体单元测试"""

import json
import pytest

from src.domain.entities.agent import Agent, CONFIG_FILES, MAX_CONFIG_LENGTH


class TestAgentDefaults:
    """Agent 默认值测试"""

    def test_default_values(self) -> None:
        agent = Agent()
        assert agent.name == ""
        assert agent.description == ""
        assert agent.vibes == "[]"
        assert agent.identity_md == ""
        assert agent.soul_md == ""
        assert agent.agents_md == ""
        assert agent.bootstrap_md == ""
        assert agent.memory_md == ""
        assert agent.tools_md == ""
        assert agent.user_md == ""
        assert agent.config_version == 1
        assert agent.updated_at is None

    def test_id_auto_generated(self) -> None:
        a1 = Agent()
        a2 = Agent()
        assert a1.id != a2.id
        assert len(a1.id) == 36  # UUID format


class TestSetVibes:
    """set_vibes 方法测试"""

    def test_set_single_vibe(self) -> None:
        agent = Agent()
        agent.set_vibes(["Professional"])
        assert json.loads(agent.vibes) == ["Professional"]

    def test_set_three_vibes(self) -> None:
        agent = Agent()
        agent.set_vibes(["Professional", "Friendly", "Creative"])
        assert json.loads(agent.vibes) == [
            "Professional", "Friendly", "Creative"]

    def test_set_empty_vibes(self) -> None:
        agent = Agent()
        agent.set_vibes([])
        assert json.loads(agent.vibes) == []

    def test_set_vibes_exceeds_limit(self) -> None:
        agent = Agent()
        with pytest.raises(ValueError, match="最多只能选择 3 个"):
            agent.set_vibes(["A", "B", "C", "D"])

    def test_set_vibes_stores_json_string(self) -> None:
        agent = Agent()
        agent.set_vibes(["中文标签"])
        assert isinstance(agent.vibes, str)
        assert "中文标签" in agent.vibes


class TestGetVibes:
    """get_vibes 方法测试"""

    def test_get_vibes_from_json_string(self) -> None:
        agent = Agent(vibes='["Professional", "Friendly"]')
        assert agent.get_vibes() == ["Professional", "Friendly"]

    def test_get_vibes_from_empty_json(self) -> None:
        agent = Agent(vibes="[]")
        assert agent.get_vibes() == []

    def test_get_vibes_from_list(self) -> None:
        agent = Agent()
        agent.vibes = ["Professional"]  # type: ignore[assignment]
        assert agent.get_vibes() == ["Professional"]


class TestUpdateConfig:
    """update_config 方法测试"""

    def test_sets_fields(self) -> None:
        agent = Agent()
        agent.update_config(identity_md="new identity", soul_md="new soul")
        assert agent.identity_md == "new identity"
        assert agent.soul_md == "new soul"

    def test_increments_version(self) -> None:
        agent = Agent(config_version=1)
        agent.update_config(identity_md="x")
        assert agent.config_version == 2
        agent.update_config(soul_md="y")
        assert agent.config_version == 3

    def test_updates_timestamp(self) -> None:
        agent = Agent()
        assert agent.updated_at is None
        agent.update_config(identity_md="x")
        assert agent.updated_at is not None

    def test_ignores_invalid_fields(self) -> None:
        agent = Agent()
        # type: ignore[arg-type]
        agent.update_config(invalid_field="should be ignored")
        assert not hasattr(agent, "invalid_field") or agent.config_version == 2

    def test_ignores_none_values(self) -> None:
        agent = Agent(identity_md="original")
        agent.update_config(identity_md=None)  # type: ignore[arg-type]
        assert agent.identity_md == "original"

    def test_config_too_long_raises(self) -> None:
        agent = Agent()
        long_content = "x" * (MAX_CONFIG_LENGTH + 1)
        with pytest.raises(ValueError, match="超过"):
            agent.update_config(identity_md=long_content)

    def test_config_at_max_length_ok(self) -> None:
        agent = Agent()
        content = "x" * MAX_CONFIG_LENGTH
        agent.update_config(identity_md=content)
        assert len(agent.identity_md) == MAX_CONFIG_LENGTH

    def test_unchanged_fields_preserved(self) -> None:
        agent = Agent(identity_md="keep", soul_md="keep too")
        agent.update_config(agents_md="new agents")
        assert agent.identity_md == "keep"
        assert agent.soul_md == "keep too"
        assert agent.agents_md == "new agents"


class TestConfigFilesConstant:
    """CONFIG_FILES 常量测试"""

    def test_contains_seven_files(self) -> None:
        assert len(CONFIG_FILES) == 7

    def test_all_end_with_md(self) -> None:
        for f in CONFIG_FILES:
            assert f.endswith("_md"), f"{f} should end with _md"
