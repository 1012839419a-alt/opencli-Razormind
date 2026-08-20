import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database import commit_session
from backend.models.workflow_run import WorkflowRun
from backend.workflow.managed_gaojixing_question_batches import (
    stage_managed_question_batch,
)


def _question_bank() -> bytes:
    return json.dumps(
        {
            "phase1": [
                {"id": "G0001", "question": "第一道非品牌题"},
                {"id": "G0002", "question": "第二道非品牌题"},
            ],
            "phase2": [
                {"id": "B001", "question": "高吉星品牌题"},
            ],
        },
        ensure_ascii=False,
    ).encode()


def _workflow_run(run_id: str) -> WorkflowRun:
    return WorkflowRun(
        id=run_id,
        workflow_id="workflow-1",
        trace_id=f"trace-{run_id}",
        status="waiting",
        valid=True,
        request={},
        projection={},
    )


@pytest.mark.asyncio
async def test_managed_question_batch_materializes_once_and_dispatches_after_commit(
    db_session, tmp_path
):
    from backend.models.gaojixing_collection import GaojixingQuestionCheckpoint
    from backend.services.gaojixing_collection_service import ensure_collection

    run_id = "run-gjx-durable-1"
    signing_key = "test-signing-key"
    staged = stage_managed_question_batch(
        _question_bank(),
        filename="questions.json",
        run_id=run_id,
        storage_root=tmp_path,
        signing_key=signing_key,
    )
    db_session.add(_workflow_run(run_id))
    dispatched: list[str] = []

    job = await ensure_collection(
        db_session,
        workflow_run_id=run_id,
        node_id="batch::tool",
        question_batch_ref=staged.question_batch_ref,
        storage_root=tmp_path,
        signing_key=signing_key,
        dispatch=dispatched.append,
    )
    repeated = await ensure_collection(
        db_session,
        workflow_run_id=run_id,
        node_id="batch::tool",
        question_batch_ref=staged.question_batch_ref,
        storage_root=tmp_path,
        signing_key=signing_key,
        dispatch=dispatched.append,
    )

    checkpoints = list(
        (
            await db_session.execute(
                select(GaojixingQuestionCheckpoint)
                .where(GaojixingQuestionCheckpoint.collection_run_id == job.id)
                .order_by(GaojixingQuestionCheckpoint.position)
            )
        )
        .scalars()
        .all()
    )
    assert repeated.id == job.id
    assert [(row.question_id, row.phase, row.position) for row in checkpoints] == [
        ("G0001", "phase1", 1),
        ("G0002", "phase1", 2),
        ("B001", "phase2", 3),
    ]
    assert dispatched == []

    await commit_session(db_session)

    assert dispatched == [job.id]


class _FakeEvidenceDriver:
    def __init__(self, project_root):
        self.project_root = project_root
        self.collected: list[str] = []
        self.inspected: list[str] = []

    async def preflight(self) -> None:
        return None

    async def collect(self, *, question_id: str, question: str) -> dict:
        self.collected.append(question_id)
        return self._capture(question_id, question)

    async def inspect_current(self, *, question_id: str, question: str) -> dict | None:
        self.inspected.append(question_id)
        return self._capture(question_id, question)

    def _capture(self, question_id: str, question: str) -> dict:
        screenshot_files = []
        for suffix in ("01_顶部", "02_正文", "03_底部"):
            relative = f"screenshots/{question_id}_{suffix}.png"
            path = self.project_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"{question_id}:{suffix}".encode())
            screenshot_files.append(relative)
        is_brand = question_id.startswith("B")
        return {
            "id": question_id,
            "question": question,
            "has_brand": is_brand,
            "status": "completed",
            "chat_url": f"https://www.doubao.com/chat/{1000000000 + len(self.collected)}",
            "answer": f"完整回答：{question}",
            "collected_at": "2026-08-12T10:00:00Z",
            "page_modules": {
                "keywords": "页面未显示",
                "ref_links": "页面未显示",
                "product_links": "页面未显示",
                "video_links": "页面未显示",
                "followups": "页面未显示",
            },
            "brand_observation": {
                "target": "高吉星",
                "appeared": is_brand,
                "positions": ([{"module": "原问句", "text": question}] if is_brand else []),
                "natural_recommendation": None if is_brand else False,
                "basis": (
                    "品牌词问句，不判断自然推荐"
                    if is_brand
                    else "页面回答和已显示模块未出现高吉星"
                ),
            },
            "page_evidence": {
                "screenshot_files": screenshot_files,
                "module_expectations": {
                    name: {"displayed": False, "expected_count": 0}
                    for name in (
                        "keywords",
                        "ref_links",
                        "product_links",
                        "video_links",
                        "followups",
                    )
                },
                "screenshot_coverage": {"top": True, "answer": True, "bottom": True},
            },
            "required_missing": [],
        }


