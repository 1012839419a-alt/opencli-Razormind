"""Collect a cited Doubao research answer through the installed OpenCLI adapter."""

import os
import re
from typing import Any

from backend.channels.base import AbstractChannel, Capabilities, ChannelResult
from backend.channels.registry import register_channel

_URL_RE = re.compile(r"https?://[^\s<>\]\[\](){}\"']+", re.IGNORECASE)
_TRAILING_URL_PUNCTUATION = ".,;:!?\uff0c\u3002\uff1b\uff1a\uff01\uff1f"
def _citations(text: str) -> list[dict[str, str]]:
    """Extract and de-duplicate URLs while preserving the answer's order."""
    seen: set[str] = set()
    citations: list[dict[str, str]] = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(_TRAILING_URL_PUNCTUATION)
        if url and url not in seen:
            seen.add(url)
            citations.append({"url": url})
    return citations


def _answer(rows: list[dict[str, Any]]) -> str:
    """Return the assistant text from OpenCLI's case-preserving table JSON."""
    assistant_rows = [
        row
        for row in rows
        if str(row.get("Role", row.get("role", ""))).strip().lower()
        in {"assistant", "ai", "bot", "助手"}
    ]
    candidates = assistant_rows or rows
    return "\n".join(
        str(row.get("Text", row.get("text", ""))).strip()
        for row in candidates
        if row.get("Text", row.get("text"))
    ).strip()


async def _run_doubao_command(command: list[str]) -> tuple[int, str, str]:
    """Late import avoids the channel registry's legacy OpenCLI import cycle."""
    from backend.channels.opencli_channel import _run_opencli

    return await _run_opencli(command, os.environ.copy())


def _opencli_binary() -> str:
    from backend.channels.opencli_channel import _resolve_bin

    return _resolve_bin("direct")


def _parse_opencli_rows(stdout: str) -> list[dict[str, Any]]:
    from backend.channels.opencli_channel import _parse_json, _parse_yaml

    try:
        return _parse_json(stdout)
    except ValueError:
        return _parse_yaml(stdout)


@register_channel
class DoubaoResearchChannel(AbstractChannel):
    """One cited Doubao answer per pipeline run.

    OpenCLI owns login/session handling; this channel deliberately owns only
    prompt construction and evidence-shaped output for the normal pipeline.
    """

    channel_type = "doubao_research"
    capabilities = Capabilities(auth_kind="session", session_affinity=True, default_rate="6/min")

    async def collect(self, config: dict[str, Any], parameters: dict[str, Any]) -> ChannelResult:
        question = str(parameters.get("question") or config.get("question") or "").strip()
        if not question:
            return ChannelResult.fail("'question' is required for doubao_research channel")

        extract_citations = bool(config.get("extract_citations", True))
        # Prompt wording belongs to the research brief.  Appending a fixed
        # instruction made the browser adapter lose its active conversation;
        # extract URLs from the returned answer without altering the query.
        request = question
        command = [
            _opencli_binary(),
            "doubao",
            "ask",
            request,
            "-f",
            "json",
            "--site-session",
            str(config.get("site_session", "ephemeral")),
        ]
        try:
            returncode, stdout, stderr = await _run_doubao_command(command)
        except TimeoutError as exc:
            return ChannelResult.fail("Doubao request timed out", error_type=type(exc).__name__)
        except FileNotFoundError as exc:
            return ChannelResult.fail("opencli binary not found", error_type=type(exc).__name__)
        except Exception as exc:
            return ChannelResult.fail(
                f"Doubao request failed: {exc}", error_type=type(exc).__name__
            )

        if returncode:
            return ChannelResult.fail(
                f"opencli doubao ask exited with code {returncode}: {stderr[:500]}"
            )
        try:
            answer = _answer(_parse_opencli_rows(stdout))
        except Exception as exc:
            return ChannelResult.fail(
                f"Failed to parse Doubao answer: {exc}", error_type=type(exc).__name__
            )
        if not answer:
            return ChannelResult.fail("Doubao returned no assistant text")

        citations = _citations(answer) if extract_citations else []
        return ChannelResult.ok(
            [
                {
                    "title": question,
                    "content": answer,
                    "author": "doubao",
                    "question": question,
                    "citations": citations,
                    "citation_count": len(citations),
                    "citation_capture": (
                        "answer_url_extraction" if extract_citations else "disabled"
                    ),
                }
            ],
            citation_count=len(citations),
            citation_capture="answer_url_extraction" if extract_citations else "disabled",
        )

    async def validate_config(self, config: dict[str, Any]) -> list[str]:
        return (
            []
            if str(config.get("question") or "").strip()
            else ["'question' is required for doubao_research channel"]
        )
