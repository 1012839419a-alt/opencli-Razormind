import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.processors.paw_processor import PawProcessor
from backend.processors.registry import get_processor


class FakeResponse:
    def __init__(self, payload, *, fail=False):
        self.payload = payload
        self.fail = fail
        self.closed = False

    def raise_for_status(self):
        if self.fail:
            raise RuntimeError("sidecar unavailable")

    async def aiter_bytes(self):
        yield json.dumps(self.payload, allow_nan=True).encode("utf-8")

    async def aclose(self):
        self.closed = True


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def build_request(self, method, url, json):
        return method, url, json

    async def send(self, request, *, stream):
        method, url, payload = request
        assert method == "POST"
        assert stream is True
        self.requests.append((url, payload))
        return next(self.responses)


def _record(title="Market note"):
    record = MagicMock()
    record.normalized_data = {"title": title, "content": "Short normalized content"}
    record.raw_data = {"cookies": "must-not-send", "html": "<html>full document</html>"}
    return record


def _settings():
    return SimpleNamespace(
        paw_runtime_url="http://paw-runtime:8097",
        paw_runtime_timeout_seconds=4,
        paw_program_id="0123456789abcdef",
        paw_max_tokens=512,
    )


def _response(enrichment=None, **overrides):
    return {
        "contractVersion": overrides.get("contractVersion", "opencli.paw.runtime.v1"),
        "programId": overrides.get("programId", "0123456789abcdef"),
        "enrichment": {"summary": "ok"} if enrichment is None else enrichment,
    }


def test_paw_processor_is_registered():
    assert get_processor("paw").processor_type == "paw"

@pytest.mark.asyncio
async def test_paw_rejects_missing_program_identity_before_http():
    settings = _settings()
    settings.paw_program_id = ""
    with patch("backend.processors.paw_processor.get_settings", return_value=settings), patch(
        "backend.processors.paw_processor.guarded_async_client"
    ) as guarded:
        result = await PawProcessor().process([_record()], "{{title}}", {})

    assert result.success is False
    assert result.error == "runtime.program_not_configured"
    guarded.assert_not_awaited()



@pytest.mark.asyncio
async def test_paw_posts_only_rendered_normalized_short_text_and_validates_response():
    client = FakeClient([FakeResponse(_response())])
    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client",
        return_value=(client, "http://paw-runtime:8097"),
    ) as guarded:
        result = await PawProcessor().process(
            [_record()], "Classify {{title}}", {"max_tokens": 32}
        )

    assert result.success is True
    assert result.enrichments == [{"summary": "ok"}]
    assert client.requests == [
        (
            "http://paw-runtime:8097/v1/enrich",
            {
                "programId": "0123456789abcdef",
                "input": "Classify Market note",
                "maxTokens": 32,
            },
        )
    ]
    assert guarded.await_args.kwargs["allow_private"] is True



@pytest.mark.asyncio
async def test_paw_accepts_enrichment_matching_optional_output_schema():
    client = FakeClient([FakeResponse(_response({"summary": "ok"}))])
    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client",
        return_value=(client, "http://paw-runtime:8097"),
    ):
        result = await PawProcessor().process(
            [_record()],
            "{{title}}",
            {
                "output_schema": {
                    "type": "object",
                    "required": ["summary"],
                    "properties": {"summary": {"type": "string"}},
                }
            },
        )

    assert result.success is True
    assert result.enrichments == [{"summary": "ok"}]


@pytest.mark.asyncio
async def test_paw_rejects_enrichment_not_matching_optional_output_schema():
    client = FakeClient([FakeResponse(_response({"summary": 3}))])
    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client",
        return_value=(client, "http://paw-runtime:8097"),
    ):
        result = await PawProcessor().process(
            [_record()],
            "{{title}}",
            {"output_schema": {"type": "object", "properties": {"summary": {"type": "string"}}}},
        )

    assert result.success is False
    assert result.failed_indices == {0}
    assert result.enrichments == [{}]