@pytest.mark.asyncio
async def test_local_executor_dispatches_committed_upload_into_the_real_runner(
    db_engine, tmp_path, monkeypatch
):
    import asyncio

    from backend.config import get_settings
    from backend.models.gaojixing_collection import (
        GaojixingCollectionRun,
        GaojixingCollectionRunStatus,
    )
    from backend.services.gaojixing_collection_service import ensure_collection
    from backend.workflow import gaojixing_worker_runtime
    from backend.workflow.gaojixing_collection_runner import run_collection_job

    run_id = "run-gjx-local-dispatch"
    signing_key = "test-signing-key"
    staged = stage_managed_question_batch(
        _question_bank(),
        filename="questions.json",
        run_id=run_id,
        storage_root=tmp_path,
        signing_key=signing_key,
    )
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    completed = asyncio.Event()

    async def execute(job_id: str) -> str:
        return await run_collection_job(
            job_id,
            session_factory=sessions,
            driver_factory=_FakeEvidenceDriver,
            schedule_resume=lambda _run_id: completed.set(),
            storage_root=tmp_path,
            signing_key=signing_key,
        )

    monkeypatch.setattr(get_settings(), "task_executor", "local")
    monkeypatch.setattr(gaojixing_worker_runtime, "execute_collection_job", execute)
    async with sessions() as db:
        db.add(_workflow_run(run_id))
        job = await ensure_collection(
            db,
            workflow_run_id=run_id,
            node_id="batch::tool",
            question_batch_ref=staged.question_batch_ref,
            storage_root=tmp_path,
            signing_key=signing_key,
        )
        job_id = job.id
        await commit_session(db)

    await asyncio.wait_for(completed.wait(), timeout=5)
    async with sessions() as db:
        stored = await db.get(GaojixingCollectionRun, job_id)
        assert stored is not None
        assert stored.status == GaojixingCollectionRunStatus.REVIEWING.value


@pytest.mark.asyncio
async def test_hermes_executor_leaves_new_collection_queued_for_hermes(
    db_engine, tmp_path, monkeypatch
):
    """A Hermes-owned execution resource must not be claimed by the API process."""
    import asyncio

    from backend.config import get_settings
    from backend.models.gaojixing_collection import GaojixingCollectionRun
    from backend.services.gaojixing_collection_service import ensure_collection
    from backend.workflow import gaojixing_worker_runtime

    run_id = "run-gjx-hermes-dispatch"
    staged = stage_managed_question_batch(
        _question_bank(),
        filename="questions.json",
        run_id=run_id,
        storage_root=tmp_path,
        signing_key="test-signing-key",
    )
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    started = asyncio.Event()

    async def api_process_execute(_job_id: str) -> str:
        started.set()
        return "completed"

    monkeypatch.setattr(get_settings(), "task_executor", "hermes")
    monkeypatch.setattr(gaojixing_worker_runtime, "execute_collection_job", api_process_execute)
    async with sessions() as db:
        db.add(_workflow_run(run_id))
        collection = await ensure_collection(
            db,
            workflow_run_id=run_id,
            node_id="batch::tool",
            question_batch_ref=staged.question_batch_ref,
            storage_root=tmp_path,
            signing_key="test-signing-key",
        )
        await commit_session(db)

    await asyncio.sleep(0)
    assert not started.is_set()
    async with sessions() as db:
        stored = await db.get(GaojixingCollectionRun, collection.id)
        assert stored is not None
        assert stored.status == "queued"


