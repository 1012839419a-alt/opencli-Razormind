import pytest

from backend.channels.doubao_research_channel import (
    DoubaoResearchChannel,
    _citations,
    _conversation_url,
    _run_doubao_command,
    _structured_response,
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
    assert _conversation_url(status) == "https://www.doubao.com/chat/38436240748612354"


def test_conversation_url_ignores_root_chat():
    status = (
        '[{"Status": "Connected", "Url": "https://www.doubao.com/chat", "Title": "x"}]'
    )
    assert _conversation_url(status) == ""


def test_conversation_url_tolerates_garbage():
    assert _conversation_url("not json at all") == ""


def test_structured_response_preserves_share_data_and_keywords():
    response = _structured_response(
        "```json\n"
        '{"answer":"结论", "session_share_data":[{"url":"https://doubao.com/share/1"}], '
        '"suggested_keywords":["DHA 食物"]}\n```'
    )

    assert response["answer"] == "结论"
    assert response["session_share_data"] == [{"url": "https://doubao.com/share/1"}]
    assert response["suggested_keywords"] == ["DHA 食物"]


def test_structured_response_preserves_data_and_links():
    response = _structured_response(
        '{"answer":"结论", "data":{"items":["一","二"]}, '
        '"links":[{"title":"来源","url":"https://example.com/source"}], '
        '"session_share_data":[], "suggested_keywords":[]}'
    )

    assert response["data"] == {"items": ["一", "二"]}
    assert response["links"] == [{"title": "来源", "url": "https://example.com/source"}]
    assert response["response_data"]["data"] == {"items": ["一", "二"]}


def test_structured_response_accepts_doubao_suggested_keys_alias():
    response = _structured_response(
        '{"answer":"结论", "session_share_data":"", '
        '"suggested_keys":["深海鱼", "DHA 鸡蛋"], "citations":[]}'
    )

    assert response["suggested_keywords"] == ["深海鱼", "DHA 鸡蛋"]


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
async def test_collect_stores_structured_share_data_and_suggested_keywords(monkeypatch):
    async def fake_run(command):
        return (
            0,
            "[{\"Role\":\"assistant\",\"Text\":"
            '"{\\"answer\\":\\"研究结论\\",'
            '\\"session_share_data\\":[{\\"url\\":\\"https://doubao.com/share/1\\"}],'
            '\\"suggested_keywords\\":[\\"DHA 食物\\"]}"}]',
            "",
        )

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)
    result = await DoubaoResearchChannel().collect({"question": "推荐追问"}, {})

    assert result.success
    assert result.items[0]["content"] == "研究结论"
    assert result.items[0]["data"] == []
    assert result.items[0]["links"] == [{"url": "https://doubao.com/share/1"}]
    assert result.items[0]["response_data"]["answer"] == "研究结论"
    assert result.items[0]["session_share_data"] == [{"url": "https://doubao.com/share/1"}]
    assert result.items[0]["suggested_keywords"] == ["DHA 食物"]
    assert result.items[0]["citations"] == [{"url": "https://doubao.com/share/1"}]


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
    assert [command[2] for command in calls] == ["ask", "status"]


@pytest.mark.asyncio
async def test_collect_tolerates_status_failure(monkeypatch):
    async def fake_run(command):
        if command[2] == "ask":
            return 0, '[{"Role":"assistant","Text":"回答"}]', ""
        return 1, "", "status exploded"

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)
    result = await DoubaoResearchChannel().collect({"question": "测试"}, {})

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


@pytest.mark.asyncio
async def test_doubao_command_uses_host_bridge_when_configured(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"returncode": 0, "stdout": "logged_in: true", "stderr": ""}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, **kwargs):
            assert url.endswith("/doubao")
            assert kwargs["json"] == {"command": "status", "args": []}
            return FakeResponse()

    monkeypatch.setattr(
        "backend.channels.doubao_research_channel.httpx.AsyncClient",
        lambda **_: FakeClient(),
    )
    monkeypatch.setenv("DOUBAO_CLI_BRIDGE_URL", "http://host.docker.internal:18765/doubao")
    monkeypatch.setenv("DOUBAO_CLI_BRIDGE_TOKEN", "bridge-token")

    result = await _run_doubao_command(["opencli", "doubao", "status"])

    assert result == (0, "logged_in: true", "")
