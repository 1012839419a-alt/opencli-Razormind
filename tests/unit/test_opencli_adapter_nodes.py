from __future__ import annotations

from subprocess import CompletedProcess

from backend.workflow import opencli_adapter_nodes


def test_opencli_catalog_fails_closed_when_decoding_produces_no_stdout(monkeypatch) -> None:
    monkeypatch.setattr(opencli_adapter_nodes, "_resolve_opencli_bin", lambda: "opencli")
    monkeypatch.setattr(
        opencli_adapter_nodes.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args, 0, stdout=None, stderr=None),
    )
    opencli_adapter_nodes._load_opencli_catalog.cache_clear()
    try:
        assert opencli_adapter_nodes._load_opencli_catalog() == ()
    finally:
        opencli_adapter_nodes._load_opencli_catalog.cache_clear()
