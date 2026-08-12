from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from backend.workflow.gaojixing_doubao_driver import (
    _BIND_TARGET_TURN_JS,
    _COLLECT_PAGE_JS,
    DoubaoDriverUnavailableError,
    OpenCLIDoubaoEvidenceDriver,
    _brand_observation,
    _page_modules,
)


class _CommandProbe:
    def __init__(self, *, ask_code: int = 0) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.ask_code = ask_code

    async def __call__(self, command: list[str], endpoint: str):
        del endpoint
        self.commands.append(tuple(command))
        action = command[1]
        if action == "new":
            return 0, [], ""
        if action == "ask":
            return self.ask_code, [{"Role": "assistant", "Text": "这是完整回答。"}], "ask failed"
        if action == "status":
            return 0, [{"Url": "https://www.doubao.com/chat/1234567890"}], ""
        raise AssertionError(command)


@asynccontextmanager
async def _endpoint_lease():
    yield "http://agent-1:19222"


def _canonical_capture(question_id: str, question: str, answer: str) -> dict:
    return {
        "id": question_id,
        "question": question,
        "has_brand": question_id.startswith("B"),
        "status": "completed",
        "chat_url": "https://www.doubao.com/chat/1234567890",
        "answer": answer,
        "collected_at": "2026-08-12T16:00:00+08:00",
        "page_modules": {
            "keywords": "页面未显示",
            "ref_links": "页面未显示",
            "product_links": "页面未显示",
            "video_links": "页面未显示",
            "followups": "页面未显示",
        },
        "brand_observation": {
            "target": "高吉星",
            "appeared": False,
            "positions": [],
            "natural_recommendation": False,
            "basis": "页面回答和已显示模块未出现高吉星",
        },
        "page_evidence": {
            "screenshot_files": ["top.png", "answer.png", "bottom.png"],
            "module_expectations": {
                name: {"displayed": False, "expected_count": 0}
                for name in (
                    "keywords",
                    "ref_links",
                    "product_links",
                    "video_links",
                    "followups",
                )
            },
            "screenshot_coverage": {"top": True, "answer": True, "bottom": True},
        },
        "required_missing": [],
    }


@pytest.mark.asyncio
async def test_preflight_is_read_only_and_only_calls_status(tmp_path):
    commands = _CommandProbe()
    driver = OpenCLIDoubaoEvidenceDriver(
        project_root=tmp_path,
        endpoint_lease=_endpoint_lease,
        command_runner=commands,
        page_capture=lambda **_kwargs: None,
    )

    await driver.preflight()

    assert [command[1] for command in commands.commands] == ["status"]


@pytest.mark.asyncio
async def test_collect_runs_new_ask_once_status_then_captures_canonical_evidence(tmp_path):
    commands = _CommandProbe()
    page_calls = []

    async def capture(**kwargs):
        page_calls.append(kwargs)
        return _canonical_capture(kwargs["question_id"], kwargs["question"], kwargs["answer"])

    driver = OpenCLIDoubaoEvidenceDriver(
        project_root=tmp_path,
        endpoint_lease=_endpoint_lease,
        command_runner=commands,
        page_capture=capture,
    )

    result = await driver.collect(question_id="G0001", question="第一道新题")

    assert [command[1] for command in commands.commands] == ["new", "ask", "status"]
    assert sum(command[1] == "ask" for command in commands.commands) == 1
    assert result["id"] == "G0001"
    assert result["question"] == "第一道新题"
    assert result["answer"] == "这是完整回答。"
    assert page_calls[0]["allow_submit"] is False


@pytest.mark.asyncio
async def test_failed_ask_is_never_retried(tmp_path):
    commands = _CommandProbe(ask_code=9)
    driver = OpenCLIDoubaoEvidenceDriver(
        project_root=tmp_path,
        endpoint_lease=_endpoint_lease,
        command_runner=commands,
        page_capture=lambda **_kwargs: None,
    )

    with pytest.raises(DoubaoDriverUnavailableError, match="doubao-ask-failed"):
        await driver.collect(question_id="G0001", question="第一道新题")

    assert sum(command[1] == "ask" for command in commands.commands) == 1
    assert all(command[1] != "status" for command in commands.commands)


@pytest.mark.asyncio
async def test_inspect_current_never_submits_and_returns_none_on_question_mismatch(tmp_path):
    commands = _CommandProbe()

    async def mismatch(**_kwargs):
        return None

    driver = OpenCLIDoubaoEvidenceDriver(
        project_root=tmp_path,
        endpoint_lease=_endpoint_lease,
        command_runner=commands,
        page_capture=mismatch,
    )

    result = await driver.inspect_current(question_id="G0001", question="第一道新题")

    assert result is None
    assert [command[1] for command in commands.commands] == ["status"]


def test_driver_rejects_a_project_root_that_is_not_a_directory(tmp_path):
    missing = Path(tmp_path) / "missing"

    with pytest.raises(DoubaoDriverUnavailableError, match="project-root-unavailable"):
        OpenCLIDoubaoEvidenceDriver(project_root=missing)


def test_page_capture_binds_modules_to_one_exact_conversation_turn():
    assert 'exact(item.text) === exact(question)' in _BIND_TARGET_TURN_JS
    assert "matches.length !== 1" in _BIND_TARGET_TURN_JS
    assert "data-gjx-target-assistant" in _BIND_TARGET_TURN_JS
    assert 'document.body && document.body.innerText' not in _COLLECT_PAGE_JS
    assert 'data-gjx-target-assistant' in _COLLECT_PAGE_JS


def test_page_modules_fail_closed_when_declared_reference_count_is_incomplete():
    modules, expectations, missing = _page_modules(
        {
            "reference_signal": {"keyword_count": 1, "reference_count": 2},
            "keywords": ["维生素"],
            "source_links": [{"title": "一", "url": "https://example.com/1"}],
            "product_links": [],
            "video_cards": [],
            "followups": [],
            "source_block_count": 1,
            "product_module_count": 0,
        },
        [],
    )

    assert modules["ref_links"] == [{"title": "一", "url": "https://example.com/1"}]
    assert expectations["ref_links"]["expected_count"] == 2
    assert "reference-count-mismatch" in missing


def test_negative_brand_context_is_not_classified_as_natural_recommendation():
    observation = _brand_observation(
        "孕妇营养品怎么选？",
        "不推荐高吉星用于这个场景，应该先咨询医生。",
        {
            "keywords": "页面未显示",
            "ref_links": "页面未显示",
            "product_links": "页面未显示",
            "video_links": "页面未显示",
            "followups": "页面未显示",
        },
    )

    assert observation["appeared"] is True
    assert observation["natural_recommendation"] is False
