from backend.agent_runtimes.codex_adapter import CodexRuntimeAdapter


def test_codex_json_events_become_closed_runtime_events():
    adapter = CodexRuntimeAdapter()

    call = adapter._translate_event(
        "task-1",
        {
            "type": "item.started",
            "item": {"id": "cmd-1", "type": "command_execution", "command": "python verify.py"},
        },
    )
    result = adapter._translate_event(
        "task-1",
        {
            "type": "item.completed",
            "item": {
                "id": "cmd-1",
                "type": "command_execution",
                "aggregated_output": "",
                "exit_code": 0,
            },
        },
    )
    final_text = adapter._translate_event(
        "task-1",
        {"type": "item.completed", "item": {"type": "agent_message", "text": "{\"tests\": []}"}},
    )

    assert call == {
        "type": "tool_call",
        "task_id": "task-1",
        "name": "command_execution",
        "args": {"command": "python verify.py"},
        "call_id": "cmd-1",
    }
    assert result == {
        "type": "tool_result",
        "task_id": "task-1",
        "name": "command_execution",
        "result": "",
        "call_id": "cmd-1",
        "is_error": False,
    }
    assert final_text == {"type": "text", "task_id": "task-1", "text": "{\"tests\": []}"}


def test_codex_adapter_requires_controller_owned_worktree_config():
    errors = CodexRuntimeAdapter().validate_config({"timeout_seconds": 10})

    assert errors == ["'cwd' must be a non-empty controller-owned worktree path"]
