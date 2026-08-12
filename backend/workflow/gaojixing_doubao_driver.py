# ruff: noqa: E501 -- embedded, audited DOM scripts remain readable as JavaScript
"""Certified OpenCLI + Playwright adapter for Gaojixing Doubao evidence.

The adapter owns the browser-side mutation boundary: ``collect`` is the only
method allowed to create a conversation and submit a question.  Recovery uses
``inspect_current`` and is therefore read-only.  Every capture is written to a
unique attempt directory; the durable collection runner decides which capture
is accepted under its fencing lease.
"""

from __future__ import annotations

import inspect
import json
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

_FORMAL_CHAT_URL = re.compile(r"^https://www\.doubao\.com/chat/\d+$")
_PLACEHOLDER_ANSWERS = {
    "已生成代码",
    "已生成图片",
    "已生成视频",
    "已生成音频",
    "已生成文件",
    "思考中",
    "生成中",
    "加载中",
    "正在生成",
    "正在思考",
    "稍等片刻",
    "计算中",
    "正在计算",
    "正在进行计算",
    "正在为您计算",
    "正在查询",
}
_MODULE_NAMES = (
    "keywords",
    "ref_links",
    "product_links",
    "video_links",
    "followups",
)

CommandRunner = Callable[
    [list[str], str], Awaitable[tuple[int, list[dict[str, Any]], str]]
]
PageCapture = Callable[..., Awaitable[dict[str, Any] | None] | dict[str, Any] | None]
EndpointLease = Callable[[], AbstractAsyncContextManager[str]]


