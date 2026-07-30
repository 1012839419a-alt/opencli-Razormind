"""Fetch one public Douyin video detail through the browser-bound OpenCLI adapter."""

import json
import re
from typing import Any
from urllib.parse import urlparse

from backend.channels.base import AbstractChannel, Capabilities, ChannelResult
from backend.channels.registry import register_channel

_AWEME_ID_RE = re.compile(r"(?:/video/|/share/video/|[?&]aweme_id=)(\d{15,25})(?:[/?&#]|$)")


def _aweme_id(value: Any) -> str | None:
    """Accept a canonical Douyin video URL or its numeric aweme id."""
    raw = str(value or "").strip()
    if raw.isdigit() and 15 <= len(raw) <= 25:
        return raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower()
    if not (
        host == "douyin.com"
        or host.endswith(".douyin.com")
        or host.endswith(".iesdouyin.com")
    ):
        return None
    match = _AWEME_ID_RE.search(raw)
    return match.group(1) if match else None


def _first_url(value: Any) -> str | None:
    if isinstance(value, dict):
        urls = value.get("url_list")
        if isinstance(urls, list):
            return next((str(url) for url in urls if isinstance(url, str) and url), None)
    return None


def _tags(detail: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for tag in detail.get("video_tag") or []:
        if isinstance(tag, dict) and isinstance(tag.get("tag_name"), str) and tag["tag_name"]:
            tags.append(tag["tag_name"])
    for extra in detail.get("text_extra") or []:
        if isinstance(extra, dict):
            name = extra.get("hashtag_name") or extra.get("hashtag_name_raw")
            if isinstance(name, str) and name:
                tags.append(name)
    return list(dict.fromkeys(tags))


def _detail_item(detail: dict[str, Any], aweme_id: str) -> dict[str, Any]:
    author = detail.get("author") if isinstance(detail.get("author"), dict) else {}
    video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
    statistics = detail.get("statistics") if isinstance(detail.get("statistics"), dict) else {}
    description = str(detail.get("desc") or detail.get("caption") or "").strip()
    play_url = _first_url(video.get("play_addr") or video.get("play_addr_h264"))
    cover_url = _first_url(video.get("cover") or video.get("origin_cover"))
    canonical_url = f"https://www.douyin.com/video/{aweme_id}"
    return {
        "title": description or f"Douyin video {aweme_id}",
        "content": description,
        "author": str(author.get("nickname") or author.get("unique_id") or ""),
        "url": canonical_url,
        "aweme_id": str(detail.get("aweme_id") or aweme_id),
        "create_time": detail.get("create_time"),
        "play_url": play_url,
        "cover_url": cover_url,
        "statistics": {
            key: statistics.get(key)
            for key in ("digg_count", "comment_count", "share_count", "collect_count", "play_count")
            if statistics.get(key) is not None
        },
        "tags": _tags(detail),
        "media": {
            "type": "video",
            "play_url": play_url,
            "cover_url": cover_url,
            "duration_ms": video.get("duration"),
        },
    }


def _parse_detail(stdout: str) -> dict[str, Any]:
    start = stdout.find("{")
    if start < 0:
        raise ValueError("OpenCLI browser eval returned no JSON")
    payload = json.loads(stdout[start:])
    if not isinstance(payload, dict):
        raise ValueError("OpenCLI browser eval returned a non-object payload")
    detail = payload.get("aweme_detail")
    if not isinstance(detail, dict):
        raise ValueError("Douyin detail response has no aweme_detail")
    return detail


async def _run_douyin_command(command: list[str]) -> tuple[int, str, str]:
    """Use OpenCLI's bounded subprocess helper rather than spawning a shell."""
    import os

    from backend.channels.opencli_channel import _run_opencli

    return await _run_opencli(command, os.environ.copy())


def _opencli_binary() -> str:
    from backend.channels.opencli_channel import _resolve_bin

    return _resolve_bin("direct")


@register_channel
class DouyinDetailChannel(AbstractChannel):
    """Collect public metadata and playable media URLs for one Douyin video."""

    channel_type = "douyin_detail"
    capabilities = Capabilities(auth_kind="session", session_affinity=True, default_rate="12/min")

    async def collect(self, config: dict[str, Any], parameters: dict[str, Any]) -> ChannelResult:
        raw_url = parameters.get("url") or config.get("url")
        aweme_id = _aweme_id(raw_url)
        if not aweme_id:
            return ChannelResult.fail("'url' must be a Douyin video URL or numeric aweme id")

        session = str(
            parameters.get("browser_session") or config.get("browser_session") or "douyin-detail"
        )
        canonical_url = f"https://www.douyin.com/video/{aweme_id}"
        detail_script = (
            f"fetch('/aweme/v1/web/aweme/detail/?aweme_id={aweme_id}')"
            ".then(function(r){return r.text()})"
        )
        binary = _opencli_binary()
        try:
            open_code, _, open_stderr = await _run_douyin_command(
                [binary, "browser", session, "open", canonical_url]
            )
            if open_code:
                return ChannelResult.fail(
                    f"OpenCLI browser open exited with code {open_code}: {open_stderr[:500]}"
                )
            eval_code, stdout, stderr = await _run_douyin_command(
                [
                    binary,
                    "browser",
                    session,
                    "eval",
                    # ``>`` in an arrow function is interpreted by the Windows
                    # ``.CMD`` OpenCLI shim before it reaches the browser.
                    detail_script,
                ]
            )
        except TimeoutError as exc:
            return ChannelResult.fail(
                "Douyin detail request timed out", error_type=type(exc).__name__
            )
        except FileNotFoundError as exc:
            return ChannelResult.fail("opencli binary not found", error_type=type(exc).__name__)
        except Exception as exc:
            return ChannelResult.fail(
                f"Douyin detail request failed: {exc}", error_type=type(exc).__name__
            )

        if eval_code:
            return ChannelResult.fail(
                f"OpenCLI browser eval exited with code {eval_code}: {stderr[:500]}"
            )
        try:
            item = _detail_item(_parse_detail(stdout), aweme_id)
        except (ValueError, json.JSONDecodeError) as exc:
            return ChannelResult.fail(
                f"Failed to parse Douyin detail: {exc}", error_type=type(exc).__name__
            )
        return ChannelResult.ok([item], aweme_id=aweme_id, canonical_url=canonical_url)

    async def validate_config(self, config: dict[str, Any]) -> list[str]:
        return (
            []
            if _aweme_id(config.get("url"))
            else ["'url' must be a Douyin video URL or numeric aweme id"]
        )

    def identity(self, item: dict[str, Any]) -> str | None:
        value = item.get("aweme_id")
        return str(value) if value else None
