import httpx
import pytest

from backend.channels.base import AuthContext, FetchContext
from backend.channels.feishu_table_channel import FeishuTableChannel
from backend.schemas.source import DataSourceCreate


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return httpx.Response(200, json=self.payload, request=httpx.Request("GET", url))


def _config(**overrides):
    return {
        "transport": "http",
        "app_token": "bascn-keywords",
        "table_id": "tblKeywords",
        "keyword_field": "关键词",
        "status_field": "状态",
        "eligible_status": "待采集",
        **overrides,
    }


@pytest.mark.asyncio
async def test_fetch_maps_eligible_rows_and_preserves_stable_lineage():
    client = FakeClient(
        {
            "code": 0,
            "data": {
                "items": [
                    {"record_id": "rec_1", "fields": {"关键词": "高吉星", "状态": "待采集"}},
                    {"record_id": "rec_2", "fields": {"关键词": "忽略", "状态": "已完成"}},
                ],
                "has_more": False,
            },
        }
    )
    result = await FeishuTableChannel().fetch(
        FetchContext(
            config=_config(),
            params={},
            source_id="source-1",
            auth=AuthContext(kind="bearer", token="tenant-token"),
            http=client,
        )
    )

    assert [item["keyword"] for item in result.items] == ["高吉星"]
    assert result.items[0]["id"] == "feishu:source-1:rec_1"
    assert result.items[0]["source_row_id"] == "rec_1"
    assert client.calls[0][1]["headers"] == {"Authorization": "Bearer tenant-token"}
    assert client.calls[0][1]["params"]["page_size"] == 100


@pytest.mark.asyncio
async def test_fetch_returns_next_cursor_for_bounded_pagination():
    client = FakeClient(
        {"code": 0, "data": {"items": [], "has_more": True, "page_token": "next-page"}}
    )
    result = await FeishuTableChannel().fetch(
        FetchContext(config=_config(), params={}, auth=AuthContext(token="token"), http=client)
    )

    assert result.has_more
    assert result.next_cursor == {"page_token": "next-page"}


@pytest.mark.asyncio
async def test_fetch_fails_closed_without_encrypted_token():
    with pytest.raises(Exception, match="token"):
        await FeishuTableChannel().fetch(
            FetchContext(config=_config(), params={}, auth=AuthContext())
        )


@pytest.mark.asyncio
async def test_validate_config_requires_table_identifiers():
    errors = await FeishuTableChannel().validate_config({})
    assert {
        "'app_token' is required for feishu_table",
        "'table_id' is required for feishu_table",
        "'keyword_field' is required for feishu_table",
    } <= set(errors)


def test_source_schema_accepts_feishu_table_channel():
    source = DataSourceCreate(
        name="Feishu keywords", channel_type="feishu_table", channel_config=_config()
    )
    assert source.channel_type == "feishu_table"
