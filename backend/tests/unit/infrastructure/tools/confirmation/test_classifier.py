"""CommandClassifier 单元测试（task 1.2 / 1.3）"""

from src.infrastructure.tools.confirmation.classifier import (
    ClassificationResult,
    CommandClassifier,
)
from src.infrastructure.tools.confirmation.config import (
    DangerousCommandEntry,
    DangerousCommandSet,
    load_dangerous_commands,
)


def _default_classifier() -> CommandClassifier:
    return CommandClassifier(load_dangerous_commands())


class TestCommandClassifier:
    def test_dangerous_token_rm_rf_triggers(self) -> None:
        r = _default_classifier().classify("rm -rf /tmp/build")
        assert r.needs_confirmation is True
        assert r.category == "rm-recursive"
        assert isinstance(r, ClassificationResult)

    def test_sudo_triggers(self) -> None:
        r = _default_classifier().classify("sudo apt update")
        assert r.needs_confirmation is True
        assert r.category == "sudo"

    def test_redirect_triggers(self) -> None:
        r = _default_classifier().classify("echo hi > /etc/passwd")
        assert r.needs_confirmation is True
        assert r.category == "redirect-overwrite"

    def test_safe_command_no_confirmation(self) -> None:
        r = _default_classifier().classify("ls -la")
        assert r.needs_confirmation is False
        assert r.category == ""
        assert r.risk_reason == ""

    def test_compound_shell_scans_all_segments(self) -> None:
        r = _default_classifier().classify("ls && rm -rf build")
        assert r.needs_confirmation is True
        assert r.category == "rm-recursive"

    def test_config_driven_set_change(self) -> None:
        custom = DangerousCommandSet(
            entries=(
                DangerousCommandEntry(
                    pattern=r"git push --force",
                    category="git-force",
                    reason="强推",
                ),
            )
        )
        clf = CommandClassifier(custom)
        # 自定义集合命中
        assert clf.classify("git push --force origin main").needs_confirmation is True
        # 默认集合会命中、但自定义集合未收录的命令 → 安全
        assert clf.classify("rm -rf build").needs_confirmation is False
