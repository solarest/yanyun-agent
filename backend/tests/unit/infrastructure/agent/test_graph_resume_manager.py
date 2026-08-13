import asyncio
import json
from types import SimpleNamespace

import pytest

from src.application.services.session_file_storage import SessionFileStorage
from src.infrastructure.agent.graph_resume_manager import GraphResumeManager


@pytest.mark.asyncio
async def test_checkpoint_resume_rebuilds_runtime_config_and_finalizes_with_runner(tmp_path) -> None:
    """重启后的确认恢复必须通过运行时构建器补全图配置。"""
    task = SimpleNamespace(
        id="task-1",
        session_id="session-1",
        message="continue the task",
    )
    file_storage = SessionFileStorage(base_path=str(tmp_path))
    task_dir = file_storage.create_task_dir(task.session_id, task.id)
    (task_dir / "checkpointer.json").write_text("{}")
    (task_dir / "resume_meta.json").write_text(json.dumps({
        "agent_id": "agent-1",
        "session_id": task.session_id,
        "model": "test-model",
        "workspace": "/tmp/workspace",
        "max_turns": 3,
    }))

    completed = asyncio.Event()

    class FakeGraph:
        async def ainvoke(self, command, config):
            assert command.resume == "allow_once"
            assert config["configurable"]["llm"] == "rebuilt-llm"
            assert config["configurable"]["tool_registry"] == "rebuilt-tools"
            return {"final_result": "done", "error": None}

    class FakeRunner:
        async def build_checkpoint_resume(self, *, task, resume_meta, checkpointer_file, task_dir, send_message_use_case):
            assert resume_meta["agent_id"] == "agent-1"
            assert checkpointer_file.name == "checkpointer.json"
            assert task_dir.name == task.id
            return FakeGraph(), {
                "configurable": {
                    "thread_id": task.id,
                    "llm": "rebuilt-llm",
                    "tool_registry": "rebuilt-tools",
                }
            }

        async def finalize_checkpoint_resume(self, *, task, result, task_dir):
            assert result["final_result"] == "done"
            completed.set()

    class FakeTaskRepository:
        async def get_by_id(self, task_id):
            return task if task_id == task.id else None

    manager = GraphResumeManager()
    started = await manager.resume(
        task.id,
        "allow_once",
        file_storage=file_storage,
        task_repo=FakeTaskRepository(),
        resume_runner=FakeRunner(),
        send_message_use_case=object(),
    )

    assert started is True
    await asyncio.wait_for(completed.wait(), timeout=1)
