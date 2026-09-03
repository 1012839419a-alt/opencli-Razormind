import asyncio
import sys

import pytest

from backend.agent_runtimes.base import AgentTask
from backend.agent_runtimes.openclaw_adapter import (
    OpenClawRuntimeAdapter,
    _extract_reply_text,
)

_FAKE_OPENCLAW_JSON = r'''
import json
import sys
args = sys.argv
assert "--agent" in args
assert "--json" in args
message = args[args.index("-m") + 1]
print("[openclaw] startup notice")
print(json.dumps({"text": f"ECHO: {message}", "run_id": "r1"}))
'''
_FAKE_OPENCLAW_NESTED = r'''
import json
print(json.dumps({"response": {"content": "nested reply"}}))
'''
_FAKE_OPENCLAW_NON_JSON = r'''
print("plain diagnostic output, no json at all")
'''
_FAKE_OPENCLAW_FAIL = r'''
import sys
sys.stderr.write("billing error: no valid subscription\n")
sys.exit(1)
'''
_FAKE_OPENCLAW_SLOW = r'''
import time
time.sleep(30)
'''
_FAKE_OPENCLAW_STDERR_FLOOD = r'''
import sys
sys.stderr.write("x" * (1024 * 1024 * 2))
print("done")
'''


def _task(**overrides) -> AgentTask:
    value = dict(
        task_id="t1",
        workflow="default",
        input={"message": "hello"},
        config={},
    )
    value.update(overrides)
    return AgentTask(**value)


async def _collect(adapter, task):
    return [event async for event in adapter.invoke(task)]


@pytest.mark.asyncio
async def test_json_reply_and_task_model_provider(tmp_path):
    script = tmp_path / "fake_openclaw.py"
    script.write_text(_FAKE_OPENCLAW_JSON, encoding="utf-8")
    events = await _collect(
        OpenClawRuntimeAdapter(),
        _task(
            provider="openrouter",
            model="claude-sonnet",
            config={"binary": sys.executable, "args": [str(script)]},
        ),
    )
    assert [event["type"] for event in events] == ["started", "text", "done"]
    assert "ECHO: hello" in events[1]["text"]
    assert events[-1]["result"] == {"text": events[1]["text"]}


@pytest.mark.asyncio
async def test_nested_json_reply_is_extracted(tmp_path):
    script = tmp_path / "fake_openclaw.py"
    script.write_text(_FAKE_OPENCLAW_NESTED, encoding="utf-8")
    events = await _collect(
        OpenClawRuntimeAdapter(),
        _task(config={"binary": sys.executable, "args": [str(script)]}),
    )
    assert events[-1]["result"] == {"text": "nested reply"}


@pytest.mark.asyncio
async def test_non_json_stdout_falls_back_to_text(tmp_path):
    script = tmp_path / "fake_openclaw.py"
    script.write_text(_FAKE_OPENCLAW_NON_JSON, encoding="utf-8")
    events = await _collect(
        OpenClawRuntimeAdapter(),
        _task(config={"binary": sys.executable, "args": [str(script)]}),
    )
    assert "plain diagnostic output" in events[-1]["result"]["text"]


@pytest.mark.asyncio
async def test_nonzero_exit_includes_stderr(tmp_path):
    script = tmp_path / "fake_openclaw.py"
    script.write_text(_FAKE_OPENCLAW_FAIL, encoding="utf-8")
    events = await _collect(
        OpenClawRuntimeAdapter(),
        _task(config={"binary": sys.executable, "args": [str(script)]}),
    )
    assert events[0]["type"] == "started"
    assert events[-1]["error_type"] == "ProcessExitError"
    assert "billing error" in events[-1]["message"]


@pytest.mark.asyncio
async def test_stderr_is_drained_concurrently(tmp_path):
    script = tmp_path / "fake_openclaw.py"
    script.write_text(_FAKE_OPENCLAW_STDERR_FLOOD, encoding="utf-8")
    events = await _collect(
        OpenClawRuntimeAdapter(),
        _task(config={"binary": sys.executable, "args": [str(script)]}),
    )
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_timeout_emits_error(tmp_path):
    script = tmp_path / "fake_openclaw.py"
    script.write_text(_FAKE_OPENCLAW_SLOW, encoding="utf-8")
    events = await _collect(
        OpenClawRuntimeAdapter(),
        _task(
            config={
                "binary": sys.executable,
                "args": [str(script)],
                "timeout_seconds": 1,
            }
        ),
    )
    assert events[-1]["type"] == "error"
    assert events[-1]["error_type"] == "TimeoutError"


def test_extract_reply_text_probing():
    assert _extract_reply_text("plain") == "plain"
    assert _extract_reply_text({"text": "hi"}) == "hi"
    assert _extract_reply_text({"response": {"content": "nested"}}) == "nested"
    assert _extract_reply_text({"run_id": "r1"}) is None
    assert _extract_reply_text(["not", "a", "dict"]) is None


def test_validate_config_rejects_bad_values_and_env_types():
    errors = OpenClawRuntimeAdapter().validate_config(
        {"local": "yes", "timeout_seconds": 0, "env": {"TOKEN": 123}}
    )
    assert any("'local' must be a boolean" in error for error in errors)
    assert any("positive number" in error for error in errors)
    assert any("string keys and values" in error for error in errors)


def test_readiness_uses_configured_binary(monkeypatch):
    monkeypatch.setattr(
        "shutil.which",
        lambda binary: "/resolved/openclaw" if binary == "custom" else None,
    )
    readiness = asyncio.run(OpenClawRuntimeAdapter().readiness({"binary": "custom"}))
    assert readiness.status == "ready"
    assert readiness.binary_present is True


def test_runtime_type_and_capabilities():
    adapter = OpenClawRuntimeAdapter()
    assert adapter.runtime_type == "openclaw"
    assert adapter.capabilities.features == frozenset({"model_selection"})