class DoubaoDriverUnavailableError(RuntimeError):
    """Stable fail-closed error raised when the certified driver cannot proceed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OpenCLIDoubaoEvidenceDriver:
    """Submit once through OpenCLI and capture strict page evidence via CDP."""

    def __init__(
        self,
        *,
        project_root: str | Path,
        endpoint_lease: EndpointLease | None = None,
        command_runner: CommandRunner | None = None,
        page_capture: PageCapture | None = None,
    ) -> None:
        root = Path(project_root).resolve()
        if not root.is_dir():
            raise DoubaoDriverUnavailableError("project-root-unavailable")
        self._project_root = root
        self._endpoint_lease = endpoint_lease or _default_endpoint_lease
        self._command_runner = command_runner or _default_command_runner
        self._page_capture = page_capture or _capture_page_evidence

    async def preflight(self) -> None:
        """Verify the logged-in Doubao session without creating or submitting."""

        async with self._endpoint_lease() as endpoint:
            code, rows, _stderr = await self._command_runner(
                _status_command(), endpoint
            )
            if code:
                raise DoubaoDriverUnavailableError("doubao-status-failed")
            if not _chat_url(rows, allow_non_chat=True):
                raise DoubaoDriverUnavailableError("doubao-session-unavailable")

    async def collect(self, *, question_id: str, question: str) -> dict[str, Any]:
        """Create one conversation, submit ``question`` exactly once, and capture."""

        if not question_id or not question.strip():
            raise DoubaoDriverUnavailableError("question-invalid")
        async with self._endpoint_lease() as endpoint:
            new_code, _new_rows, _new_stderr = await self._command_runner(
                _new_command(), endpoint
            )
            if new_code:
                raise DoubaoDriverUnavailableError("doubao-new-failed")

            ask_code, ask_rows, _ask_stderr = await self._command_runner(
                _ask_command(question), endpoint
            )
            if ask_code:
                # Never retry here: the browser may have accepted the question
                # even if the CLI response failed. Recovery must inspect only.
                raise DoubaoDriverUnavailableError("doubao-ask-failed")
            answer = _assistant_answer(ask_rows)

            status_code, status_rows, _status_stderr = await self._command_runner(
                _status_command(), endpoint
            )
            if status_code:
                raise DoubaoDriverUnavailableError("doubao-status-failed")
            chat_url = _chat_url(status_rows)
            if chat_url is None:
                raise DoubaoDriverUnavailableError("formal-chat-url-missing")
            capture = await _maybe_await(
                self._page_capture(
                    endpoint=endpoint,
                    project_root=self._project_root,
                    question_id=question_id,
                    question=question,
                    answer=answer,
                    chat_url=chat_url,
                    allow_submit=False,
                )
            )
            if capture is None:
                raise DoubaoDriverUnavailableError("page-question-not-proven")
            return capture

    async def inspect_current(
        self, *, question_id: str, question: str
    ) -> dict[str, Any] | None:
        """Read the current conversation; never create a chat or submit a question."""

        async with self._endpoint_lease() as endpoint:
            status_code, status_rows, _stderr = await self._command_runner(
                _status_command(), endpoint
            )
            if status_code:
                return None
            chat_url = _chat_url(status_rows)
            if chat_url is None:
                return None
            return await _maybe_await(
                self._page_capture(
                    endpoint=endpoint,
                    project_root=self._project_root,
                    question_id=question_id,
                    question=question,
                    answer="",
                    chat_url=chat_url,
                    allow_submit=False,
                )
            )


def build_opencli_doubao_evidence_driver(
    *, project_root: str | Path
) -> OpenCLIDoubaoEvidenceDriver:
    """Compose the production driver used by local and Celery workers."""

    return OpenCLIDoubaoEvidenceDriver(project_root=project_root)


def _new_command() -> list[str]:
    return ["doubao", "new", "--site-session", "persistent", "-f", "json"]


def _ask_command(question: str) -> list[str]:
    return [
        "doubao",
        "ask",
        question,
        "--site-session",
        "persistent",
        "--timeout",
        "150",
        "-f",
        "json",
    ]


def _status_command() -> list[str]:
    return ["doubao", "status", "--site-session", "persistent", "-f", "json"]


@asynccontextmanager
async def _default_endpoint_lease() -> AsyncIterator[str]:
    from backend.browser_pool import get_pool

    try:
        pool = get_pool()
    except RuntimeError as exc:
        raise DoubaoDriverUnavailableError("browser-pool-unavailable") from exc
    async with pool.acquire() as endpoint:
        yield endpoint


async def _default_command_runner(
    command: list[str], endpoint: str
) -> tuple[int, list[dict[str, Any]], str]:
    from backend.channels.opencli_channel import _parse_json, _parse_yaml, _run_opencli
    from backend.config import get_settings
    from backend.opencli_runtime import resolve_opencli_bin

    if get_settings().collection_mode != "local":
        raise DoubaoDriverUnavailableError("doubao-local-runtime-required")
    env = os.environ.copy()
    # OpenCLI 0.9.x uses the CDP endpoint. Obsolete daemon variables override
    # this value in older deployments, so the certified adapter removes them.
    env.pop("OPENCLI_DAEMON_HOST", None)
    env.pop("OPENCLI_DAEMON_PORT", None)
    env["OPENCLI_CDP_ENDPOINT"] = endpoint
    try:
        code, stdout, stderr = await _run_opencli(
            [resolve_opencli_bin(), *command], env
        )
    except (FileNotFoundError, TimeoutError) as exc:
        raise DoubaoDriverUnavailableError("opencli-runtime-unavailable") from exc
    rows: list[dict[str, Any]] = []
    if stdout.strip():
        try:
            rows = _parse_json(stdout)
        except (ValueError, TypeError):
            parsed = _parse_yaml(stdout)
            rows = [item for item in parsed if isinstance(item, dict)]
    return code, rows, stderr


def _chat_url(
    rows: list[dict[str, Any]], *, allow_non_chat: bool = False
) -> str | None:
    for row in rows:
        for key in ("Url", "URL", "url"):
            value = str(row.get(key) or "").strip()
            if _FORMAL_CHAT_URL.fullmatch(value):
                return value
            if allow_non_chat and value.startswith("https://www.doubao.com"):
                return value
    return None


def _assistant_answer(rows: list[dict[str, Any]]) -> str:
    candidates = [
        row
        for row in rows
        if str(row.get("Role", row.get("role", ""))).strip().lower()
        in {"assistant", "ai", "bot", "助手"}
    ] or rows
    return "\n".join(
        str(row.get("Text", row.get("text", ""))).strip()
        for row in candidates
        if str(row.get("Text", row.get("text", ""))).strip()
    ).strip()


async def _maybe_await(value):
    return await value if inspect.isawaitable(value) else value


async def _capture_page_evidence(
    *,
    endpoint: str,
    project_root: Path,
    question_id: str,
    question: str,
    answer: str,
    chat_url: str,
    allow_submit: bool,
) -> dict[str, Any] | None:
    if allow_submit:
        raise DoubaoDriverUnavailableError("page-capture-submit-forbidden")
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise DoubaoDriverUnavailableError("playwright-unavailable") from exc

    attempt_token = uuid4().hex
    attempt_root = project_root / "screenshots" / question_id / f"attempt-{attempt_token}"
    attempt_root.mkdir(parents=True, exist_ok=False)
    pw = await async_playwright().start()
    browser = None
    page = None
    try:
        browser = await pw.chromium.connect_over_cdp(endpoint)
        context = browser.contexts[0] if browser.contexts else None
        if context is None:
            raise DoubaoDriverUnavailableError("doubao-browser-context-missing")
        page = next(
            (candidate for candidate in context.pages if candidate.url == chat_url),
            None,
        )
        if page is None:
            page = await context.new_page()
            await page.goto(chat_url, wait_until="domcontentloaded", timeout=30_000)
        baseline = await page.evaluate(_BASELINE_PAGE_JS)
        baseline = baseline if isinstance(baseline, dict) else {}
        exception_kind = _page_exception_kind(baseline)
        if exception_kind:
            artifact = await _save_verification_screenshot(
                page, attempt_root, project_root, exception_kind
            )
            return {
                "id": question_id,
                "question": question,
                "status": "verification_required",
                "verification": {
                    "kind": exception_kind,
                    "pageMarkerDetected": True,
                    "screenshotPath": artifact,
                },
            }
        target = await _wait_for_stable_target_turn(
            page,
            question=question,
            token=attempt_token,
        )
        if target is None:
            return None
        if target.get("status") == "verification_required":
            exception_kind = str(target.get("exception_kind") or "")
            if exception_kind not in {"captcha", "login", "access"}:
                raise DoubaoDriverUnavailableError("verification-kind-invalid")
            artifact = await _save_verification_screenshot(
                page, attempt_root, project_root, exception_kind
            )
            return {
                "id": question_id,
                "question": question,
                "status": "verification_required",
                "verification": {
                    "kind": exception_kind,
                    "pageMarkerDetected": True,
                    "screenshotPath": artifact,
                },
            }
        final_answer = str(target.get("answer") or "").strip()
        if _placeholder_answer(final_answer):
            raise DoubaoDriverUnavailableError("full-answer-missing")
        if answer.strip() and not _placeholder_answer(answer) and answer.strip() != final_answer:
            raise DoubaoDriverUnavailableError("opencli-page-answer-mismatch")

        await _expand_references(page, target, attempt_token)
        snapshot = await _wait_for_stable_module_snapshot(page, attempt_token)
        if snapshot.get("target_bound") is not True:
            return None
        if str(snapshot.get("answer") or "").strip() != final_answer:
            raise DoubaoDriverUnavailableError("answer-changed-during-capture")

        screenshots, coverage = await _save_sequential_screenshots(
            page, attempt_root, project_root, attempt_token
        )
        videos = await _capture_video_evidence(
            page,
            snapshot.get("video_cards"),
            attempt_root,
            project_root,
            attempt_token,
        )
        modules, expectations, missing = _page_modules(snapshot, videos)
        observation = _brand_observation(question, final_answer, modules)
        return {
            "id": question_id,
            "question": question,
            "has_brand": question_id.startswith("B"),
            "status": "completed",
            "chat_url": chat_url,
            "answer": final_answer,
            "collected_at": datetime.now(timezone(timedelta(hours=8))).isoformat(
                timespec="seconds"
            ),
            "page_modules": modules,
            "brand_observation": observation,
            "page_evidence": {
                "screenshot_files": screenshots,
                "module_expectations": expectations,
                "screenshot_coverage": coverage,
            },
            "required_missing": missing,
        }
    except DoubaoDriverUnavailableError:
        raise
    except Exception as exc:
        raise DoubaoDriverUnavailableError("doubao-page-capture-failed") from exc
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        await pw.stop()


async def _wait_for_stable_target_turn(
    page,
    *,
    question: str,
    token: str,
) -> dict[str, Any] | None:
    """Bind one exact user turn and require five stable assistant samples."""

    previous_signature = ""
    stable_samples = 0
    for _ in range(65):
        baseline = await page.evaluate(_BASELINE_PAGE_JS)
        baseline = baseline if isinstance(baseline, dict) else {}
        exception_kind = _page_exception_kind(baseline)
        if exception_kind:
            return {
                "status": "verification_required",
                "exception_kind": exception_kind,
            }
        current = await page.evaluate(
            _BIND_TARGET_TURN_JS,
            {"question": question, "token": token},
        )
        if not isinstance(current, dict):
            current = {}
        status = current.get("status")
        if status == "ambiguous":
            raise DoubaoDriverUnavailableError("page-question-ambiguous")
        if status != "matched":
            previous_signature = ""
            stable_samples = 0
            await page.wait_for_timeout(1_000)
            continue
        signature = str(current.get("signature") or "")
        if signature and signature == previous_signature:
            stable_samples += 1
            if stable_samples >= 5:
                return current
        else:
            previous_signature = signature
            stable_samples = 1
        await page.wait_for_timeout(1_000)
    raise DoubaoDriverUnavailableError("doubao-page-unstable")


def _page_exception_kind(snapshot: dict[str, Any]) -> str | None:
    for kind in ("captcha", "login", "access"):
        if snapshot.get(kind) is True:
            return kind
    return None


async def _save_verification_screenshot(
    page, attempt_root: Path, project_root: Path, kind: str
) -> str:
    path = attempt_root / f"verification-{kind}.png"
    await page.screenshot(path=str(path), full_page=False)
    return path.relative_to(project_root).as_posix()


async def _expand_references(
    page, baseline: dict[str, Any], token: str
) -> None:
    signal = baseline.get("reference_signal")
    if not isinstance(signal, dict):
        return
    expected = signal.get("reference_count")
    if isinstance(expected, int) and baseline.get("source_link_count") == expected:
        return
    result = await page.evaluate(_EXPAND_REFERENCES_JS, token)
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise DoubaoDriverUnavailableError("reference-module-expand-failed")
    await page.wait_for_timeout(800)


async def _wait_for_stable_module_snapshot(page, token: str) -> dict[str, Any]:
    previous = ""
    stable_samples = 0
    for _ in range(15):
        snapshot = await page.evaluate(_COLLECT_PAGE_JS, token)
        if not isinstance(snapshot, dict):
            raise DoubaoDriverUnavailableError("page-capture-invalid")
        signature = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        if signature == previous:
            stable_samples += 1
            if stable_samples >= 2:
                return snapshot
        else:
            previous = signature
            stable_samples = 1
        await page.wait_for_timeout(1_000)
    raise DoubaoDriverUnavailableError("page-module-unstable")


async def _save_sequential_screenshots(
    page,
    attempt_root: Path,
    project_root: Path,
    token: str,
) -> tuple[list[str], dict[str, bool]]:
    metrics = await page.evaluate(_SCROLL_METRICS_JS, token)
    if not isinstance(metrics, dict) or metrics.get("ok") is not True:
        raise DoubaoDriverUnavailableError("target-scroll-container-missing")
    height = max(1, int((metrics or {}).get("height") or 1))
    viewport = max(1, int((metrics or {}).get("viewport") or 1))
    maximum = max(0, height - viewport)
    overlap = min(240, max(120, viewport // 4))
    step = max(1, viewport - overlap)
    offsets = [0]
    while offsets[-1] < maximum:
        offsets.append(min(maximum, offsets[-1] + step))
    if len(offsets) < 3:
        offsets = [0, maximum // 2, maximum]

    artifacts: list[str] = []
    answer_seen = False
    for index, offset in enumerate(offsets):
        positioned = await page.evaluate(
            _SCROLL_TO_JS,
            {"token": token, "offset": offset},
        )
        if not isinstance(positioned, dict):
            raise DoubaoDriverUnavailableError("target-scroll-position-failed")
        actual = int(positioned.get("actual") or 0)
        if abs(actual - offset) > 4:
            raise DoubaoDriverUnavailableError("target-scroll-position-mismatch")
        await page.wait_for_timeout(250)
        answer_seen = answer_seen or bool(
            await page.evaluate(_ANSWER_VISIBLE_JS, token)
        )
        label = "顶部" if index == 0 else "底部" if index == len(offsets) - 1 else f"正文{index:02d}"
        path = attempt_root / f"{index + 1:02d}_{label}.png"
        await page.screenshot(path=str(path), full_page=False)
        artifacts.append(path.relative_to(project_root).as_posix())
    if not answer_seen:
        raise DoubaoDriverUnavailableError("answer-screenshot-coverage-missing")
    return artifacts, {"top": True, "answer": True, "bottom": True}


async def _capture_video_evidence(
    page,
    video_cards: Any,
    attempt_root: Path,
    project_root: Path,
    token: str,
) -> list[dict[str, str]]:
    count = len(video_cards) if isinstance(video_cards, list) else 0
    records: list[dict[str, str]] = []
    for index in range(count):
        details = await page.evaluate(
            _OPEN_VIDEO_JS,
            {"token": token, "index": index},
        )
        if not isinstance(details, dict) or details.get("opened") is not True:
            records.append({"account": "", "title": "", "screenshot_file": ""})
            continue
        await page.wait_for_timeout(700)
        player_token = f"{token}-{index}"
        player = await page.evaluate(_READ_VIDEO_PLAYER_JS, player_token)
        player = player if isinstance(player, dict) else {}
        path = attempt_root / f"相关视频{index + 1:02d}_账号标题.png"
        if player.get("valid") is True:
            await page.locator(
                f'[data-gjx-video-player="{player_token}"]'
            ).screenshot(path=str(path))
        records.append(
            {
                "account": str(player.get("account") or "").strip(),
                "title": str(
                    details.get("card_title") or player.get("title") or ""
                ).strip(),
                "screenshot_file": (
                    path.relative_to(project_root).as_posix()
                    if path.is_file()
                    else ""
                ),
            }
        )
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(250)
        closed = await page.evaluate(_VIDEO_PLAYER_CLOSED_JS, player_token)
        if closed is not True:
            records[-1]["account"] = ""
            records[-1]["screenshot_file"] = ""
    return records


def _page_modules(
    snapshot: dict[str, Any], videos: list[dict[str, str]]
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    signal = snapshot.get("reference_signal")
    signal = signal if isinstance(signal, dict) else {}
    expected_keywords = signal.get("keyword_count")
    expected_refs = signal.get("reference_count")
    keywords = _unique_texts(snapshot.get("keywords"))
    references = _unique_links(snapshot.get("source_links"))
    products = _unique_links(snapshot.get("product_links"))
    followups = _unique_texts(snapshot.get("followups"))
    modules: dict[str, Any] = {
        "keywords": keywords if isinstance(expected_keywords, int) else "页面未显示",
        "ref_links": references if isinstance(expected_refs, int) else "页面未显示",
        "product_links": products or "页面未显示",
        "video_links": videos or "页面未显示",
        "followups": followups or "页面未显示",
    }
    expectations = {
        "keywords": {
            "displayed": isinstance(expected_keywords, int),
            "expected_count": expected_keywords if isinstance(expected_keywords, int) else 0,
        },
        "ref_links": {
            "displayed": isinstance(expected_refs, int),
            "expected_count": expected_refs if isinstance(expected_refs, int) else 0,
        },
        "product_links": {"displayed": bool(products), "expected_count": len(products)},
        "video_links": {"displayed": bool(videos), "expected_count": len(videos)},
        "followups": {"displayed": bool(followups), "expected_count": len(followups)},
    }
    missing: list[str] = []
    source_count = snapshot.get("source_block_count")
    if isinstance(source_count, int) and source_count > 1:
        missing.append("reference-source-block-not-unique")
    elif isinstance(signal.get("reference_count"), int) and source_count != 1:
        missing.append("reference-source-block-not-unique")
    if snapshot.get("reference_overlay_ambiguous") is True:
        missing.append("reference-overlay-ambiguous")
    if isinstance(expected_keywords, int) and len(keywords) != expected_keywords:
        missing.append("keyword-count-mismatch")
    if isinstance(expected_refs, int) and len(references) != expected_refs:
        missing.append("reference-count-mismatch")
    if any(not row["account"] or not row["title"] for row in videos):
        missing.append("related-video-account-title-missing")
    product_module_count = snapshot.get("product_module_count")
    if isinstance(product_module_count, int) and product_module_count > len(products):
        missing.append("product-module-link-missing")
    return modules, expectations, missing


def _unique_texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    output: list[str] = []
    for item in value:
        text = str(
            item.get("text") or item.get("title") or ""
            if isinstance(item, dict)
            else item
        ).strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _unique_links(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    output: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("text") or "").strip()
        url = str(item.get("url") or item.get("href") or "").strip()
        if title and url.startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            output.append({"title": title, "url": url})
    return output


def _brand_observation(
    question: str, answer: str, modules: dict[str, Any]
) -> dict[str, Any]:
    target = "高吉星"
    positions: list[dict[str, str]] = []
    start = answer.find(target)
    while start >= 0 and len(positions) < 10:
        positions.append(
            {
                "module": "回答正文",
                "text": answer[max(0, start - 40) : start + len(target) + 60]
                .replace("\n", " ")
                .strip(),
            }
        )
        start = answer.find(target, start + len(target))
    for key, label in (
        ("ref_links", "参考资料"),
        ("product_links", "产品外链"),
        ("video_links", "相关视频"),
        ("followups", "推荐追问"),
    ):
        values = modules.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            text = (
                " ".join(str(part) for part in value.values())
                if isinstance(value, dict)
                else str(value)
            )
            if target in text:
                positions.append({"module": label, "text": text})
    appeared = bool(positions)
    if target in question:
        natural: bool | None = None
        basis = "品牌词问句：只记录出现位置，不判断自然推荐"
    elif not appeared:
        natural = False
        basis = "页面回答和已显示模块未出现高吉星"
    else:
        recommend_words = ("推荐", "建议", "可选", "适合", "优先", "值得", "首选")
        natural = any(
            position["module"] in {"产品外链", "相关视频", "推荐追问"}
            or (
                any(word in position["text"] for word in recommend_words)
                and not any(
                    negative in position["text"]
                    for negative in ("不推荐", "不建议", "避免", "慎选", "不适合")
                )
            )
            for position in positions
        )
        basis = (
            "非品牌问句中，高吉星以推荐性内容或产品/视频/追问形式出现"
            if natural
            else "非品牌问句中仅出现高吉星，未见推荐性线索"
        )
    return {
        "target": target,
        "appeared": appeared,
        "positions": positions[:20],
        "natural_recommendation": natural,
        "basis": basis,
    }


def _placeholder_answer(answer: str) -> bool:
    value = answer.strip()
    return not value or value in _PLACEHOLDER_ANSWERS or (
        len(value) < 6 and re.search(r"[。！？!?]|\n", value) is None
    )


_BASELINE_PAGE_JS = r"""
() => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    if (!el) return false;
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      const style = getComputedStyle(n);
      if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const hasVisible = selector => [...document.querySelectorAll(selector)].some(visible);
  const overlays = [...document.querySelectorAll('[role="dialog"], [aria-modal="true"], .semi-modal, .modal, [role="alert"]')]
    .filter(visible)
    .map(el => norm(el.innerText || el.textContent || ''))
    .filter(text => text && text.length <= 500);
  const routerLogin = window._ROUTER_DATA?.loaderData?.chat_layout?.userSetting?.data?.is_login;
  const captcha = hasVisible('iframe[src*="captcha"], iframe[src*="verify"], iframe[src*="rmc"], input[placeholder*="验证码"], input[aria-label*="验证码"]')
    || overlays.some(text => /人机验证|完成安全验证|滑动验证|拖动滑块/.test(text));
  const login = !captcha && (routerLogin === false || overlays.some(text => /扫码登录|请登录后使用|登录后继续/.test(text)));
  const access = !captcha && !login && overlays.some(text => /访问异常|访问受限|服务异常|当前访问人数过多|网络不给力/.test(text));
  return {
    captcha,
    login,
    access,
  };
}
"""

_BIND_TARGET_TURN_JS = r"""
({question, token}) => {
  const clean = value => (value || '').replace(/\u00a0/g, ' ').replace(/\n{3,}/g, '\n\n').trim();
  const exact = value => clean(value).normalize('NFKC')
    .replace(/^\s*\d+\s*[.、．]\s*/, '')
    .replace(/[^\p{L}\p{N}]/gu, '').toLowerCase();
  const visible = el => {
    if (!(el instanceof HTMLElement)) return false;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const role = root => {
    if (root.matches('[data-testid="send_message"], [class*="send-message"], [class*="bg-g-send-msg-bubble"]')
      || root.querySelector('[data-testid="send_message"], [class*="send-message"], [class*="bg-g-send-msg-bubble"], [data-foundation-type="send-message-action-bar"]')) return 'User';
    if (root.matches('[data-testid="receive_message"], [data-testid*="receive_message"], [class*="receive-message"], [class*="bg-g-receive-msg-bubble"]')
      || root.querySelector('[data-testid="receive_message"], [data-testid*="receive_message"], [class*="receive-message"], [class*="bg-g-receive-msg-bubble"], [data-foundation-type="receive-message-action-bar"]')) return 'Assistant';
    if ((root.matches('[class*="inner-item-"], [class*="top-item-"]') || root.closest('[class*="inner-item-"], [class*="top-item-"]'))
      && (root.matches('.flow-markdown-body, .md-box-root, [class*="md-box-root"]') || root.querySelector('.flow-markdown-body, .md-box-root, [class*="md-box-root"]'))
      && !root.matches('[class*="bg-g-send-msg-bubble"]') && !root.querySelector('[class*="bg-g-send-msg-bubble"]')) return 'Assistant';
    return '';
  };
  const textSelectors = [
    '[data-testid="message_text_content"]', '[data-testid="message_content"]',
    '[data-testid*="message_text"]', '[data-testid*="message_content"]',
    '[class*="message-text"]', '[class*="message-content"]',
    '[class*="bg-g-send-msg-bubble"]', '[class*="bg-g-receive-msg-bubble"]',
    '.flow-markdown-body', '.md-box-root', '[class*="md-box-root"]', '[class*="bubble"]'
  ];
  const text = root => {
    for (const selector of textSelectors) {
      const chunks = [...root.querySelectorAll(selector)].filter(visible)
        .map(el => clean(el.innerText || el.textContent || '')).filter(Boolean);
      if (chunks.length) return clean([...new Set(chunks)].join('\n'));
    }
    return clean(root.innerText || root.textContent || '');
  };
  const lists = [...document.querySelectorAll('[class*="message-list-"], .container-PvPoAn, .scroll-view-OEiNXD, [data-testid="message-list"]')].filter(visible);
  if (!lists.length) return {status: 'missing'};
  const selectors = [
    '[class*="inner-item-"]', '[class*="top-item-"]', '[class*="item-kDun2N"]',
    '[data-testid="union_message"]', '[data-testid="message-block-container"]',
    '[data-message-id]', '[class*="bg-g-send-msg-bubble"]', '[class*="bg-g-receive-msg-bubble"]'
  ];
  const roots = [];
  const seen = new Set();
  for (const list of lists) for (const selector of selectors) list.querySelectorAll(selector).forEach(el => {
    if (!seen.has(el)) { seen.add(el); roots.push(el); }
  });
  const ordered = roots.filter(visible)
    .filter((el, index, items) => !items.some((other, otherIndex) => otherIndex !== index && other.contains(el)))
    .map(el => ({el, role: role(el), text: text(el)}))
    .filter(item => item.role && item.text)
    .sort((a, b) => a.el === b.el ? 0 : (a.el.compareDocumentPosition(b.el) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
  const matches = ordered.map((item, index) => ({item, index}))
    .filter(({item}) => item.role === 'User' && exact(item.text) === exact(question));
  if (matches.length !== 1) return {status: matches.length > 1 ? 'ambiguous' : 'missing'};
  const start = matches[0].index;
  const assistants = [];
  for (let index = start + 1; index < ordered.length; index += 1) {
    if (ordered[index].role === 'User') break;
    if (ordered[index].role === 'Assistant') assistants.push(ordered[index]);
  }
  if (!assistants.length) return {status: 'pending'};
  document.querySelectorAll('[data-gjx-target-assistant], [data-gjx-target-user], [data-gjx-scroll]').forEach(el => {
    el.removeAttribute('data-gjx-target-assistant');
    el.removeAttribute('data-gjx-target-user');
    el.removeAttribute('data-gjx-scroll');
  });
  matches[0].item.el.setAttribute('data-gjx-target-user', token);
  assistants.forEach(item => item.el.setAttribute('data-gjx-target-assistant', token));
  let scroller = assistants[0].el.parentElement;
  while (scroller && scroller !== document.body && scroller.scrollHeight <= scroller.clientHeight + 40) scroller = scroller.parentElement;
  (scroller || document.scrollingElement || document.documentElement).setAttribute('data-gjx-scroll', token);
  const answer = clean(assistants.map(item => item.text).join('\n'));
  const sourceBlocks = assistants.flatMap(item => [...item.el.querySelectorAll('[data-plugin-identifier*="block_type:10025"]')])
    .filter(visible).filter(el => /搜索\s*\d+\s*个关键词[，,、\s]*参考\s*\d+\s*篇资料/.test(clean(el.innerText)));
  const signalMatch = sourceBlocks.length === 1 ? clean(sourceBlocks[0].innerText).match(/搜索\s*(\d+)\s*个关键词[，,、\s]*参考\s*(\d+)\s*篇资料/) : null;
  const links = root => [...root.querySelectorAll('a[href]')].filter(visible)
    .filter(a => /^https?:\/\//i.test(a.href) && !/doubao\.com|bytedance|zijieapi|byteimg|feiliao/i.test(a.href));
  const signature = clean(assistants.map(item => item.el.innerText || '').join('\n'));
  return {
    status: 'matched', answer, signature,
    reference_signal: signalMatch ? {keyword_count: Number(signalMatch[1]), reference_count: Number(signalMatch[2])} : null,
    source_link_count: sourceBlocks.length === 1 ? links(sourceBlocks[0]).length : 0,
  };
}
"""

_EXPAND_REFERENCES_JS = r"""
(token) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const roots = [...document.querySelectorAll(`[data-gjx-target-assistant="${token}"]`)];
  const sources = roots.flatMap(root => [...root.querySelectorAll('[data-plugin-identifier*="block_type:10025"]')])
    .filter(el => /搜索\s*\d+\s*个关键词[，,、\s]*参考\s*\d+\s*篇资料/.test(norm(el.innerText)));
  if (sources.length !== 1) return {ok: false, reason: 'source-block-not-unique'};
  const source = sources[0];
  const trigger = [source, ...source.querySelectorAll('*')]
    .filter(el => /搜索\s*\d+\s*个关键词[，,、\s]*参考\s*\d+\s*篇资料/.test(norm(el.innerText)))
    .sort((a, b) => norm(a.innerText).length - norm(b.innerText).length)[0];
  if (!trigger) return {ok: false, reason: 'source-trigger-missing'};
  const rect = trigger.getBoundingClientRect();
  if (rect.width < 1 || rect.height < 1) return {ok: false, reason: 'source-trigger-hidden'};
  trigger.scrollIntoView({block: 'center'});
  trigger.click();
  return {ok: true};
}
"""

_COLLECT_PAGE_JS = r"""
(token) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    if (!(el instanceof HTMLElement)) return false;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const linkRows = root => [...root.querySelectorAll('a[href]')]
    .filter(visible)
    .map(a => ({title: norm(a.innerText || a.getAttribute('aria-label') || a.title), url: (a.href || '').trim()}))
    .filter(x => x.title && /^https?:\/\//i.test(x.url) && !/doubao\.com|bytedance|zijieapi|byteimg|feiliao/i.test(x.url));
  const roots = [...document.querySelectorAll(`[data-gjx-target-assistant="${token}"]`)].filter(visible);
  if (!roots.length) return {target_bound: false};
  const answerSelector = '[data-testid="message_text_content"], [data-testid="message_content"], [data-testid*="message_text"], [data-testid*="message_content"], [class*="message-text"], [class*="message-content"], .flow-markdown-body, .md-box-root, [class*="md-box-root"]';
  const answerNodes = roots.flatMap(root => [root, ...root.querySelectorAll(answerSelector)])
    .filter(el => el.matches(answerSelector)).filter(visible);
  const answer = norm([...new Set(answerNodes.map(el => norm(el.innerText || el.textContent || '')).filter(Boolean))].join('\n'));
  const sources = roots.flatMap(root => [...root.querySelectorAll('[data-plugin-identifier*="block_type:10025"]')])
    .filter(visible).filter(el => /搜索\s*\d+\s*个关键词[，,、\s]*参考\s*\d+\s*篇资料/.test(norm(el.innerText)));
  const source = sources.length === 1 ? sources[0] : null;
  const sourceText = norm(source && source.innerText);
  const signal = sourceText.match(/搜索\s*(\d+)\s*个关键词[，,、\s]*参考\s*(\d+)\s*篇资料/);
  const keywords = [];
  for (const match of sourceText.matchAll(/[“"]([^”"]+)[”"]/g)) {
    const value = norm(match[1]);
    if (value && value.length < 160 && !keywords.includes(value)) keywords.push(value);
  }
  const productRoots = roots.flatMap(root => [...root.querySelectorAll('[data-plugin-identifier*="product"], [class*="product-card"], [class*="commodity-card"], [class*="goods-card"]')]).filter(visible);
  const productLinks = productRoots.flatMap(linkRows);
  const videoBlocks = roots.flatMap(root => [...root.querySelectorAll('[data-plugin-identifier*="block_type:10050"]')]).filter(visible);
  const videoCards = videoBlocks
    .map(block => {
      const card = block.querySelector('.video-card-CJKKPp, [class*="video-card"], .video-wrapper-YpeXnI, [class*="video-wrapper"]');
      return card && visible(card) ? {card_title: norm(card.innerText)} : null;
    }).filter(Boolean);
  const followups = roots.flatMap(root => [...root.querySelectorAll('[class*="recommend"], [class*="suggest"], [class*="follow"], [class*="related"]')])
    .filter(visible).flatMap(root => [...root.querySelectorAll('button, [role="button"], li')]).filter(visible)
    .map(el => norm(el.innerText)).filter(text => text.length > 4 && text.length < 160 && /[?？]/.test(text))
    .filter((text, index, all) => all.indexOf(text) === index);
  let references = source ? linkRows(source) : [];
  let overlay_ambiguous = false;
  if (signal && references.length !== Number(signal[2])) {
    const overlays = [...document.querySelectorAll('[role="dialog"], [aria-modal="true"], [class*="popover"], [class*="reference"]')]
      .filter(visible).map(root => ({root, links: linkRows(root)})).filter(item => item.links.length > 0);
    if (overlays.length === 1) references = overlays[0].links;
    else if (overlays.length > 1) overlay_ambiguous = true;
  }
  return {
    target_bound: true, answer,
    reference_signal: signal ? {keyword_count: Number(signal[1]), reference_count: Number(signal[2])} : null,
    keywords,
    source_links: references,
    product_links: productLinks,
    product_module_count: productRoots.length,
    video_cards: videoCards,
    followups,
    source_block_count: sources.length,
    reference_overlay_ambiguous: overlay_ambiguous,
  };
}
"""

_SCROLL_METRICS_JS = r"""
(token) => {
  const scroller = document.querySelector(`[data-gjx-scroll="${token}"]`);
  if (!(scroller instanceof HTMLElement)) return {ok: false};
  return {ok: true, height: scroller.scrollHeight, viewport: scroller.clientHeight || window.innerHeight};
}
"""

_SCROLL_TO_JS = r"""
({token, offset}) => {
  const scroller = document.querySelector(`[data-gjx-scroll="${token}"]`);
  if (!(scroller instanceof HTMLElement)) return null;
  scroller.scrollTop = offset;
  scroller.dispatchEvent(new Event('scroll', {bubbles: true}));
  return {actual: scroller.scrollTop};
}
"""

_ANSWER_VISIBLE_JS = r"""
(token) => [...document.querySelectorAll(`[data-gjx-target-assistant="${token}"]`)].some(root => {
  const rect = root.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < window.innerHeight;
})
"""

_OPEN_VIDEO_JS = r"""
({token, index}) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const roots = [...document.querySelectorAll(`[data-gjx-target-assistant="${token}"]`)];
  const block = roots.flatMap(root => [...root.querySelectorAll('[data-plugin-identifier*="block_type:10050"]')])[index];
  const card = block && block.querySelector('.video-card-CJKKPp, [class*="video-card"], .video-wrapper-YpeXnI, [class*="video-wrapper"]');
  if (!card) return {opened: false};
  card.scrollIntoView({block: 'center'});
  const card_title = norm(card.innerText);
  card.click();
  return {opened: true, card_title};
}
"""

_READ_VIDEO_PLAYER_JS = r"""
(token) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    if (!(el instanceof HTMLElement)) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const roots = [...document.querySelectorAll('.play-wrapper.active, [role="dialog"]')].filter(visible);
  if (roots.length !== 1) return {valid: false};
  const root = roots[0];
  const unique = entries => entries.filter((entry, index, all) => all.findIndex(other => other.text === entry.text) === index);
  const accountEntries = unique([...root.querySelectorAll('.name-lctyxx, [class*="author"], [class*="account"], [class*="name-"]')]
    .filter(visible).map(el => ({el, text: norm(el.innerText)})).filter(entry => entry.text)
    .filter(entry => entry.text.startsWith('@') || entry.text.length <= 80));
  const titleEntries = unique([...root.querySelectorAll('.captions-DxoqDI, [class*="caption"], [class*="title"]')]
    .filter(visible).map(el => ({el, text: norm(el.innerText)})).filter(entry => entry.text));
  if (accountEntries.length !== 1 || titleEntries.length !== 1) return {valid: false};
  const rootRect = root.getBoundingClientRect();
  const inside = el => {
    const rect = el.getBoundingClientRect();
    return rect.left >= rootRect.left && rect.right <= rootRect.right
      && rect.top >= rootRect.top && rect.bottom <= rootRect.bottom;
  };
  if (!inside(accountEntries[0].el) || !inside(titleEntries[0].el)) return {valid: false};
  root.setAttribute('data-gjx-video-player', token);
  return {
    valid: true,
    account: accountEntries[0].text,
    title: titleEntries[0].text,
  };
}
"""

_VIDEO_PLAYER_CLOSED_JS = r"""
(token) => {
  const root = document.querySelector(`[data-gjx-video-player="${token}"]`);
  if (!root) return true;
  const style = getComputedStyle(root);
  const rect = root.getBoundingClientRect();
  return style.display === 'none' || style.visibility === 'hidden' || rect.width < 1 || rect.height < 1;
}
"""


__all__ = [
    "DoubaoDriverUnavailableError",
    "OpenCLIDoubaoEvidenceDriver",
    "build_opencli_doubao_evidence_driver",
]
