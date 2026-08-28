import json
import threading
from concurrent.futures import ThreadPoolExecutor

from compat.paw_runtime.app import create_app
from compat.paw_runtime.engine import CONTRACT_VERSION, MAX_INPUT_CHARS, PawRuntime
from fastapi.testclient import TestClient


class FakePaw:
    def __init__(self, *, ready=True, output='{"summary":"classified"}'):
        self.ready = ready
        self.output = output
        self.function_calls = []
        self.inference_calls = []

    def is_offline_ready(self, program_id):
        return self.ready

    def function(self, program_id, **kwargs):
        self.function_calls.append((program_id, kwargs))

        def infer(input_text, **inference_kwargs):
            self.inference_calls.append((input_text, inference_kwargs))
            return self.output

        return infer


class BlockingPaw(FakePaw):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.second_entered = threading.Event()
        self.release = threading.Event()
        self.active = 0
        self.active_lock = threading.Lock()

    def function(self, program_id, **kwargs):
        self.function_calls.append((program_id, kwargs))

        def infer(input_text, **inference_kwargs):
            with self.active_lock:
                self.active += 1
                if self.active == 1:
                    self.entered.set()
                else:
                    self.second_entered.set()
            self.release.wait(timeout=2)
            with self.active_lock:
                self.active -= 1
            return json.dumps({"summary": input_text})

        return infer


def _runtime(paw=None, **kwargs):
    return PawRuntime(paw_sdk=paw or FakePaw(), program_id="0123456789abcdef", **kwargs)


def test_health_exposes_fixed_identity_and_offline_readiness():
    client = TestClient(create_app(_runtime()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ready": True,
        "offline": True,
        "contractVersion": CONTRACT_VERSION,
        "program": {
            "programId": "0123456789abcdef",
            "pawVersion": "0.4.4",
            "contractVersion": CONTRACT_VERSION,
        },
    }

def test_health_rejects_missing_program_identity():
    client = TestClient(create_app(PawRuntime(paw_sdk=FakePaw(), program_id="")))

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["program"]["programId"] == ""



def test_enrich_calls_official_sdk_offline_with_fixed_program():
    paw = FakePaw()
    client = TestClient(create_app(_runtime(paw)))

    response = client.post(
        "/v1/enrich",
        json={"programId": "0123456789abcdef", "input": "short prompt", "maxTokens": 32},
    )

    assert response.status_code == 200
    assert response.json()["enrichment"] == {"summary": "classified"}
    assert paw.function_calls == [
        (
            "0123456789abcdef",
            {"offline": True, "n_ctx": 2048, "n_gpu_layers": 0, "verbose": False},
        )
    ]
    assert paw.inference_calls == [("short prompt", {"max_tokens": 32, "temperature": 0.0})]


def test_runtime_reuses_successfully_loaded_offline_function():
    paw = FakePaw()
    runtime = _runtime(paw)

    assert runtime.enrich(runtime.program_id, "first", 8) == {"summary": "classified"}
    assert runtime.enrich(runtime.program_id, "second", 8) == {"summary": "classified"}

    assert len(paw.function_calls) == 1
    assert [call[0] for call in paw.inference_calls] == ["first", "second"]


def test_runtime_serializes_concurrent_offline_inference():
    paw = BlockingPaw()
    runtime = _runtime(paw)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(runtime.enrich, runtime.program_id, "first", 8)
        assert paw.entered.wait(timeout=1)
        second = executor.submit(runtime.enrich, runtime.program_id, "second", 8)
        assert not paw.second_entered.wait(timeout=0.1)
        paw.release.set()
        assert first.result() == {"summary": "first"}
        assert second.result() == {"summary": "second"}

    assert not paw.second_entered.is_set()


def test_missing_cache_is_not_ready_and_never_loads_or_prepares_program():
    paw = FakePaw(ready=False)
    client = TestClient(create_app(_runtime(paw)))

    health = client.get("/health")
    assert health.status_code == 503
    assert health.json()["status"] == "not_ready"
    response = client.post(
        "/v1/enrich",
        json={"programId": "0123456789abcdef", "input": "short", "maxTokens": 8},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "runtime.not_ready"
    assert paw.function_calls == []


def test_program_mismatch_and_empty_input_are_rejected_without_sdk_call():
    paw = FakePaw()
    client = TestClient(create_app(_runtime(paw)))

    mismatch = client.post(
        "/v1/enrich",
        json={"programId": "other.program", "input": "short", "maxTokens": 8},
    )
    empty = client.post(
        "/v1/enrich",
        json={"programId": "0123456789abcdef", "input": "", "maxTokens": 8},
    )

    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "request.program_mismatch"
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "request.invalid"
    assert paw.function_calls == []


def test_ascii_escaped_non_bmp_input_at_character_limit_reaches_sdk():
    paw = FakePaw()
    client = TestClient(create_app(_runtime(paw)))
    input_text = "😀" * MAX_INPUT_CHARS

    response = client.post(
        "/v1/enrich",
        content=json.dumps(
            {"programId": "0123456789abcdef", "input": input_text, "maxTokens": 8}
        ),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    assert paw.inference_calls == [(input_text, {"max_tokens": 8, "temperature": 0.0})]


def test_sdk_output_must_be_bounded_finite_json_object():
    for output, code in [
        ('{"score":NaN}', "response.invalid_json"),
        ("[]", "response.invalid_enrichment"),
        (json.dumps({"large": "x" * 32}), "response.too_large"),
    ]:
        runtime = _runtime(FakePaw(output=output), max_output_bytes=16)
        try:
            runtime.enrich(runtime.program_id, "short", 8)
        except Exception as error:
            assert error.code == code
        else:  # pragma: no cover - each malformed value must fail closed
            raise AssertionError("invalid SDK output must be rejected")


def test_request_byte_limit_is_413():
    client = TestClient(create_app(_runtime(), max_request_bytes=64))

    response = client.post(
        "/v1/enrich",
        json={"programId": "0123456789abcdef", "input": "x" * 128, "maxTokens": 8},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request.too_large"