@pytest.mark.asyncio
async def test_paw_rejects_nonlocal_endpoint_and_sensitive_or_blank_prompts():
    settings = _settings()
    settings.paw_runtime_url = "https://example.test:8097"
    with patch("backend.processors.paw_processor.get_settings", return_value=settings), patch(
        "backend.processors.paw_processor.guarded_async_client"
    ) as guarded:
        result = await PawProcessor().process([_record()], "{{title}}", {})
    assert result.error == "runtime.endpoint_rejected: paw.local_only"
    guarded.assert_not_awaited()

    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client"
    ) as guarded:
        sensitive = await PawProcessor().process([_record()], "{{auth_token}}", {})
        blank = await PawProcessor().process([_record()], "   ", {})
    assert sensitive.error == "request.sensitive_placeholder"
    assert blank.failed_indices == {0}
    guarded.assert_not_awaited()


@pytest.mark.asyncio
async def test_paw_rejects_invalid_output_schema_before_contacting_sidecar():
    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client"
    ) as guarded:
        result = await PawProcessor().process(
            [_record()], "{{title}}", {"output_schema": {"type": "not-a-json-schema-type"}}
        )

    assert result.success is False
    assert result.error == "request.output_schema_invalid"
    guarded.assert_not_awaited()

@pytest.mark.asyncio
async def test_paw_rejects_identity_or_contract_mismatch_without_enrichment():
    client = FakeClient(
        [
            FakeResponse(_response(programId="other.program")),
            FakeResponse(_response(contractVersion="opencli.other.v1")),
        ]
    )
    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client",
        return_value=(client, "http://paw-runtime:8097"),
    ):
        result = await PawProcessor().process([_record(), _record()], "{{title}}", {})

    assert result.success is False
    assert result.failed_indices == {0, 1}
    assert result.enrichments == [{}, {}]


@pytest.mark.asyncio
async def test_paw_rejects_oversized_prompt_before_sidecar_call():
    client = FakeClient([])
    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client",
        return_value=(client, "http://paw-runtime:8097"),
    ):
        result = await PawProcessor().process([_record("x" * 8_193)], "{{title}}", {})

    assert result.success is False
    assert result.failed_indices == {0}
    assert client.requests == []


@pytest.mark.asyncio
async def test_paw_rejects_empty_rendered_input_without_contacting_sidecar():
    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client"
    ) as guarded:
        result = await PawProcessor().process([_record()], "", {})

    assert result.success is False
    assert result.failed_indices == {0}
    guarded.assert_not_awaited()


@pytest.mark.asyncio
async def test_paw_rejects_invalid_token_config_without_contacting_sidecar():
    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()):
        result = await PawProcessor().process([_record()], "{{title}}", {"max_tokens": 513})

    assert result.success is False
    assert result.error == "request.max_tokens_invalid"


@pytest.mark.asyncio
async def test_paw_rejects_guard_failure_without_contacting_sidecar():
    from backend.security.url_guard import SSRFValidationError

    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client",
        side_effect=SSRFValidationError("blocked"),
    ):
        result = await PawProcessor().process([_record()], "{{title}}", {})

    assert result.success is False
    assert result.error.startswith("runtime.endpoint_rejected:")


@pytest.mark.asyncio
async def test_paw_rejects_non_json_or_oversized_enrichment():
    client = FakeClient(
        [
            FakeResponse(_response({"not_json": {1}})),
            FakeResponse(_response({"large": "x" * 65_537})),
        ]
    )
    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client",
        return_value=(client, "http://paw-runtime:8097"),
    ):
        result = await PawProcessor().process([_record(), _record()], "{{title}}", {})

    assert result.success is False
    assert result.failed_indices == {0, 1}


@pytest.mark.asyncio
async def test_paw_rejects_nonfinite_json_enrichment():
    client = FakeClient([FakeResponse(_response({"score": float("nan")}))])
    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client",
        return_value=(client, "http://paw-runtime:8097"),
    ):
        result = await PawProcessor().process([_record()], "{{title}}", {})

    assert result.success is False
    assert result.failed_indices == {0}


@pytest.mark.asyncio
async def test_paw_continues_after_sidecar_failure():
    client = FakeClient([FakeResponse({}, fail=True), FakeResponse(_response({"tag": "news"}))])
    with patch("backend.processors.paw_processor.get_settings", return_value=_settings()), patch(
        "backend.processors.paw_processor.guarded_async_client",
        return_value=(client, "http://paw-runtime:8097"),
    ):
        result = await PawProcessor().process([_record(), _record()], "{{title}}", {})

    assert result.success is False
    assert result.failed_indices == {0}
    assert result.enrichments == [{}, {"tag": "news"}]
