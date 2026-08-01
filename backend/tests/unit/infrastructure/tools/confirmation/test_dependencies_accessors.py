"""审批存储单例访问器测试（task 3.3）"""

from src.presentation.dependencies import (
    get_pending_approval_registry,
    get_session_approval_store,
)


def test_pending_approval_registry_is_process_singleton() -> None:
    assert get_pending_approval_registry() is get_pending_approval_registry()


def test_session_approval_store_is_process_singleton() -> None:
    assert get_session_approval_store() is get_session_approval_store()


def test_registry_and_store_are_distinct_singletons() -> None:
    # 访问器各返回各自类型的单例，互不相同
    assert get_pending_approval_registry() is not get_session_approval_store()
