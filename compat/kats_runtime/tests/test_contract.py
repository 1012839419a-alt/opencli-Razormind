from fastapi.testclient import TestClient

from app import create_app
from engine import (
    CONTRACT_VERSION,
    DETECTOR_TARGETS,
    FORECAST_TARGETS,
    PUBLIC_TARGETS,
    KatsRuntime,
)


def test_runtime_catalog_covers_every_kats_feature_family():
    runtime = KatsRuntime()
    capabilities = runtime.capabilities()

    assert CONTRACT_VERSION == "opencli.kats.runtime.v1"
    assert set(capabilities["operations"]) == {
        "forecast",
        "detect",
        "features",
        "decompose",
        "backtest",
        "tune",
        "simulate",
        "advanced",
    }
    assert set(capabilities["forecastAlgorithms"]) == set(FORECAST_TARGETS)
    assert set(capabilities["detectors"]) == set(DETECTOR_TARGETS)
    assert set(capabilities["publicTargets"]) == set(PUBLIC_TARGETS)
    assert {
        "ensemble.kats",
        "global.model",
        "reconciliation.temporal_hierarchy",
        "meta.model_select",
        "backtest.cross_validation",
        "tuning.nevergrad",
        "simulator",
    } <= set(PUBLIC_TARGETS)


def test_request_limit_rejects_the_body_before_validation() -> None:
    response = TestClient(create_app(max_request_bytes=64)).post(
        "/v1/execute",
        json={"operation": "simulate", "inputItems": [{"padding": "x" * 128}]},
    )

    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "request.too_large",
        "message": "The request body exceeds the configured request limit.",
        "details": {"maxBytes": 64},
    }
