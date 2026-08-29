import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.config import WorkbenchRepositoryConfiguration
from backend.models.identity import User, Workspace
from backend.models.workbench import (
    WorkbenchProposal,
    WorkbenchRepository,
    WorkbenchThread,
    WorkbenchTurn,
    WorkbenchTurnEvent,
)
from backend.schemas.workbench import WorkbenchTurnCreate
from backend.services.workbench_service import (
    WorkbenchError,
    _terminal_result,
    append_turn_event,
    confirm_proposal,
    create_turn,
    event_read,
    get_thread,
    list_repositories,
)


async def _turn(db_session):
    user = User(subject="workbench-user")
    workspace = Workspace(name="Workbench", slug="workbench")
    db_session.add_all((user, workspace))
    await db_session.flush()
    repository = WorkbenchRepository(
        workspace_id=workspace.id,
        name="admin",
        repository_path="/server/repos/admin",
        base_ref="refs/heads/main",
        worktree_root="/server/worktrees",
        execution_node_url="http://edge-1:19823",
        shared_filesystem_id="workspace-volume-1",
    )
    db_session.add(repository)
    await db_session.flush()
    thread = WorkbenchThread(
        workspace_id=workspace.id,
        repository_id=repository.id,
        created_by_user_id=user.id,
        title="Operator conversation",
    )
    db_session.add(thread)
    await db_session.flush()
    turn = WorkbenchTurn(
        thread_id=thread.id,
        workspace_id=workspace.id,
        sequence=1,
        request_id="request-1",
        requirement="Update the documentation parser",
        operations_agent_id="runtime-1",
        published_version=4,
        profile_version=2,
        runtime_type="pi",
        workflow="coding",
        base_sha="a" * 40,
        worktree_path="/server/worktrees/turn-1",
    )
    db_session.add(turn)
    await db_session.flush()
    return turn


async def test_append_turn_event_allocates_monotonic_sequence_and_redacts(db_session):
    turn = await _turn(db_session)

    first = await append_turn_event(
        db_session,
        turn=turn,
        event_type="tool_call",
        payload={"name": "write", "args": {"api_token": "do-not-persist", "path": "src/a.py"}},
    )
    second = await append_turn_event(
        db_session,
        turn=turn,
        event_type="text",
        payload={"text": "authorization=inline-secret"},
    )
    await db_session.commit()

    stored = list(
        await db_session.scalars(
            select(WorkbenchTurnEvent)
            .where(WorkbenchTurnEvent.turn_id == turn.id)
            .order_by(WorkbenchTurnEvent.sequence)
        )
    )
    assert [event.sequence for event in stored] == [1, 2]
    assert first.event_id != second.event_id
    assert stored[0].payload["args"]["api_token"] == "[REDACTED]"
    assert stored[1].payload["text"] == "authorization=[REDACTED]"
    assert event_read(stored[1]).event_type == "text"


async def test_append_turn_event_bounds_large_runtime_output(db_session):
    turn = await _turn(db_session)

    event = await append_turn_event(
        db_session,
        turn=turn,
        event_type="tool_result",
        payload={"result": "x" * 20_000},
    )

    assert event.payload["result"].endswith("…[truncated]")
    assert len(event.payload["result"].encode("utf-8")) < 9_000


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _checkpoint(
    repository_path: Path,
    isolated_path: Path,
    base_sha: str,
    changes: dict[str, str],
) -> str:
    _git(repository_path, "worktree", "add", "--detach", str(isolated_path), base_sha)
    try:
        for relative_path, contents in changes.items():
            path = isolated_path / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8")
        _git(isolated_path, "add", "-A")
        tree_sha = _git(isolated_path, "write-tree")
        return _git(
            isolated_path,
            "commit-tree",
            tree_sha,
            "-p",
            base_sha,
            "-m",
            "proposal",
        )
    finally:
        _git(repository_path, "worktree", "remove", "--force", str(isolated_path))


