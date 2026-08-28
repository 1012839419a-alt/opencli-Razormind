import pytest

from backend.channels.doubao_research_channel import (
    DoubaoResearchChannel,
    _citations,
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


def test_structured_response_preserves_share_data_and_keywords():
    response = _structured_response(
        "```json\n"
        '{"answer":"结论", "session_share_data":[{"url":"https://doubao.com/share/1"}], '
        '"suggested_keywords":["DHA 食物"]}\n```'
    )

    assert response["answer"] == "结论"
    assert response["session_share_data"] == [{"url": "https://doubao.com/share/1"}]
    assert response["suggested_keywords"] == ["DHA 食物"]


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


def test_source_schema_accepts_doubao_research_channel():
    source = DataSourceCreate(
        name="Doubao research", channel_type="doubao_research", channel_config={"question": "test"}
    )
    assert source.channel_type == "doubao_research"
