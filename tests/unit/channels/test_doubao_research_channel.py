import pytest

from backend.channels.doubao_research_channel import (
    DoubaoResearchChannel,
    _citations,
    _conversation_url,
)
from backend.schemas.source import DataSourceCreate


def test_citations_preserve_order_and_strip_punctuation():
    assert _citations(
        "See https://a.example/x. Again https://a.example/x and https://b.example/y."
    ) == [
        {"url": "https://a.example/x"},
        {"url": "https://b.example/y"},
    ]


def test_conversation_url_extracts_chat_id():
    status = (
        '[{"Status": "Connected", "Url": '
        '"https://www.doubao.com/chat/38436240748612354", "Title": "x"}]'
    )
    assert (
        _conversation_url(status)
        == "https://www.doubao.com/chat/38436240748612354"
    )


def test_conversation_url_ignores_root_chat():
    # A freshly opened /chat page has no conversation id yet — must not be picked up.
    status = (
        '[{"Status": "Connected", "Url": "https://www.doubao.com/chat", "Title": "x"}]'
    )
    assert _conversation_url(status) == ""


def test_conversation_url_tolerates_garbage():
    assert _conversation_url("not json at all") == ""


@pytest.mark.asyncio
async def test_collect_stores_answer_and_citations(monkeypatch):
    async def fake_run(command):
        assert command[1:3] == ["doubao", "ask"]
        assert command[3] == "麻将机"
        return 0, '[{"Role":"assistant","Text":"结论。https://example.com/source"}]', ""

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)
    result = await DoubaoResearchChannel().collect({"question": "麻将机"}, {})

    assert result.success
    assert result.items[0]["title"] == "麻将机"
    assert result.items[0]["citations"] == [{"url": "https://example.com/source"}]
    assert result.metadata["citation_count"] == 1


@pytest.mark.asyncio
async def test_collect_requires_question():
    result = await DoubaoResearchChannel().collect({}, {})
    assert not result.success
    assert "question" in result.error


@pytest.mark.asyncio
async def test_collect_accepts_opencli_yaml_fallback(monkeypatch):
    async def fake_run(command):
        return 0, "- Role: Assistant\n  Text: https://example.com/\n", ""

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)
    result = await DoubaoResearchChannel().collect({"question": "test"}, {})

    assert result.success
    assert result.items[0]["citations"] == [{"url": "https://example.com/"}]


@pytest.mark.asyncio
async def test_collect_captures_conversation_url(monkeypatch):
    calls = []

    async def fake_run(command):
        calls.append(command)
        if command[2] == "ask":
            return 0, '[{"Role":"assistant","Text":"回答"}]', ""
        if command[2] == "status":
            return 0, (
                '[{"Status": "Connected", "Url": '
                '"https://www.doubao.com/chat/12345", "Title": "t"}]'
            ), ""
        return 0, "", ""

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)
    result = await DoubaoResearchChannel().collect({"question": "测试"}, {})

    assert result.success
    assert result.items[0]["conversation_url"] == "https://www.doubao.com/chat/12345"
    # ask + status both hit the adapter
    assert [c[2] for c in calls] == ["ask", "status"]


@pytest.mark.asyncio
async def test_collect_tolerates_status_failure(monkeypatch):
    async def fake_run(command):
        if command[2] == "ask":
            return 0, '[{"Role":"assistant","Text":"回答"}]', ""
        return 1, "", "status exploded"

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)
    result = await DoubaoResearchChannel().collect({"question": "测试"}, {})

    # A failed status must NOT fail the collect — answer is already in hand.
    assert result.success
    assert result.items[0]["conversation_url"] == ""


@pytest.mark.asyncio
async def test_collect_classifies_captcha_block(monkeypatch):
    async def fake_run(command):
        return 1, "", (
            "ok: false\nerror:\n  code: COMMAND_EXEC\n"
            "  message: Doubao blocked the request with a verification challenge\n"
            "  help: 'Detected challenge signal: iframe[src*=\"captcha\"]'"
        )

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)
    result = await DoubaoResearchChannel().collect({"question": "测试"}, {})

    assert not result.success
    assert result.error_type == "captcha_challenge"


@pytest.mark.asyncio
async def test_collect_does_not_classify_generic_error(monkeypatch):
    async def fake_run(command):
        return 1, "", "some unrelated error"

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)
    result = await DoubaoResearchChannel().collect({"question": "测试"}, {})

    assert not result.success
    assert result.error_type is None


def test_source_schema_accepts_doubao_research_channel():
    source = DataSourceCreate(
        name="Doubao research", channel_type="doubao_research", channel_config={"question": "test"}
    )
    assert source.channel_type == "doubao_research"

