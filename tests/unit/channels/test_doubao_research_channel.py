import pytest

from backend.channels.doubao_research_channel import DoubaoResearchChannel, _citations
from backend.schemas.source import DataSourceCreate


def test_citations_preserve_order_and_strip_punctuation():
    assert _citations(
        "See https://a.example/x. Again https://a.example/x and https://b.example/y."
    ) == [
        {"url": "https://a.example/x"},
        {"url": "https://b.example/y"},
    ]


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


def test_source_schema_accepts_doubao_research_channel():
    source = DataSourceCreate(
        name="Doubao research", channel_type="doubao_research", channel_config={"question": "test"}
    )
    assert source.channel_type == "doubao_research"