@pytest.mark.asyncio
async def test_fake_driver_collects_phase1_before_phase2_and_builds_certifiable_archive(
    db_engine, tmp_path
):
    from backend.models.gaojixing_collection import (
        GaojixingCollectionRun,
        GaojixingCollectionRunStatus,
    )
    from backend.services.gaojixing_collection_service import (
        ensure_collection,
        mark_collection_succeeded,
    )
    from backend.workflow.gaojixing_certification import (
        execute_gaojixing_batch_certification,
    )
    from backend.workflow.gaojixing_collection_runner import run_collection_job
    from backend.workflow.gaojixing_doubao import execute_gaojixing_doubao_batch

    run_id = "run-gjx-fake-e2e"
    signing_key = "test-signing-key"
    staged = stage_managed_question_batch(
        _question_bank(),
        filename="questions.json",
        run_id=run_id,
        storage_root=tmp_path,
        signing_key=signing_key,
    )
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as db:
        db.add(_workflow_run(run_id))
        job = await ensure_collection(
            db,
            workflow_run_id=run_id,
            node_id="batch::tool",
            question_batch_ref=staged.question_batch_ref,
            storage_root=tmp_path,
            signing_key=signing_key,
            dispatch=lambda _job_id: None,
        )
        job_id = job.id
        await commit_session(db)

    resolved_root = tmp_path / "runs" / run_id
    drivers: list[_FakeEvidenceDriver] = []

    def driver_factory(attempt_root):
        driver = _FakeEvidenceDriver(attempt_root)
        drivers.append(driver)
        return driver

    resumed: list[str] = []
    outcome = await run_collection_job(
        job_id,
        session_factory=sessions,
        driver_factory=driver_factory,
        schedule_resume=resumed.append,
        storage_root=tmp_path,
        signing_key=signing_key,
    )

    assert outcome == "workflow_resume_scheduled"
    assert drivers[0].collected == ["G0001", "G0002", "B001"]
    assert drivers[0].inspected == []
    assert resumed == [run_id]
    accepted = json.loads(
        (resolved_root / "raw" / "G0001.json").read_text(encoding="utf-8")
    )
    accepted_refs = accepted["page_evidence"]["screenshot_files"]
    assert all(reference.startswith("screenshots/G0001/") for reference in accepted_refs)
    assert all((resolved_root / reference).is_file() for reference in accepted_refs)
    assert ".worker-staging" not in json.dumps(accepted)
    assert not (resolved_root / ".worker-staging").exists()
    async with sessions() as db:
        stored = await db.get(GaojixingCollectionRun, job_id)
        assert stored is not None
        assert stored.status == GaojixingCollectionRunStatus.REVIEWING.value

    params = {
        "sourceMode": "project_archive",
        "projectRoot": str(resolved_root),
        "questionBankPath": str(resolved_root / "question-bank.json"),
    }
    batch = await execute_gaojixing_doubao_batch([], params)
    certification = await execute_gaojixing_batch_certification(
        [{"raw": batch}], params
    )
    assert batch["status"] == "completed"
    assert certification["status"] == "certified"
    async with sessions() as db:
        assert await mark_collection_succeeded(db, workflow_run_id=run_id) is True
        await db.commit()
        stored = await db.get(GaojixingCollectionRun, job_id)
        assert stored is not None
        assert stored.status == GaojixingCollectionRunStatus.SUCCEEDED.value


class _CaptchaThenRecoveredDriver(_FakeEvidenceDriver):
    async def collect(self, *, question_id: str, question: str) -> dict:
        if self.collected:
            return await super().collect(question_id=question_id, question=question)
        self.collected.append(question_id)
        screenshot = self.project_root / "screenshots" / f"{question_id}_captcha.png"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        screenshot.write_bytes(b"captcha")
        return {
            "id": question_id,
            "question": question,
            "status": "verification_required",
            "verification": {
                "kind": "captcha",
                "pageMarkerDetected": True,
                "screenshotPath": screenshot.relative_to(self.project_root).as_posix(),
            },
        }


class _PhaseGateDriver(_FakeEvidenceDriver):
    def __init__(self, project_root):
        super().__init__(project_root)
        self.second_phase1_ready = __import__("asyncio").Event()
        self.release_second_phase1 = __import__("asyncio").Event()

    async def collect(self, *, question_id: str, question: str) -> dict:
        self.collected.append(question_id)
        capture = self._capture(question_id, question)
        if question_id == "G0002":
            self.second_phase1_ready.set()
            await self.release_second_phase1.wait()
        return capture


