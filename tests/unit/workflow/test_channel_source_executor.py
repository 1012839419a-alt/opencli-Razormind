import pytest

from backend.channels.base import ChannelResult
from backend.workflow.channel_source_executor import execute_workflow_channel_source


@pytest.mark.asyncio
async def test_channel_source_executor_passes_each_upstream_keyword_directly(monkeypatch):
    calls = []

    async def fake_collect(source, params):
        calls.append((source.channel_type, params))
        return ChannelResult.ok([{"keyword": params["question"], "id": params["question"]}])

    monkeypatch.setattr("backend.workflow.channel_source_executor.collect", fake_collect)
    items = await execute_workflow_channel_source(
        {
            "channelType": "doubao_research",
            "params": {"question": "{{keyword}}", "site_session": "ephemeral"},
        },
        max_items=10,
        upstream_items=[{"keyword": "gjs"}, {"keyword": "dha"}],
    )

    assert [params["question"] for _, params in calls] == ["gjs", "dha"]
    assert [item["id"] for item in items] == ["gjs", "dha"]


@pytest.mark.asyncio
async def test_channel_source_executor_rejects_missing_feishu_connection():
    with pytest.raises(Exception, match="DataSource"):
        await execute_workflow_channel_source(
            {"channelType": "feishu_table", "params": {}}, max_items=10
        )
