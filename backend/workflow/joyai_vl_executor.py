"""JoyAI-VL-Interaction executor for OpenCLI Tool Capabilities.

Bridges the workflow runtime to a self-hosted JoyAI-VL-Interaction deployment
(https://github.com/jd-opensource/JoyAI-VL-Interaction) — JD's 8B real-time
video-language interaction model, served OpenAI-compatible via vLLM-Omni.

MVP scope: one synchronous interaction probe per tool call — send the node's
prompt plus media references (video URL / image frames) to the model's
chat-completions endpoint and emit the reply as an event.v1-style payload.
The always-on streaming mode (model watches a live feed and speaks up
unprompted) needs a persistent session and lands later on the same executor.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

JOYAI_VL_INTERACTION_EXECUTOR = "joyai_vl_interaction"
JOYAI_VL_TOOL_CAPABILITY_ID = "tool.realtime.vl.interaction"
JOYAI_VL_DEFAULT_MODEL = "JoyAI-VL-Interaction-Preview"
JOYAI_VL_ENDPOINT_ENV = "JOYAI_VL_URL"
JOYAI_VL_MAX_SAMPLED_FRAMES = 16
JOYAI_VL_MAX_FRAME_BYTES = 5 * 1024 * 1024


class JoyAIVLExecutionError(RuntimeError):
    """Raised when the JoyAI-VL interaction executor cannot produce a reply."""


def execute_joyai_vl_interaction(params: dict[str, Any]) -> dict[str, Any]:
    """Run one vision-language interaction turn against a JoyAI-VL deployment."""

    endpoint = (
        _read_string(params.get("endpoint"))
        or _read_string(params.get("endpointUrl"))
        or _read_string(os.environ.get(JOYAI_VL_ENDPOINT_ENV))
    )
    if not endpoint:
        raise JoyAIVLExecutionError(
            f"JoyAI-VL endpoint is not configured: set {JOYAI_VL_ENDPOINT_ENV} "
            "(vLLM-Omni base URL, e.g. http://joyai-vl:8000) or pass params.endpoint"
        )

    model = _read_string(params.get("model")) or JOYAI_VL_DEFAULT_MODEL
    prompt = (
        _read_string(params.get("prompt"))
        or "描述当前画面正在发生什么, 如有需要人工注意的事件请指出."
    )
    video_url = _read_string(params.get("videoUrl")) or _read_string(params.get("video_url"))
    image_urls = _read_string_list(params.get("imageUrls")) or _read_string_list(
        params.get("image_urls")
    )
    timeout_seconds = _read_timeout(params.get("timeoutSeconds"))
    sampled_frames = _sample_video_frames(video_url, params, timeout_seconds)

    content: list[dict[str, Any]] = []
    if video_url and not sampled_frames:
        content.append({"type": "video_url", "video_url": {"url": video_url}})
    for url in [*image_urls, *sampled_frames]:
        content.append({"type": "image_url", "image_url": {"url": url}})
    content.append({"type": "text", "text": prompt})

    request_body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
    }
    max_tokens = _read_int(params.get("maxTokens"))
    if max_tokens:
        request_body["max_tokens"] = max_tokens

    url = endpoint.rstrip("/") + "/v1/chat/completions"
    opened_at = time.time()
    request = urllib.request.Request(
        url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 OpenCLI-Admin-joyai-vl-executor/0.1",
            **_auth_header(params),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except JoyAIVLExecutionError:
        raise
    except Exception as exc:  # pragma: no cover - exercised by live smoke failures.
        raise JoyAIVLExecutionError(f"JoyAI-VL request failed: {exc}") from exc

    choices = payload.get("choices") or []
    if not choices:
        raise JoyAIVLExecutionError(f"JoyAI-VL returned no choices: {payload}")
    message = choices[0].get("message") or {}
    reply = message.get("content")
    if not isinstance(reply, str) or not reply.strip():
        raise JoyAIVLExecutionError(f"JoyAI-VL returned an empty reply: {payload}")

    duration_ms = round((time.time() - opened_at) * 1000)
    return {
        "schema": "event.vl.interaction.v1",
        "source": "joyai-vl",
        "eventType": "vl.interaction",
        "observedAt": datetime.now(tz=UTC).isoformat(),
        "model": payload.get("model") or model,
        "reply": reply,
        "media": {
            "videoUrl": video_url,
            "imageCount": len(image_urls) + len(sampled_frames),
            **({"sampledFrameCount": len(sampled_frames)} if sampled_frames else {}),
        },
        "request": {
            "url": url,
            "prompt": prompt,
            "durationMs": duration_ms,
        },
        "usage": payload.get("usage") or {},
    }


def _sample_video_frames(
    video_url: str | None, params: dict[str, Any], request_timeout: float
) -> list[str]:
    requested = params.get("sampleVideoFrames")
    if requested is None or requested is False:
        return []
    if not video_url:
        raise JoyAIVLExecutionError("sampleVideoFrames requires params.videoUrl")

    if requested is True:
        frame_count = 4
    elif isinstance(requested, int) and not isinstance(requested, bool):
        frame_count = requested
    else:
        raise JoyAIVLExecutionError(
            "sampleVideoFrames must be true or an integer between "
            f"1 and {JOYAI_VL_MAX_SAMPLED_FRAMES}"
        )
    if not 1 <= frame_count <= JOYAI_VL_MAX_SAMPLED_FRAMES:
        raise JoyAIVLExecutionError(
            f"sampleVideoFrames must be between 1 and {JOYAI_VL_MAX_SAMPLED_FRAMES}"
        )

    interval = _read_bounded_number(
        params.get("sampleIntervalSeconds"), "sampleIntervalSeconds", 0.1, 3600.0, 1.0
    )
    ffmpeg_timeout = _read_bounded_number(
        params.get("sampleTimeoutSeconds"),
        "sampleTimeoutSeconds",
        1.0,
        300.0,
        min(request_timeout, 300.0),
    )
    local_video = Path(video_url)
    parsed = urlparse(video_url)
    if not local_video.is_file() and parsed.scheme not in {"http", "https"}:
        raise JoyAIVLExecutionError(
            "videoUrl must be a local file path or an http(s) URL when sampling"
        )

    with tempfile.TemporaryDirectory(prefix="opencli-joyai-") as temp_dir:
        output_pattern = str(Path(temp_dir) / "frame-%03d.jpg")
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            video_url,
            "-vf",
            f"fps=1/{interval:g},scale='min(1280,iw)':-2",
            "-frames:v",
            str(frame_count),
            "-q:v",
            "3",
            output_pattern,
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=ffmpeg_timeout,
            )
        except FileNotFoundError as exc:
            raise JoyAIVLExecutionError(
                "video sampling requires ffmpeg to be installed and available on PATH"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise JoyAIVLExecutionError(
                f"ffmpeg video sampling timed out after {ffmpeg_timeout:g} seconds"
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip()
            raise JoyAIVLExecutionError(
                f"ffmpeg video sampling failed{f': {detail}' if detail else ''}"
            ) from exc

        frame_paths = sorted(Path(temp_dir).glob("frame-*.jpg"))
        if not frame_paths:
            raise JoyAIVLExecutionError("ffmpeg video sampling produced no frames")
        frames: list[str] = []
        for frame_path in frame_paths[:frame_count]:
            size = frame_path.stat().st_size
            if size <= 0 or size > JOYAI_VL_MAX_FRAME_BYTES:
                raise JoyAIVLExecutionError(
                    f"sampled frame size must be between 1 and {JOYAI_VL_MAX_FRAME_BYTES} bytes"
                )
            frames.append(
                "data:image/jpeg;base64,"
                + base64.b64encode(frame_path.read_bytes()).decode("ascii")
            )
        return frames


def _auth_header(params: dict[str, Any]) -> dict[str, str]:
    api_key = _read_string(params.get("apiKey")) or _read_string(os.environ.get("JOYAI_VL_API_KEY"))
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _read_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _read_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _read_int(value: object) -> int | None:
    try:
        return int(cast(Any, value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _read_timeout(value: object) -> float:
    if isinstance(value, int | float) and value > 0:
        return float(value)
    return 30.0


def _read_bounded_number(
    value: object, name: str, minimum: float, maximum: float, default: float
) -> float:
    if value is None:
        return default
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not minimum <= float(value) <= maximum
    ):
        raise JoyAIVLExecutionError(f"{name} must be between {minimum:g} and {maximum:g}")
    return float(value)
