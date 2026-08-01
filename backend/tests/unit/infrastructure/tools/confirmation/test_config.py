"""危险命令集合配置加载测试（task 1.1）"""

from src.infrastructure.tools.confirmation.config import (
    DangerousCommandEntry,
    DangerousCommandSet,
    load_dangerous_commands,
)


class TestLoadDangerousCommands:
    def test_default_set_has_expected_categories(self) -> None:
        s = load_dangerous_commands()
        cats = {e.category for e in s.entries}
        assert "rm-recursive" in cats
        assert "sudo" in cats
        assert "redirect-overwrite" in cats
        assert "mkfs" in cats
        assert "dd-write" in cats
        assert "chmod-recursive" in cats
        assert "remote-pipe-shell" in cats
        assert "fork-bomb" in cats

    def test_default_entries_carry_pattern_and_reason(self) -> None:
        s = load_dangerous_commands()
        for e in s.entries:
            assert e.pattern, f"empty pattern for {e.category}"
            assert e.reason, f"empty reason for {e.category}"

    def test_entries_are_compilable_regex(self) -> None:
        import re

        s = load_dangerous_commands()
        for e in s.entries:
            re.compile(e.pattern)  # 不抛异常即可

    def test_load_from_custom_path(self, tmp_path) -> None:
        f = tmp_path / "custom.json"
        f.write_text(
            '{"dangerous_commands": ['
            '{"pattern": "git push --force", "category": "git-force", "reason": "强推"}'
            "]}",
            encoding="utf-8",
        )
        s = load_dangerous_commands(str(f))
        assert len(s.entries) == 1
        assert isinstance(s.entries[0], DangerousCommandEntry)
        assert s.entries[0].category == "git-force"
        assert isinstance(s, DangerousCommandSet)
