"""Intent parsing for Collection Need text.

Translates a natural-language user need into structured intent records that the
``demand_assembler`` can project onto real canvas source/channel/runtime
capabilities. The parser is intentionally deterministic — it recognises a small
handful of intent dimensions (target source/site, topic/query, frequency),
never invents capabilities, and always declares what it could not resolve so the
assembler can either emit a blocked-source node or report a missing capability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Order matters: more specific (multi-character) patterns first so a longer
# match wins over a shorter one. Patterns are matched with re.IGNORECASE.
SITE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # ── opencli runnable today ─────────────────────────────────────────────
    # All patterns are wrapped with a Latin-only boundary guard at match time
    # so CJK characters (each "self-contained word") and punctuation are
    # considered separators, while "xhs-test" or "jin10api" do NOT match.
    (
        "xiaohongshu",
        (
            r"小红书",
            r"xiaohongshu",
            r"xhs",
            r"RED\s*书",
        ),
    ),
    (
        "bilibili",
        (
            r"哔哩哔哩",
            r"哔哩",
            r"(?:bilibili|bili|b站)",
        ),
    ),
    (
        "jin10",
        (
            r"金十",
            r"jin10",
            r"jin\s*10",
        ),
    ),
    # ── non-opencli channels (today those project as blocked source nodes) ─
    (
        "weibo",
        (
            r"微博",
            r"weibo",
            r"sina\s*weibo",
        ),
    ),
    (
        "zhihu",
        (
            r"知乎",
            r"zhihu",
        ),
    ),
    (
        "douyin",
        (
            r"抖音",
            r"douyin",
            r"tiktok",
        ),
    ),
    (
        "twitter",
        (
            r"推特",
            r"X\s*平台",
            r"(?:twitter|x\.com)",
        ),
    ),
    (
        "wechat-mp",
        (
            r"微信公众号",
            r"微信公号",
            r"公众号",
        ),
    ),
    (
        "news-rss",
        (
            r"rss",
            r"rss\s*源",
            r"新闻订阅",
        ),
    ),
    (
        "hackernews",
        (
            r"hacker\s*news",
            r"hn\s*榜单",
            r"hn",
        ),
    ),
    (
        "reddit",
        (
            r"reddit",
            r"\br/",
        ),
    ),
    (
        "github-trending",
        (
            r"github\s*trending",
            r"github\s*热门",
            r"gh\s*trending",
        ),
    ),
)

# Topic/kind hints — best-effort, never required. Recognises common demand
# shapes the operator uses in this product (热帖/热搜/资讯/...). The value of
# "kind" maps to OpenCLI source command defaults and channel config defaults.
TOPIC_KIND_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("hot-posts", (r"热帖", r"热门帖子", r"hot\s*posts?", r"热门帖", r"trending")),
    ("hot-search", (r"热搜", r"热门搜索", r"hot\s*search(?:es)?", r"trending\s*(?:topics?|posts?)")),
    # Finance before news so compound "财经新闻" matches finance before "新闻" alone
    ("finance", (r"财经", r"金融", r"行情", r"\bfina?nce?\b", r"stock")),
    ("news", (r"新闻", r"资讯", r"\bnews\b", r"headlines?")),
    ("tech", (r"科技", r"tech\s*news", r"技术")),
    ("video", (r"视频", r"video", r"vlog")),
    ("tweet", (r"推文", r"动态", r"\btweets?\b")),
    ("article", (r"文章", r"\barticle", r"post")),
)

# Schedule/frequency hints. Mapped onto cron expressions / interval seconds.
FREQUENCY_PATTERNS: tuple[tuple[str, tuple[str, ...], dict[str, Any]], ...] = (
    (
        "realtime",
        (r"实时", r"realtime", r"real-?time", r"立刻"),
        {"cron": "* * * * *", "interval": "1m"},
    ),
    (
        "every-5m",
        (r"每\s*5\s*分钟", r"every\s*5\s*min", r"每\s*五分钟"),
        {"cron": "*/5 * * * *", "interval": "5m"},
    ),
    (
        "every-15m",
        (r"每\s*15\s*分钟", r"every\s*15\s*min"),
        {"cron": "*/15 * * * *", "interval": "15m"},
    ),
    (
        "every-30m",
        (r"每\s*半\s*小时", r"每\s*30\s*分钟", r"every\s*30\s*min"),
        {"cron": "*/30 * * * *", "interval": "30m"},
    ),
    (
        "hourly",
        (r"每小时", r"每\s*小\s*时", r"hourly", r"every\s*hour"),
        {"cron": "0 * * * *", "interval": "1h"},
    ),
    (
        "every-6h",
        (r"每\s*6\s*小时", r"every\s*6\s*h"),
        {"cron": "0 */6 * * *", "interval": "6h"},
    ),
    (
        "daily",
        (r"每天", r"每日", r"daily"),
        {"cron": "0 9 * * *", "interval": "24h"},
    ),
    (
        "weekly",
        (r"每周", r"weekly"),
        {"cron": "0 9 * * 1", "interval": "7d"},
    ),
)

# Map a recognised site to the channel it should bind to. The mapping is the
# single source of truth for "what channel does this site belong to?" — frontend
# preview uses the same table.
SITE_TO_CHANNEL: dict[str, str] = {
    "xiaohongshu": "opencli",
    "bilibili": "opencli",
    "jin10": "opencli",
    "weibo": "opencli",
    "zhihu": "opencli",
    "douyin": "opencli",
    "twitter": "opencli",
    "wechat-mp": "opencli",
    "news-rss": "rss",
    "hackernews": "api",
    "reddit": "api",
    "github-trending": "api",
}


@dataclass
class SourceIntent:
    """Per-site intent emitted by the parser.

    ``channel`` and ``source_group`` map to real backend channels / OpenCLI
    source groups. ``args`` are channel-agnostic query arguments (keyword,
    topic, etc.) consumed by the assembler when it materialises the
    source node.
    """

    site: str
    channel: str
    source_group: str = "social"
    kind: str = "hot-posts"
    label: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    resource_tags: list[str] = field(default_factory=list)


@dataclass
class ParsedNeed:
    """Structured intent from one user-typed collection need."""

    text: str
    topic: str
    kind: str | None
    frequency: str | None
    frequency_hint: dict[str, Any] | None
    sources: list[SourceIntent]
    unmatched_tokens: list[str] = field(default_factory=list)

    @property
    def has_recognised_source(self) -> bool:
        return bool(self.sources)


_STOPWORDS = {
    "抓",
    "采集",
    "收集",
    "监控",
    "找",
    "看",
    "fetch",
    "scrape",
    "collect",
    "monitor",
    "track",
    "的",
    "和",
    "及",
    "或",
    "还有",
}

# Tokens we do not want to treat as a "topic" when nothing else survives.
_NOISE_TOPICS = {"热门", "热帖", "新闻", "资讯", "数据", "内容", "信息", "订阅"}


def parse_collection_need(text: str) -> ParsedNeed:
    """Parse a user collection need into a structured ``ParsedNeed``.

    The parser is permissive: when it cannot resolve a dimension (e.g. unknown
    site), it records the unmatched token and continues. ``sources`` may be
    empty, in which case the assembler should emit a missing-capability patch.
    """

    raw = (text or "").strip()
    if not raw:
        return ParsedNeed(
            text="",
            topic="",
            kind=None,
            frequency=None,
            frequency_hint=None,
            sources=[],
            unmatched_tokens=[],
        )

    matched_sites: list[SourceIntent] = []
    unmatched: list[str] = []

    kind = _first_match_kind(raw)
    frequency, frequency_hint = _frequency_hint(raw)

    for site, patterns in SITE_PATTERNS:
        if _matches_any(raw, patterns):
            channel = SITE_TO_CHANNEL.get(site, "opencli")
            intent = SourceIntent(
                site=site,
                channel=channel,
                source_group=_source_group_for_site(site),
                kind=kind or "hot-posts",
                label=_label_for_site(site),
            )
            matched_sites.append(intent)
        else:
            unmatched.append(site)

    topic = _extract_topic(raw)

    return ParsedNeed(
        text=raw,
        topic=topic,
        kind=kind,
        frequency=frequency,
        frequency_hint=frequency_hint,
        sources=matched_sites,
        unmatched_tokens=unmatched,
    )


# Token-boundary helper: site/kind/frequency tokens in real-world user
# queries come packed against CJK characters on either side (``B站AI``,
# ``AI热帖``). Applying strict Latin-only word boundaries would reject those
# cases. We accept the small risk of false positives like ``jin10api``
# matching ``jin10`` and rely on the user typing real-world phrasing — the
# assistant surface is bilingual natural language, not code identifiers.
_BOUNDARY_LOOKBEHIND = ""


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    """Return True when any pattern matches ``text``.

    Patterns are wrapped with a Latin-only boundary guard so that "xhs" matches
    "XHS 趋势" but not "xhs-test" or "xhsabc". The guard is asymmetric on
    purpose: digits adjacent to a keyword are allowed in CJK text but NOT in
    Latin words like "fetch20ids".
    """

    for raw_pattern in patterns:
        pattern = _wrap_boundary(raw_pattern)
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def _wrap_boundary(pattern: str) -> str:
    """Wrap ``pattern`` with a left-side Latin-word guard."""

    return f"{_BOUNDARY_LOOKBEHIND}(?:{pattern})"


def _strip_all(text: str, patterns) -> str:
    """Apply all pattern groups as a single replace pass.

    Accepts tuples of 2-tuples (SITE_PATTERNS, TOPIC_KIND_PATTERNS) or
    3-tuples (FREQUENCY_PATTERNS — extra field is ignored here). Patterns are
    each wrapped with the same Latin-only boundary guards used by
    ``_matches_any``.
    """

    flat: list[str] = []
    for group in patterns:
        if len(group) == 3:
            _, patterns_in_group, _ = group
        else:
            _, patterns_in_group = group
        flat.extend(patterns_in_group)
    if not flat:
        return text
    wrapped = [_wrap_boundary(p) for p in flat]
    joined = "|".join(wrapped)
    return re.sub(joined, " ", text, flags=re.IGNORECASE)


def _first_match_kind(text: str) -> str | None:
    for kind, patterns in TOPIC_KIND_PATTERNS:
        if _matches_any(text, patterns):
            return kind
    return None


def _frequency_hint(text: str) -> tuple[str | None, dict[str, Any] | None]:
    for label, patterns, hint in FREQUENCY_PATTERNS:
        if _matches_any(text, patterns):
            return label, hint
    return None, None


def _extract_topic(text: str) -> str:
    """Best-effort topic extraction. Returns the trimmed remainder after
    stripping intent verbs, site tokens, topic/kind markers, and frequency
    cues. Falls back to a generic placeholder when nothing survives.
    """

    value = text.strip()
    # Drop leading intent verbs.
    for pattern in (
        r"^(?:抓|采集|收集|监控|找|看|帮我|麻烦你|请|帮我|麻烦)\s*",
        r"^(?:please\s+)?(?:fetch|scrape|collect|monitor|track|pull|get)\s+",
    ):
        value = re.sub(pattern, "", value, flags=re.IGNORECASE)

    value = _strip_all(value, SITE_PATTERNS)
    value = _strip_all(value, TOPIC_KIND_PATTERNS)
    value = _strip_all(value, FREQUENCY_PATTERNS)

    # Drop stray stopwords as standalone tokens (CJK and ASCII variants).
    for token in _STOPWORDS:
        value = re.sub(rf"(?:{re.escape(token)})", " ", value, flags=re.IGNORECASE)

    value = re.sub(r"\s+", " ", value).strip(" ：:，,。.??")
    if not value or value in _NOISE_TOPICS:
        return "热门"
    return value


def _source_group_for_site(site: str) -> str:
    mapping = {
        "xiaohongshu": "social",
        "bilibili": "video",
        "jin10": "finance",
        "weibo": "social",
        "zhihu": "social",
        "douyin": "video",
        "twitter": "social",
        "wechat-mp": "social",
        "news-rss": "news",
        "hackernews": "tech",
        "reddit": "social",
        "github-trending": "tech",
    }
    return mapping.get(site, "social")


def _label_for_site(site: str) -> str:
    mapping = {
        "xiaohongshu": "Xiaohongshu",
        "bilibili": "Bilibili",
        "jin10": "JIN10",
        "weibo": "Weibo",
        "zhihu": "Zhihu",
        "douyin": "Douyin",
        "twitter": "Twitter / X",
        "wechat-mp": "WeChat MP",
        "news-rss": "RSS News",
        "hackernews": "Hacker News",
        "reddit": "Reddit",
        "github-trending": "GitHub Trending",
    }
    return mapping.get(site, site.title())
