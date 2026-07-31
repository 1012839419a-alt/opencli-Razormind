"""Core Kats smoke check for the isolated Python 3.10 environment."""

from __future__ import annotations

import math

from engine import KatsRuntime


def main() -> None:
    runtime = KatsRuntime()
    series = [
        {
            "time": f"2025-01-{index + 1:02d}",
            "value": 20 + index * 0.3 + math.sin(index / 3),
        }
        for index in range(28)
    ]
    common = {"series": series, "timeField": "time", "valueField": "value", "freq": "D"}

    forecast = runtime.execute(
        "forecast",
        [],
        {
            **common,
            "algorithm": "arima",
            "steps": 3,
            "modelParams": {"p": 1, "d": 1, "q": 1},
        },
    )
    features = runtime.execute(
        "features",
        [],
        {**common, "selectedFeatures": ["length", "mean"]},
    )
    decomposition = runtime.execute(
        "decompose",
        [],
        {
            **common,
            "method": "STL",
            "decomposition": "additive",
            "decompositionParams": {"period": 7},
        },
    )
    detection = runtime.execute(
        "detect",
        [],
        {**common, "algorithm": "cusum"},
    )

    assert len(forecast["data"]) == 3
    assert features["data"]["length"] == 28
    assert set(decomposition["data"]) == {"trend", "seasonal", "rem"}
    assert isinstance(detection["data"], list)
    print("kats core smoke: forecast/features/decompose/detect passed")


if __name__ == "__main__":
    main()