@pytest.mark.asyncio
async def test_phase2_gate_rechecks_every_passed_phase1_raw_digest(
    db_engine, tmp_path
):
    import asyncio

    from backend.models.gaojixing_collection import GaojixingCollectionRun
    from backend.services.gaojixing_collection_service import ensure_collection
    from backend.workflow.gaojixing_collection_runner import run_collection_job

    run_id = "run-gjx-phase-gate"
    signing_key = "test-signing-key"
    staged = stage_managed_question_batch(
        _question_bank(),
        filename="questions.json",
        run_id=run_id,
        storage_root=tmp_path,
        signing_key=signing_key,
    )
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as db:
        db.add(_workflow_run(run_id))
        job = await ensure_collection(
            db,
            workflow_run_id=run_id,
            node_id="batch::tool",
            question_batch_ref=staged.question_batch_ref,
            storage_root=tmp_path,
            signing_key=signing_key,
            dispatch=lambda _job_id: None,
        )
        job_id = job.id
        await commit_session(db)

    driver = _PhaseGateDriver(tmp_path / "unused")

    def driver_factory(attempt_root):
        driver.project_root = attempt_root
        return driver

    task = asyncio.create_task(
        run_collection_job(
            job_id,
            session_factory=sessions,
            driver_factory=driver_factory,
            schedule_resume=lambda _run_id: None,
            storage_root=tmp_path,
            signing_key=signing_key,
        )
    )
    await driver.second_phase1_ready.wait()
    raw = tmp_path / "runs" / run_id / "raw" / "G0001.json"
    assert raw.is_file()
    raw.write_bytes(b'{"tampered":true}')
    driver.release_second_phase1.set()

    assert await task == "failed"
    assert driver.collected == ["G0001", "G0002"]
    async with sessions() as db:
        failed = await db.get(GaojixingCollectionRun, job_id)
        assert failed is not None
        assert failed.failure == {
            "code": "phase1-evidence-invalid",
            "questionId": "G0001",
        }


@pytest.mark.asyncio
async def test_captcha_waits_with_opaque_artifact_and_resume_never_reasks_question(
    db_engine, tmp_path
):
    from backend.models.gaojixing_collection import (
        GaojixingCollectionRun,
        GaojixingCollectionRunStatus,
    )
    from backend.services.gaojixing_collection_service import (
        ensure_collection,
        resume_collection,
    )
    from backend.workflow.gaojixing_collection_runner import run_collection_job

    run_id = "run-gjx-captcha"
    signing_key = "test-signing-key"
    staged = stage_managed_question_batch(
        _question_bank(),
        filename="questions.json",
        run_id=run_id,
        storage_root=tmp_path,
        signing_key=signing_key,
    )
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as db:
        db.add(_workflow_run(run_id))
        job = await ensure_collection(
            db,
            workflow_run_id=run_id,
            node_id="batch::tool",
            question_batch_ref=staged.question_batch_ref,
            storage_root=tmp_path,
            signing_key=signing_key,
            dispatch=lambda _job_id: None,
        )
        job_id = job.id
        await commit_session(db)

    project_root = tmp_path / "runs" / run_id
    driver = _CaptchaThenRecoveredDriver(tmp_path / "unused")

    def driver_factory(attempt_root):
        driver.project_root = attempt_root
        return driver

    first = await run_collection_job(
        job_id,
        session_factory=sessions,
        driver_factory=driver_factory,
        schedule_resume=lambda _run_id: None,
        storage_root=tmp_path,
        signing_key=signing_key,
    )
    assert first == "waiting_verification"
    async with sessions() as db:
        waiting = await db.get(GaojixingCollectionRun, job_id)
        assert waiting is not None
        assert waiting.status == GaojixingCollectionRunStatus.WAITING_VERIFICATION.value
        assert waiting.waiting_artifact_ref is not None
        assert waiting.waiting_artifact_ref.startswith(
            "run-artifact:verification/G0001/"
        )
        assert str(tmp_path) not in waiting.waiting_artifact_ref
        verification_path = (
            project_root / waiting.waiting_artifact_ref.removeprefix("run-artifact:")
        )
        assert verification_path.read_bytes() == b"captcha"

    dispatched: list[str] = []
    async with sessions() as db:
        await resume_collection(db, job_id=job_id, dispatch=dispatched.append)
        assert dispatched == []
        await commit_session(db)
    assert dispatched == [job_id]

    second = await run_collection_job(
        job_id,
        session_factory=sessions,
        driver_factory=driver_factory,
        schedule_resume=lambda _run_id: None,
        storage_root=tmp_path,
        signing_key=signing_key,
    )
    assert second == "workflow_resume_scheduled"
    assert driver.collected.count("G0001") == 1
    assert driver.inspected == ["G0001"]


