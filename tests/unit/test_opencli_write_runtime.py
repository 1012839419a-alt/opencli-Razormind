from backend.schemas.workflow import CompiledWorkflowNode, WorkflowAgentPermissions
from backend.workflow.opencli_hda_tracer import _opencli_mutation_block_reason
from backend.workflow.runtime_registry import OPENCLI_BINDING_ID


def _compiled_write_node(*, proposal_state: str) -> CompiledWorkflowNode:
    return CompiledWorkflowNode(
        id="tool-twitter-post",
        kind="action",
        capability="store",
        params={
            "site": "twitter",
            "command": "post",
            "args": {"text": "hello"},
            "opencliAccess": "write",
            "opencliAdapterNodeId": "opencli.adapter.twitter.post",
        },
        runtime={
            "proposal_state": proposal_state,
            "binding": {"binding_id": OPENCLI_BINDING_ID},
        },
    )


def test_opencli_write_requires_explicit_node_acceptance():
    reason = _opencli_mutation_block_reason(
        _compiled_write_node(proposal_state="proposed"),
        WorkflowAgentPermissions(canMutateExternalSites=True),
    )

    assert reason is not None
    assert reason.code == "opencli_write_approval_required"
    assert reason.details["proposalState"] == "proposed"


def test_opencli_write_requires_project_mutation_permission():
    reason = _opencli_mutation_block_reason(
        _compiled_write_node(proposal_state="accepted"),
        WorkflowAgentPermissions(canMutateExternalSites=False),
    )

    assert reason is not None
    assert reason.code == "opencli_write_permission_required"
    assert reason.details["requiredPermission"] == "canMutateExternalSites"


def test_opencli_write_runs_after_acceptance_and_permission():
    reason = _opencli_mutation_block_reason(
        _compiled_write_node(proposal_state="accepted"),
        WorkflowAgentPermissions(canMutateExternalSites=True),
    )

    assert reason is None
