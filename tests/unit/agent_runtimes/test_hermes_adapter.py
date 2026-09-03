import asyncio
import sys

import pytest

from backend.agent_runtimes.base import AgentTask
from backend.agent_runtimes.hermes_adapter import HermesRuntimeAdapter

_FAKE_HERMES_HAPPY = r'''
import sys
args = sys.argv
assert "-z" in args
prompt = args[args.index("-z") + 1]
print(f"REPLY_TO: {prompt}")
'''
_FAKE_HERMES_FAIL = r'''
import sys
sys.stderr.write("model provider auth failed\n")
sys.exit(1)
'''
_FAKE_HERMES_SLOW = r'''
import time
time.sleep(30)
'''
_FAKE_HERMES_STDERR_FLOOD = r'''
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
async def test_happy_path_uses_task_provider_and_model(tmp_path):
    script = tmp_path / "fake_hermes.py"
    script.write_text(_FAKE_HERMES_HAPPY, encoding="utf-8")
    events = await _collect(
        HermesRuntimeAdapter(),
        _task(
            provider="openrouter",
            model="anthropic/claude-sonnet",
            config={"binary": sys.executable, "args": [str(script)]},
        ),
    )
    assert [event["type"] for event in events] == ["started", "text", "done"]
    assert "hello" in events[1]["text"]
    assert events[-1]["result"] == {"text": events[1]["text"]}


@pytest.mark.asyncio
async def test_instructions_are_prepended(tmp_path):
    script = tmp_path / "fake_hermes.py"
    script.write_text(_FAKE_HERMES_HAPPY, encoding="utf-8")
    events = await _collect(
        HermesRuntimeAdapter(),
        _task(
            instructions="Follow the contract.",
            input={"message": "do the thing"},
            config={"binary": sys.executable, "args": [str(script)]},
        ),
    )
    assert "Follow the contract." in events[1]["text"]
    assert "do the thing" in events[1]["text"]


@pytest.mark.asyncio
async def test_nonzero_exit_includes_stderr(tmp_path):
    script = tmp_path / "fake_hermes.py"
    script.write_text(_FAKE_HERMES_FAIL, encoding="utf-8")
    events = await _collect(
        HermesRuntimeAdapter(),
        _task(config={"binary": sys.executable, "args": [str(script)]}),
    )
    assert events[0]["type"] == "started"
    assert events[-1]["type"] == "error"
    assert events[-1]["error_type"] == "ProcessExitError"
    assert "model provider auth failed" in events[-1]["message"]


@pytest.mark.asyncio
async def test_stderr_is_drained_concurrently(tmp_path):
    script = tmp_path / "fake_hermes.py"
    script.write_text(_FAKE_HERMES_STDERR_FLOOD, encoding="utf-8")
    events = await _collect(
        HermesRuntimeAdapter(),
        _task(config={"binary": sys.executable, "args": [str(script)]}),
    )
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_timeout_emits_error(tmp_path):
    script = tmp_path / "fake_hermes.py"
    script.write_text(_FAKE_HERMES_SLOW, encoding="utf-8")
    events = await _collect(
        HermesRuntimeAdapter(),
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


def test_validate_config_rejects_bad_values_and_env_types():
    errors = HermesRuntimeAdapter().validate_config(
        {"model": 123, "timeout_seconds": -1, "env": {"TOKEN": 123}}
    )
    assert any("'model' must be a string" in error for error in errors)
    assert any("positive number" in error for error in errors)
    assert any("string keys and values" in error for error in errors)


def test_readiness_uses_configured_binary(monkeypatch):
    monkeypatch.setattr(
        "shutil.which",
        lambda binary: "/resolved/hermes" if binary == "custom" else None,
    )
    readiness = asyncio.run(HermesRuntimeAdapter().readiness({"binary": "custom"}))
    assert readiness.status == "ready"
    assert readiness.binary_present is True


def test_runtime_type_and_capabilities():
    adapter = HermesRuntimeAdapter()
    assert adapter.runtime_type == "hermes"
    assert adapter.capabilities.features == frozenset({"model_selection"})