async def test_confirmation_applies_only_controller_checkpoint_after_sha_recheck(
    db_session, tmp_path
):
    repository_path = tmp_path / "repository"
    repository_path.mkdir()
    _git(repository_path, "init", "-b", "main")
    _git(repository_path, "config", "user.name", "Test")
    _git(repository_path, "config", "user.email", "test@example.invalid")
    (repository_path / "message.txt").write_text("before\n", encoding="utf-8")
    _git(repository_path, "add", "message.txt")
    _git(repository_path, "commit", "-m", "base")
    base_sha = _git(repository_path, "rev-parse", "HEAD")

    isolated_path = tmp_path / "isolated"
    _git(repository_path, "worktree", "add", "--detach", str(isolated_path), base_sha)
    (isolated_path / "message.txt").write_text("after\n", encoding="utf-8")
    _git(isolated_path, "add", "message.txt")
    tree_sha = _git(isolated_path, "write-tree")
    checkpoint_sha = _git(
        isolated_path,
        "commit-tree",
        tree_sha,
        "-p",
        base_sha,
        "-m",
        "proposal",
    )
    _git(repository_path, "worktree", "remove", "--force", str(isolated_path))

    user = User(subject="checkpoint-user")
    workspace = Workspace(name="Checkpoint", slug="checkpoint")
    db_session.add_all((user, workspace))
    await db_session.flush()
    repository = WorkbenchRepository(
        workspace_id=workspace.id,
        name="controller-repository",
        repository_path=str(repository_path),
        base_ref="refs/heads/main",
        worktree_root=str(tmp_path / "worktrees"),
        execution_node_url="http://edge-1:19823",
        shared_filesystem_id="workspace-volume-1",
    )
    db_session.add(repository)
    await db_session.flush()
    thread = WorkbenchThread(
        workspace_id=workspace.id,
        repository_id=repository.id,
        created_by_user_id=user.id,
    )
    db_session.add(thread)
    await db_session.flush()
    turn = WorkbenchTurn(
        thread_id=thread.id,
        workspace_id=workspace.id,
        sequence=1,
        request_id="checkpoint-request",
        requirement="Change the message",
        operations_agent_id="runtime-1",
        published_version=1,
        profile_version=1,
        runtime_type="pi",
        workflow="coding",
        base_sha=base_sha,
        worktree_path=str(isolated_path),
        status="proposed",
    )
    db_session.add(turn)
    await db_session.flush()
    proposal = WorkbenchProposal(
        workspace_id=workspace.id,
        repository_id=repository.id,
        turn_id=turn.id,
        base_sha=base_sha,
        checkpoint_sha=checkpoint_sha,
        diff="diff --git a/message.txt b/message.txt",
        modified_files=["message.txt"],
        tests=[],
    )
    db_session.add(proposal)
    await db_session.flush()

    assert (repository_path / "message.txt").read_text(encoding="utf-8") == "before\n"
    applied = await confirm_proposal(
        db_session,
        workspace_id=workspace.id,
        thread_id=thread.id,
        proposal_id=proposal.id,
        user_id=user.id,
    )

    assert applied.status == "applied"
    assert turn.status == "applied"
    assert (repository_path / "message.txt").read_text(encoding="utf-8") == "after\n"
    assert _git(repository_path, "rev-parse", "HEAD") == checkpoint_sha
    assert _git(repository_path, "symbolic-ref", "--quiet", "HEAD") == "refs/heads/main"
    assert _git(repository_path, "status", "--porcelain") == ""

    second_checkpoint_sha = _checkpoint(
        repository_path,
        tmp_path / "isolated-second",
        checkpoint_sha,
        {"second.txt": "second proposal\n"},
    )
    second_turn = WorkbenchTurn(
        thread_id=thread.id,
        workspace_id=workspace.id,
        sequence=2,
        request_id="checkpoint-request-2",
        requirement="Add the second file",
        operations_agent_id="runtime-1",
        published_version=1,
        profile_version=1,
        runtime_type="pi",
        workflow="coding",
        base_sha=checkpoint_sha,
        worktree_path=str(tmp_path / "isolated-second"),
        status="proposed",
    )
    db_session.add(second_turn)
    await db_session.flush()
    second_proposal = WorkbenchProposal(
        workspace_id=workspace.id,
        repository_id=repository.id,
        turn_id=second_turn.id,
        base_sha=checkpoint_sha,
        checkpoint_sha=second_checkpoint_sha,
        diff="diff --git a/second.txt b/second.txt",
        modified_files=["second.txt"],
        tests=[],
    )
    db_session.add(second_proposal)
    await db_session.flush()

    await confirm_proposal(
        db_session,
        workspace_id=workspace.id,
        thread_id=thread.id,
        proposal_id=second_proposal.id,
        user_id=user.id,
    )

    assert _git(repository_path, "rev-parse", "HEAD") == second_checkpoint_sha
    assert _git(repository_path, "status", "--porcelain") == ""

    blocked_checkpoint_sha = _checkpoint(
        repository_path,
        tmp_path / "isolated-blocked",
        second_checkpoint_sha,
        {"message.txt": "blocked proposal\n"},
    )
    blocked_turn = WorkbenchTurn(
        thread_id=thread.id,
        workspace_id=workspace.id,
        sequence=3,
        request_id="checkpoint-request-3",
        requirement="Blocked proposal",
        operations_agent_id="runtime-1",
        published_version=1,
        profile_version=1,
        runtime_type="pi",
        workflow="coding",
        base_sha=second_checkpoint_sha,
        worktree_path=str(tmp_path / "isolated-blocked"),
        status="proposed",
    )
    db_session.add(blocked_turn)
    await db_session.flush()
    blocked_proposal = WorkbenchProposal(
        workspace_id=workspace.id,
        repository_id=repository.id,
        turn_id=blocked_turn.id,
        base_sha=second_checkpoint_sha,
        checkpoint_sha=blocked_checkpoint_sha,
        diff="diff --git a/message.txt b/message.txt",
        modified_files=["message.txt"],
        tests=[],
    )
    db_session.add(blocked_proposal)
    await db_session.flush()

    _git(repository_path, "checkout", "-b", "other")
    with pytest.raises(WorkbenchError, match="target ref is not checked out"):
        await confirm_proposal(
            db_session,
            workspace_id=workspace.id,
            thread_id=thread.id,
            proposal_id=blocked_proposal.id,
            user_id=user.id,
        )
    await db_session.refresh(blocked_proposal)
    assert blocked_proposal.status == "pending_confirmation"
    assert "target ref is not checked out" in blocked_proposal.error_message

    _git(repository_path, "checkout", "main")
    (repository_path / "message.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(WorkbenchError, match="local changes"):
        await confirm_proposal(
            db_session,
            workspace_id=workspace.id,
            thread_id=thread.id,
            proposal_id=blocked_proposal.id,
            user_id=user.id,
        )
    await db_session.refresh(blocked_proposal)
    assert blocked_proposal.status == "pending_confirmation"
    assert "local changes" in blocked_proposal.error_message
    _git(repository_path, "checkout", "--", "message.txt")
    _git(repository_path, "merge", "--ff-only", blocked_checkpoint_sha)
    recovered = await confirm_proposal(
        db_session,
        workspace_id=workspace.id,
        thread_id=thread.id,
        proposal_id=blocked_proposal.id,
        user_id=user.id,
    )
    assert recovered.status == "applied"
    assert recovered.turn.status == "applied"
    assert _git(repository_path, "rev-parse", "HEAD") == blocked_checkpoint_sha
    assert _git(repository_path, "status", "--porcelain") == ""


async def test_turn_creation_pins_server_selected_runtime_and_is_idempotent(
    db_session, monkeypatch
):
    first_turn = await _turn(db_session)
    thread = await get_thread(db_session, first_turn.workspace_id, first_turn.thread_id)
    selected_agent = SimpleNamespace(id="pinned-runtime", disabled=False)
    selected_version = SimpleNamespace(version=9)
    selected_profile = SimpleNamespace(version=4, mode="suggest_changes")
    selected_binding = SimpleNamespace(
        runtime="pi",
        workflow="coding",
        agent_url="http://edge-1:19823",
        execution_node_url="http://edge-1:19823",
        shared_filesystem_id="workspace-volume-1",
    )

    async def select_runtime(*_args, **_kwargs):
        return selected_agent, selected_version, selected_profile, selected_binding

    async def resolve_base(*_args, **_kwargs):
        return "c" * 40

    async def create_worktree(*_args, **_kwargs):
        return "/controller/worktrees/turn-2"

    monkeypatch.setattr("backend.services.workbench_service._select_runtime", select_runtime)
    monkeypatch.setattr("backend.services.workbench_service._resolve_base_sha", resolve_base)
    monkeypatch.setattr("backend.services.workbench_service._create_worktree", create_worktree)
    body = WorkbenchTurnCreate(
        runtime_id="browser-selected-identity-only",
        requirement="Implement the bounded fix",
        request_id="request-2",
    )

    created = await create_turn(
        db_session,
        thread=thread,
        body=body,
        user_id="operator-id",
    )
    duplicate = await create_turn(
        db_session,
        thread=thread,
        body=body,
        user_id="operator-id",
    )

    assert created.id == duplicate.id
    assert created.sequence == 2
    assert created.operations_agent_id == "pinned-runtime"
    assert created.published_version == 9
    assert created.profile_version == 4
    assert created.runtime_type == "pi"
    assert created.base_sha == "c" * 40


async def test_server_configuration_reconciles_a_repository_mapping(db_session, monkeypatch):
    user = User(subject="configured-workbench-user")
    workspace = Workspace(name="Configured Workbench", slug="configured-workbench")
    db_session.add_all((user, workspace))
    await db_session.flush()
    configuration = WorkbenchRepositoryConfiguration(
        workspace_id=workspace.id,
        name="server-configured-repo",
        repository_path="C:/repositories/admin",
        base_ref="refs/heads/main",
        worktree_root="C:/worktrees",
        execution_node_url="http://edge-1:19823",
        shared_filesystem_id="workspace-volume-1",
    )
    monkeypatch.setattr(
        "backend.services.workbench_service.get_settings",
        lambda: SimpleNamespace(workbench_repositories=[configuration]),
    )

    repositories = await list_repositories(db_session, workspace.id)

    assert [(repository.name, repository.base_ref) for repository in repositories] == [
        ("server-configured-repo", "refs/heads/main")
    ]
    assert repositories[0].execution_node_url == "http://edge-1:19823"


async def test_turn_creation_rejects_a_runtime_on_a_different_shared_filesystem(
    db_session, monkeypatch
):
    first_turn = await _turn(db_session)
    thread = await get_thread(db_session, first_turn.workspace_id, first_turn.thread_id)
    binding = SimpleNamespace(
        runtime="pi",
        workflow="coding",
        agent_url="http://edge-2:19823",
        execution_node_url="http://edge-2:19823",
        shared_filesystem_id="workspace-volume-2",
    )

    async def select_runtime(*_args, **_kwargs):
        return (
            SimpleNamespace(id="runtime-2", disabled=False),
            SimpleNamespace(version=1),
            SimpleNamespace(version=1, mode="suggest_changes"),
            binding,
        )

    monkeypatch.setattr("backend.services.workbench_service._select_runtime", select_runtime)
    with pytest.raises(WorkbenchError, match="different execution node"):
        await create_turn(
            db_session,
            thread=thread,
            body=WorkbenchTurnCreate(
                runtime_id="runtime-2",
                requirement="Do not dispatch this worktree",
                request_id="different-filesystem",
            ),
            user_id="operator-id",
        )


def test_terminal_result_parses_fenced_codex_text_and_validates_evidence():
    result = _terminal_result(
        {
            "type": "done",
            "text": (
                "Completed.\n```json\n"
                '{"patch":"diff --git a/a.txt b/a.txt\\n","tests":['
                '{"command":"pytest tests/unit/test_a.py","outcome":"passed","summary":"ok"},'
                '{"command":7,"outcome":"passed"}]}\n```'
            ),
        }
    )

    assert result["patch"] == "diff --git a/a.txt b/a.txt\n"
    assert result["tests"] == [
        {
            "command": "pytest tests/unit/test_a.py",
            "outcome": "passed",
            "summary": "ok",
        }
    ]
