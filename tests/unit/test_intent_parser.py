"""Unit tests for the workflow intent parser.

These tests exercise the recognition tables directly so regressions surface
without spinning up the FastAPI app.
"""

from __future__ import annotations

import pytest

from backend.workflow.intent_parser import (
    ParsedNeed,
    parse_collection_need,
)


def test_parser_recognises_xiaohongshu_zh() -> None:
    parsed = parse_collection_need("抓小红书热帖")
    assert [source.site for source in parsed.sources] == ["xiaohongshu"]
    assert all(source.channel == "opencli" for source in parsed.sources)
    assert parsed.kind == "hot-posts"
    # Topic keyword remains when a more specific term like "AI" survives the
    # site/kind strip pass; "热帖" itself is the hot-posts kind marker.
    assert parsed.topic == "热门"


def test_parser_recognises_bilibili_zh() -> None:
    parsed = parse_collection_need("监控哔哩哔哩视频")
    assert any(source.site == "bilibili" for source in parsed.sources)
    assert parsed.kind == "video"


def test_parser_recognises_multi_source_zh() -> None:
    parsed = parse_collection_need("抓小红书和B站AI热帖")
    sites = sorted(source.site for source in parsed.sources)
    assert sites == ["bilibili", "xiaohongshu"]
    assert parsed.topic == "AI"
    assert parsed.kind == "hot-posts"


def test_parser_recognises_jin10() -> None:
    parsed = parse_collection_need("监控金十财经新闻")
    assert any(source.site == "jin10" for source in parsed.sources)
    assert parsed.kind == "finance"


def test_parser_recognises_xhs_en_alias() -> None:
    parsed = parse_collection_need("fetch xhs trending posts")
    assert any(source.site == "xiaohongshu" for source in parsed.sources)
    assert parsed.kind == "hot-posts"


def test_parser_recognises_twitter_en_alias() -> None:
    parsed = parse_collection_need("monitor twitter trending")
    assert any(source.site == "twitter" for source in parsed.sources)


@pytest.mark.parametrize(
    "text, expected_frequency",
    [
        ("每 5 分钟 抓小红书热帖", "every-5m"),
        ("每 15 分钟", "every-15m"),
        ("每小时 抓新闻", "hourly"),
        ("每 6 小时", "every-6h"),
        ("每日新闻", "daily"),
        ("每周一次", "weekly"),
        ("实时热搜", "realtime"),
        ("realtime news", "realtime"),
        ("every 5 min", "every-5m"),
        ("hourly updates", "hourly"),
    ],
)
def test_parser_recognises_frequency(text: str, expected_frequency: str) -> None:
    parsed = parse_collection_need(text)
    assert parsed.frequency == expected_frequency
    assert parsed.frequency_hint is not None
    assert parsed.frequency_hint["interval"]


def test_parser_extracts_topic_keyword() -> None:
    parsed = parse_collection_need("抓 AI 热帖")
    assert parsed.topic == "AI"
    assert parsed.kind == "hot-posts"


def test_parser_extracts_topic_zh() -> None:
    parsed = parse_collection_need("监控财经新闻")
    # "财经" + "新闻" both get stripped as markers; fallback "热门" applies.
    assert parsed.topic == "热门"
    assert parsed.kind in {"news", "finance"}


def test_parser_unknown_source_yields_empty_sources() -> None:
    parsed = parse_collection_need("抓未知平台热帖")
    assert parsed.sources == []
    assert parsed.has_recognised_source is False


def test_parser_empty_text_returns_empty_parsed_need() -> None:
    parsed = parse_collection_need("")
    assert isinstance(parsed, ParsedNeed)
    assert parsed.sources == []
    assert parsed.topic == ""
    assert parsed.frequency is None


def test_parser_whitespace_only_text_returns_empty() -> None:
    parsed = parse_collection_need("   \n  ")
    assert parsed.sources == []
    assert parsed.topic == ""


def test_parser_recognises_hackernews_as_api_channel() -> None:
    parsed = parse_collection_need("Hacker News 热帖")
    sites = [source for source in parsed.sources if source.site == "hackernews"]
    assert sites
    # Channel hints are derived from the site table; api/rss/etc are blocked.
    assert sites[0].channel == "api"


def test_parser_recognises_news_rss_as_rss_channel() -> None:
    parsed = parse_collection_need("RSS 订阅 BBC 新闻")
    sites = [source for source in parsed.sources if source.site == "news-rss"]
    assert sites
    assert sites[0].channel == "rss"
