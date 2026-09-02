from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

CONTRACT_VERSION = "opencli.paw.runtime.v1"
PAW_VERSION = "0.4.4"
DEFAULT_PROGRAM_ID = ""
MAX_INPUT_CHARS = 8_192
MAX_TOKENS = 512
MAX_OUTPUT_BYTES = 65_536
_PROGRAM_ID_RE = re.compile(r"^[a-f0-9]{16,64}$")


class PawRuntimeError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


def _load_sdk() -> Any | None:
    try:
        import programasweights
    except ImportError:
        return None
    return programasweights


class PawRuntime:
    """Serial, bounded adapter around the pinned offline PAW SDK."""

    def __init__(
        self,
        *,
        program_id: str | None = None,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
        n_ctx: int | None = None,
        paw_sdk: Any | None = None,
    ) -> None:
        self.program_id = program_id or os.environ.get("PAW_PROGRAM_ID", DEFAULT_PROGRAM_ID)
        self.max_output_bytes = max_output_bytes
        self.n_ctx = n_ctx or _bounded_env_int("PAW_N_CTX", 2048, 128, 2048)
        self.execution_timeout_seconds = _bounded_env_int(
            "PAW_EXECUTION_TIMEOUT_SECONDS", 30, 1, 120
        )
        self._paw = paw_sdk if paw_sdk is not None else _load_sdk()
        self._function: Any | None = None
        self._inference_lock = threading.Lock()
        self._dispatch_lock: asyncio.Lock | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="paw-inference")
        self._poisoned = False

    def identity(self) -> dict[str, str]:
        return {
            "programId": self.program_id,
            "pawVersion": PAW_VERSION,
            "contractVersion": CONTRACT_VERSION,
        }

    def is_ready(self) -> bool:
        if not _PROGRAM_ID_RE.fullmatch(self.program_id):
            return False
        if self._poisoned or self._paw is None:
            return False
        try:
            return bool(self._paw.is_offline_ready(self.program_id))
        except Exception:
            return False

    async def enrich_async(
        self, program_id: str, input_text: str, max_tokens: int
    ) -> dict[str, Any]:
        if self._poisoned:
            raise PawRuntimeError(
                "runtime.poisoned",
                "PAW runtime is unavailable.",
                status_code=503,
            )
        if self._dispatch_lock is None:
            self._dispatch_lock = asyncio.Lock()
        async with self._dispatch_lock:
            if self._poisoned:
                raise PawRuntimeError(
                    "runtime.poisoned",
                    "PAW runtime is unavailable.",
                    status_code=503,
                )
            future = asyncio.get_running_loop().run_in_executor(
                self._executor, self.enrich, program_id, input_text, max_tokens
            )
            try:
                return await asyncio.wait_for(
                    asyncio.shield(future),
                    self.execution_timeout_seconds,
                )
            except TimeoutError as exc:
                # SDK inference cannot be safely cancelled. Poison this one-worker
                # runtime so queued requests fail fast instead of accumulating threads.
                self._poisoned = True
                self._executor.shutdown(wait=False, cancel_futures=True)
                raise PawRuntimeError(
                    "runtime.timeout",
                    "PAW inference timed out; runtime is unavailable.",
                    status_code=503,
                ) from exc

    def enrich(self, program_id: str, input_text: str, max_tokens: int) -> dict[str, Any]:
        if not _PROGRAM_ID_RE.fullmatch(self.program_id):
            raise PawRuntimeError(
                "runtime.program_not_configured",
                "PAW_PROGRAM_ID must be an immutable hexadecimal program ID.",
                status_code=503,
            )
        if program_id != self.program_id:
            raise PawRuntimeError(
                "request.program_mismatch",
                "The requested PAW program is not available.",
            )
        if not input_text:
            raise PawRuntimeError("request.input_empty", "PAW input must not be empty.")
        if len(input_text) > MAX_INPUT_CHARS:
            raise PawRuntimeError(
                "request.input_too_large",
                "The input exceeds the PAW input limit.",
            )
        if not 1 <= max_tokens <= MAX_TOKENS:
            raise PawRuntimeError(
                "request.max_tokens_invalid",
                "maxTokens is outside the PAW limit.",
            )
        if self._paw is None or not self.is_ready():
            raise PawRuntimeError(
                "runtime.not_ready",
                "The fixed PAW program is unavailable in offline mode.",
                status_code=503,
            )

        try:
            with self._inference_lock:
                if self._function is None:
                    self._function = self._paw.function(
                        self.program_id,
                        offline=True,
                        n_ctx=self.n_ctx,
                        n_gpu_layers=0,
                        verbose=False,
                    )
                output = self._function(input_text, max_tokens=max_tokens, temperature=0.0)
        except Exception as exc:
            raise PawRuntimeError(
                "runtime.inference_failed", "PAW inference failed.", status_code=503
            ) from exc

        if not isinstance(output, str):
            raise PawRuntimeError("response.invalid_json", "PAW returned invalid JSON.")
        encoded = output.encode("utf-8")
        if len(encoded) > self.max_output_bytes:
            raise PawRuntimeError("response.too_large", "PAW output exceeds the output limit.")
        try:
            enrichment = json.loads(output, parse_constant=_reject_nonfinite_json)
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise PawRuntimeError("response.invalid_json", "PAW returned invalid JSON.") from exc
        if not isinstance(enrichment, dict):
            raise PawRuntimeError("response.invalid_enrichment", "PAW must return a JSON object.")
        return enrichment
