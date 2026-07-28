"""Readable names for data sources materialized by workflow record sinks."""

from backend.schemas.workflow import CompiledWorkflowNode
from backend.workflow.opencli_hda_tracer import (
    _workflow_source_config,
    _workflow_source_display_name,
)


def test_workflow_source_display_uses_the_canvas_label_not_the_runtime_path() -> None:
    node = CompiledWorkflowNode(
        id="ashare-market-intelligence-sources::source-finance-news",
        kind="source",
        capability="fetch",
        params={"sourceGroup": "finance-news"},
        runtime={"display_name": "新浪财经新闻"},
    )

    assert _workflow_source_display_name(node) == "新浪财经新闻 · 工作流扫描数据源"
    config = _workflow_source_config(node, workflow_id="workflow-1", run_id="run-1")
    assert config["sourceNodeId"] == node.id


def test_workflow_source_config_preserves_identity_when_moved_into_a_source_pool() -> None:
    node = CompiledWorkflowNode(
        id="source-pool-finance-rss::rss-federal-reserve",
        kind="source",
        capability="fetch",
        params={
            "sourceGroup": "macro-policy",
            "sourceKey": "rss-federal-reserve",
        },
        runtime={"display_name": "美联储 · 政策与公告"},
    )

    config = _workflow_source_config(node, workflow_id="workflow-1", run_id="run-1")

    assert config["sourceNodeId"] == "rss-federal-reserve"
    assert config["runtimeNodeId"] == node.id