class _BlockingDriver(_FakeEvidenceDriver):
    def __init__(self, project_root):
        super().__init__(project_root)
        self.started = __import__("asyncio").Event()
        self.release = __import__("asyncio").Event()

    async def collect(self, *, question_id: str, question: str) -> dict:
        self.collected.append(question_id)
        capture = self._capture(question_id, question)
        self.started.set()
        await self.release.wait()
        return capture


@pytest.mark.asyncio
async def test_replaced_fencing_token_prevents_old_worker_from_writing_raw(
    db_engine, tmp_path
):
    from backend.models.gaojixing_collection import (
        GAOJIXING_GLOBAL_LEASE_ID,
        GaojixingCollectionRun,
        GaojixingQuestionCheckpoint,
        GaojixingQuestionStatus,
        GaojixingRuntimeLease,
    )
    from backend.services.gaojixing_collection_service import ensure_collection
    from backend.workflow.gaojixing_collection_runner import run_collection_job

    run_id = "run-gjx-fenced-raw"
    signing_key = "test-signing-key"
    staged = stage_managed_question_batch(
        _question_bank(),
        filename="questions.json",
        run_id=run_id,
        storage_root=tmp_path,
        signing_key=signing_key,
    )
    sessions = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as db:
        db.add(_workflow_run(run_id))
        job = await ensure_collection(
            db,
            workflow_run_id=run_id,
            node_id="batch::tool",
            question_batch_ref=staged.question_batch_ref,
            storage_root=tmp_path,
            signing_key=signing_key,
            dispatch=lambda _job_id: None,
        )
        job_id = job.id
        await commit_session(db)

    project_root = tmp_path / "runs" / run_id
    driver = _BlockingDriver(tmp_path / "unused")

    def driver_factory(attempt_root):
        driver.project_root = attempt_root
        return driver

    task = __import__("asyncio").create_task(
        run_collection_job(
            job_id,
            session_factory=sessions,
            driver_factory=driver_factory,
            schedule_resume=lambda _run_id: None,
            storage_root=tmp_path,
            signing_key=signing_key,
        )
    )
    await driver.started.wait()
    async with sessions() as db:
        job = await db.get(GaojixingCollectionRun, job_id)
        lease = await db.get(GaojixingRuntimeLease, GAOJIXING_GLOBAL_LEASE_ID)
        assert job is not None and lease is not None
        replacement_token = int(job.lease_fencing_token or 0) + 1
        job.lease_owner = "replacement-worker"
        job.lease_fencing_token = replacement_token
        lease.owner = "replacement-worker"
        lease.collection_run_id = job_id
        lease.fencing_token = replacement_token
        await db.commit()
    winner = project_root / "screenshots" / "G0001" / "winner_01_顶部.png"
    winner.parent.mkdir(parents=True, exist_ok=True)
    winner.write_bytes(b"replacement-winner")
    driver.release.set()

    assert await task == "lease_lost"
    assert not (project_root / "raw" / "G0001.json").exists()
    assert winner.read_bytes() == b"replacement-winner"
    assert [
        path.relative_to(project_root).as_posix()
        for path in (project_root / "screenshots").rglob("*.png")
    ] == ["screenshots/G0001/winner_01_顶部.png"]
    assert not (project_root / ".worker-staging").exists()
    async with sessions() as db:
        checkpoint = await db.scalar(
            select(GaojixingQuestionCheckpoint).where(
                GaojixingQuestionCheckpoint.collection_run_id == job_id,
                GaojixingQuestionCheckpoint.question_id == "G0001",
            )
        )
        assert checkpoint is not None
        assert checkpoint.status == GaojixingQuestionStatus.IN_PROGRESS.value
        assert checkpoint.raw_digest is None
