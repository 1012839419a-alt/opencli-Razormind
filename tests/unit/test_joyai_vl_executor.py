"""JoyAI-VL interaction tool executor: config guard, request shape, reply parsing."""

import io
import json
import subprocess
from pathlib import Path

import pytest

from backend.workflow.joyai_vl_executor import (
    JOYAI_VL_ENDPOINT_ENV,
    JOYAI_VL_TOOL_CAPABILITY_ID,
    JoyAIVLExecutionError,
    execute_joyai_vl_interaction,
)
from backend.workflow.tool_capabilities import (
    list_workflow_tool_capabilities,
    resolve_workflow_tool_capability,
)


def test_unconfigured_endpoint_raises_actionable_error(monkeypatch):
    monkeypatch.delenv(JOYAI_VL_ENDPOINT_ENV, raising=False)
    with pytest.raises(JoyAIVLExecutionError, match=JOYAI_VL_ENDPOINT_ENV):
        execute_joyai_vl_interaction({})


def test_success_turn_builds_openai_media_request_and_parses_reply(monkeypatch):
    captured: dict = {}

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            json.dumps(
                {
                    "model": "JoyAI-VL-Interaction-Preview",
                    "choices": [{"message": {"role": "assistant", "content": "锅要溢出来了"}}],
                    "usage": {"total_tokens": 42},
                }
            ).encode("utf-8")
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    output = execute_joyai_vl_interaction(
        {
            "endpoint": "http://joyai-vl:8000/",
            "prompt": "看着炉子",
            "videoUrl": "http://media/stove.mp4",
            "imageUrls": ["http://media/frame1.jpg"],
            "timeoutSeconds": 5,
        }
    )

    assert captured["url"] == "http://joyai-vl:8000/v1/chat/completions"
    assert captured["timeout"] == 5.0
    content = captured["body"]["messages"][0]["content"]
    assert {"type": "video_url", "video_url": {"url": "http://media/stove.mp4"}} in content
    assert {"type": "image_url", "image_url": {"url": "http://media/frame1.jpg"}} in content
    assert content[-1] == {"type": "text", "text": "看着炉子"}

    assert output["schema"] == "event.vl.interaction.v1"
    assert output["source"] == "joyai-vl"
    assert output["reply"] == "锅要溢出来了"
    assert output["media"] == {"videoUrl": "http://media/stove.mp4", "imageCount": 1}
    assert output["usage"] == {"total_tokens": 42}


def test_empty_choices_raises(monkeypatch):
    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _FakeResponse(json.dumps({"choices": []}).encode("utf-8")),
    )
    with pytest.raises(JoyAIVLExecutionError, match="no choices"):
        execute_joyai_vl_interaction({"endpoint": "http://joyai-vl:8000"})


def test_video_sampling_sends_bounded_jpeg_data_urls_and_cleans_up(monkeypatch):
    captured: dict = {}

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["subprocess_kwargs"] = kwargs
        output_pattern = Path(command[-1])
        captured["temp_dir"] = output_pattern.parent
        for index, data in enumerate((b"jpeg-one", b"jpeg-two"), start=1):
            output_pattern.parent.joinpath(f"frame-{index:03d}.jpg").write_bytes(data)

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            json.dumps({"choices": [{"message": {"content": "two frames"}}]}).encode()
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    output = execute_joyai_vl_interaction(
        {
            "endpoint": "http://joyai-vl:8000",
            "videoUrl": "https://media.example/video.mp4",
            "imageUrls": ["https://media.example/still.jpg"],
            "sampleVideoFrames": 2,
            "sampleIntervalSeconds": 2.5,
            "sampleTimeoutSeconds": 7,
        }
    )

    assert captured["command"][:8] == [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-i",
        "https://media.example/video.mp4",
        "-vf",
    ]
    assert "fps=1/2.5" in captured["command"][8]
    assert captured["command"][9:11] == ["-frames:v", "2"]
    assert captured["subprocess_kwargs"] == {
        "check": True,
        "capture_output": True,
        "text": True,
        "timeout": 7.0,
    }
    content = captured["body"]["messages"][0]["content"]
    assert not any(item["type"] == "video_url" for item in content)
    image_urls = [item["image_url"]["url"] for item in content if item["type"] == "image_url"]
    assert image_urls == [
        "https://media.example/still.jpg",
        "data:image/jpeg;base64,anBlZy1vbmU=",
        "data:image/jpeg;base64,anBlZy10d28=",
    ]
    assert output["media"] == {
        "videoUrl": "https://media.example/video.mp4",
        "imageCount": 3,
        "sampledFrameCount": 2,
    }
    assert not captured["temp_dir"].exists()


def test_video_sampling_accepts_local_file_and_reports_timeout(monkeypatch, tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["temp_dir"] = Path(command[-1]).parent
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(JoyAIVLExecutionError, match="timed out after 3 seconds"):
        execute_joyai_vl_interaction(
            {
                "endpoint": "http://joyai-vl:8000",
                "videoUrl": str(video),
                "sampleVideoFrames": True,
                "sampleTimeoutSeconds": 3,
            }
        )
    assert not captured["temp_dir"].exists()


@pytest.mark.parametrize("value", [0, 17, "4", 1.5])
def test_video_sampling_rejects_invalid_frame_count(value):
    with pytest.raises(JoyAIVLExecutionError, match="sampleVideoFrames"):
        execute_joyai_vl_interaction(
            {
                "endpoint": "http://joyai-vl:8000",
                "videoUrl": "https://media.example/video.mp4",
                "sampleVideoFrames": value,
            }
        )


def test_tool_capability_is_registered_and_resolvable():
    tool = resolve_workflow_tool_capability(JOYAI_VL_TOOL_CAPABILITY_ID)
    assert tool is not None
    assert tool.executor.mode == "joyai_vl_interaction"
    assert tool.status == "runnable"
    assert [port.type for port in tool.inputPorts] == ["event[]"]
    assert [port.type for port in tool.outputPorts] == ["event[]"]
    assert JOYAI_VL_TOOL_CAPABILITY_ID in {t.id for t in list_workflow_tool_capabilities().tools}
