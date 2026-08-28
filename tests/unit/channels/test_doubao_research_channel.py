import pytest

from backend.channels.doubao_research_channel import (
    DoubaoResearchChannel,
    _citations,
# merge marker
    _conversation_url,
# merge-base marker
from backend.channels.doubao_research_channel import DoubaoResearchChannel, _citations
# incoming marker
    _structured_response,
# end marker
)
from backend.schemas.source import DataSourceCreate


def test_citations_preserve_order_and_strip_punctuation():
    assert _citations(
        "See https://a.example/x. Again https://a.example/x and https://b.example/y."
    ) == [
        {"url": "https://a.example/x"},
        {"url": "https://b.example/y"},
    ]


# merge marker
def test_conversation_url_extracts_chat_id():
    status = (
        '[{"Status": "Connected", "Url": '
        '"https://www.doubao.com/chat/38436240748612354", "Title": "x"}]'
    )
    assert _conversation_url(status) == "https://www.doubao.com/chat/38436240748612354"


def test_conversation_url_ignores_root_chat():
    # A freshly opened /chat page has no conversation id yet — must not be picked up.
    status = '[{"Status": "Connected", "Url": "https://www.doubao.com/chat", "Title": "x"}]'
    assert _conversation_url(status) == ""


def test_conversation_url_tolerates_garbage():
    assert _conversation_url("not json at all") == ""
# merge-base marker
# incoming marker
def test_structured_response_preserves_share_data_and_keywords():
    response = _structured_response(
        "```json\n"
        '{"answer":"结论", "session_share_data":[{"url":"https://doubao.com/share/1"}], '
        '"suggested_keywords":["DHA 食物"]}\n```'
    )

    assert response["answer"] == "结论"
    assert response["session_share_data"] == [{"url": "https://doubao.com/share/1"}]
    assert response["suggested_keywords"] == ["DHA 食物"]
# end marker


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


@pytest.mark.asyncio
async def test_collect_reads_settled_research_answer(monkeypatch):
    calls = []
    sleeps = []

    async def fake_run(command):
        calls.append(command[2])
        if command[2] == "ask":
            return 0, '[{"Role":"assistant","Text":"正在理解任务要求"}]', ""
        return 0, '[{"Role":"assistant","Text":"最终报告 https://example.com/source"}]', ""

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)
    monkeypatch.setattr("backend.channels.doubao_research_channel.asyncio.sleep", fake_sleep)

    result = await DoubaoResearchChannel().collect(
        {
            "question": "测试",
            "settle_seconds": 35,
            "capture_conversation_url": False,
        },
        {},
    )

    assert result.success
    assert calls == ["ask", "read"]
    assert sleeps == [35]
    assert result.items[0]["content"] == "最终报告 https://example.com/source"
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
            return (
                0,
                (
                    '[{"Status": "Connected", "Url": '
                    '"https://www.doubao.com/chat/12345", "Title": "t"}]'
                ),
                "",
            )
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
        return (
            1,
            "",
            (
                "ok: false\nerror:\n  code: COMMAND_EXEC\n"
                "  message: Doubao blocked the request with a verification challenge\n"
                "  help: 'Detected challenge signal: iframe[src*=\"captcha\"]'"
            ),
        )

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)
    result = await DoubaoResearchChannel().collect({"question": "测试"}, {})

    assert not result.success
    assert result.error_type == "captcha_challenge"


@pytest.mark.asyncio
async def test_collect_classifies_adapter_timeout(monkeypatch):
    async def fake_run(command):
        raise TimeoutError("adapter timed out")

    monkeypatch.setattr(
        "backend.channels.doubao_research_channel._run_doubao_command",
        fake_run,
    )
    result = await DoubaoResearchChannel().collect({"question": "测试"}, {})

    assert not result.success
    assert result.error_type == "TimeoutError"
    assert result.error == "Doubao request timed out"


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
async def test_health_check_accepts_unknown_login_with_authenticated_provider_probe(monkeypatch):
    calls = []

    async def fake_run(command):
        calls.append(command)
        if command[2] == "status":
            return (
                0,
                (
                    '[{"Status":"Connected","Login":"Unknown","Title":"豆包工作 - '
                    '字节跳动旗下 AI 智能助手","Url":"https://www.doubao.com/chat/?from_login=1"}]'
                ),
                "",
            )
        return 0, '[{"Name":"authenticated account","Email":"user@example.com"}]', ""

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)

    assert await DoubaoResearchChannel().health_check({"site_session": "persistent"})
    assert [command[2] for command in calls] == ["status", "whoami"]
    assert all(command[-2:] == ["--site-session", "persistent"] for command in calls)


@pytest.mark.asyncio
async def test_health_check_rejects_explicitly_logged_out_status(monkeypatch):
    async def fake_run(command):
        return 0, '[{"Status":"Connected","Login":"false"}]', ""

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)

    assert not await DoubaoResearchChannel().health_check()


@pytest.mark.asyncio
async def test_health_check_rejects_captcha_status(monkeypatch):
    async def fake_run(command):
        return 1, "", "Doubao blocked the request with a verification challenge"

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)

    assert not await DoubaoResearchChannel().health_check()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        '[{"Status":"Connected","Login":"Unknown","Title":"Other provider","Url":"https://example.com/chat"}]',
        '[{"Status":"Connected","Login":"Unknown","Title":"豆包工作","Url":"https://www.doubao.com/chat/"},'
        '{"Status":"Connected","Login":"Unknown","Title":"豆包工作","Url":"https://www.doubao.com/chat/"}]',
    ],
)
async def test_health_check_rejects_wrong_or_ambiguous_workspace(monkeypatch, status):
    async def fake_run(command):
        return 0, status, ""

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)

    assert not await DoubaoResearchChannel().health_check()


@pytest.mark.asyncio
async def test_health_check_rejects_provider_probe_error(monkeypatch):
    async def fake_run(command):
        if command[2] == "status":
            return (
                0,
                (
                    '[{"Status":"Connected","Login":"Unknown","Title":"豆包工作 - '
                    '字节跳动旗下 AI 智能助手","Url":"https://www.doubao.com/chat/"}]'
                ),
                "",
            )
        return 1, "", "whoami failed"

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)

    assert not await DoubaoResearchChannel().health_check()


@pytest.mark.asyncio
async def test_health_check_preserves_explicit_logged_in_path(monkeypatch):
    calls = []

    async def fake_run(command):
        calls.append(command)
        return 0, '[{"Status":"Connected","Login":"authenticated"}]', ""

    monkeypatch.setattr("backend.channels.doubao_research_channel._run_doubao_command", fake_run)

    assert await DoubaoResearchChannel().health_check()
    assert [command[2] for command in calls] == ["status"]
