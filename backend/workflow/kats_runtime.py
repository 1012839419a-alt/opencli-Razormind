"""Kats time-series capability catalog and isolated runtime client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from backend.config import get_settings
from backend.schemas.workflow import (
    WorkflowCapabilityVersionPin,
    WorkflowToolCapability,
    WorkflowToolCapabilityExecutor,
    WorkflowToolCapabilityPort,
)

KATS_EXECUTOR_MODE = "kats_runtime"
KATS_NAME = "facebookresearch/kats"
KATS_VERSION = "0.2.0"
KATS_COMMIT = "4145be4e5c962a06f15e833830f134d7758a7467"
KATS_CONTRACT_VERSION = "opencli.kats.runtime.v1"
KATS_PACKAGE_VERSION = "0.1.0"


@dataclass(frozen=True)
class KatsCapabilitySpec:
    operation: str
    label: str
    description: str
    icon: str
    input_type: str
    output_type: str
    parameters: tuple[dict[str, Any], ...]

    @property
    def tool_id(self) -> str:
        return f"tool.timeseries.kats.{self.operation}"


_SERIES_PARAMETERS: tuple[dict[str, Any], ...] = (
    {
        "name": "series",
        "label": "时间序列 / Series",
        "type": "array",
        "required": False,
        "default": [],
        "description": "可直接提供 [{time, value}]；留空时读取上游节点输出。",
    },
    {
        "name": "timeField",
        "label": "时间字段 / Time field",
        "type": "string",
        "required": False,
        "default": "time",
    },
    {
        "name": "valueField",
        "label": "数值字段 / Value field",
        "type": "string",
        "required": False,
        "default": "value",
    },
    {
        "name": "freq",
        "label": "频率 / Frequency",
        "type": "string",
        "required": False,
        "default": "D",
        "description": "Pandas 频率，例如 D、H、W、MS。",
    },
)

_FORECAST_ALGORITHMS = (
    "arima",
    "sarima",
    "holtwinters",
    "theta",
    "prophet",
    "linear",
    "quadratic",
    "var",
    "bayesian_var",
    "stlf",
    "lstm",
    "ml_ar",
    "neuralprophet",
    "harmonic_regression",
    "simple_heuristic",
    "nowcasting",
    "nowcasting_plus",
)

_DETECTOR_ALGORITHMS = (
    "cusum",
    "bocpd",
    "robust_stat",
    "outlier",
    "multivariate",
    "trend_mk",
    "acf",
    "fft",
    "hourly_ratio",
    "dtw",
)

KATS_CAPABILITY_SPECS: tuple[KatsCapabilitySpec, ...] = (
    KatsCapabilitySpec(
        operation="forecast",
        label="Kats 预测",
        description="运行 Kats 经典、机器学习、神经网络和 Nowcasting 预测模型。",
        icon="ChartNoAxesCombined",
        input_type="timeSeries[]",
        output_type="forecast[]",
        parameters=(
            *_SERIES_PARAMETERS,
            {
                "name": "algorithm",
                "label": "模型 / Model",
                "type": "select",
                "required": True,
                "default": "arima",
                "options": list(_FORECAST_ALGORITHMS),
            },
            {
                "name": "steps",
                "label": "预测步数 / Steps",
                "type": "integer",
                "required": True,
                "default": 12,
                "minimum": 1,
                "maximum": 10000,
            },
            {
                "name": "modelParams",
                "label": "模型参数 / Model params",
                "type": "object",
                "required": False,
                "default": {"p": 1, "d": 1, "q": 1},
            },
            {
                "name": "fitParams",
                "label": "训练参数 / Fit params",
                "type": "object",
                "required": False,
                "default": {},
            },
            {
                "name": "predictParams",
                "label": "预测参数 / Predict params",
                "type": "object",
                "required": False,
                "default": {},
            },
        ),
    ),
    KatsCapabilitySpec(
        operation="detect",
        label="Kats 异常与变点检测",
        description="运行 CUSUM、BOCPD、稳健统计、离群、多变量、趋势和季节检测器。",
        icon="Activity",
        input_type="timeSeries[]",
        output_type="anomaly[]",
        parameters=(
            *_SERIES_PARAMETERS,
            {
                "name": "algorithm",
                "label": "检测器 / Detector",
                "type": "select",
                "required": True,
                "default": "cusum",
                "options": list(_DETECTOR_ALGORITHMS),
            },
            {
                "name": "constructorParams",
                "label": "构造参数 / Constructor params",
                "type": "object",
                "required": False,
                "default": {},
            },
            {
                "name": "detectorParams",
                "label": "检测参数 / Detector params",
                "type": "object",
                "required": False,
                "default": {},
            },
        ),
    ),
    KatsCapabilitySpec(
        operation="features",
        label="Kats 特征提取",
        description="提取 TsFeatures 的统计、STL、ACF/PACF、检测器及 Nowcasting 特征。",
        icon="ListTree",
        input_type="timeSeries[]",
        output_type="featureVector[]",
        parameters=(
            *_SERIES_PARAMETERS,
            {
                "name": "selectedFeatures",
                "label": "特征或特征组 / Features",
                "type": "array",
                "required": False,
                "default": [],
            },
            {
                "name": "featureParams",
                "label": "特征参数 / Feature params",
                "type": "object",
                "required": False,
                "default": {},
            },
        ),
    ),
    KatsCapabilitySpec(
        operation="decompose",
        label="Kats 时序分解",
        description="使用 STL 或 seasonal_decompose 拆分趋势、季节和残差。",
        icon="Split",
        input_type="timeSeries[]",
        output_type="timeSeriesComponents[]",
        parameters=(
            *_SERIES_PARAMETERS,
            {
                "name": "method",
                "label": "方法 / Method",
                "type": "select",
                "required": True,
                "default": "STL",
                "options": ["STL", "seasonal_decompose"],
            },
            {
                "name": "decomposition",
                "label": "分解模式 / Mode",
                "type": "select",
                "required": True,
                "default": "additive",
                "options": ["additive", "multiplicative"],
            },
            {
                "name": "decompositionParams",
                "label": "分解参数 / Params",
                "type": "object",
                "required": False,
                "default": {"period": 7},
            },
        ),
    ),
    KatsCapabilitySpec(
        operation="backtest",
        label="Kats 回测与评估",
        description="用 Kats 数据切分、预测模型和指标运行可复现回测。",
        icon="History",
        input_type="timeSeries[]",
        output_type="backtestResult[]",
        parameters=(
            *_SERIES_PARAMETERS,
            {
                "name": "algorithm",
                "label": "模型 / Model",
                "type": "select",
                "required": True,
                "default": "arima",
                "options": list(_FORECAST_ALGORITHMS[:13]),
            },
            {
                "name": "modelParams",
                "label": "模型参数 / Model params",
                "type": "object",
                "required": False,
                "default": {"p": 1, "d": 1, "q": 1},
            },
            {
                "name": "metrics",
                "label": "指标 / Metrics",
                "type": "array",
                "required": True,
                "default": ["smape", "mape"],
            },
            {
                "name": "trainFraction",
                "label": "训练集比例 / Train fraction",
                "type": "number",
                "required": True,
                "default": 0.8,
                "minimum": 0.1,
                "maximum": 0.95,
                "step": 0.05,
            },
        ),
    ),
    KatsCapabilitySpec(
        operation="tune",
        label="Kats 调参与模型选择",
        description="运行 Kats Grid、Random、Bayesian 或 Nevergrad 参数搜索，并用回测指标评分。",
        icon="SlidersHorizontal",
        input_type="timeSeries[]",
        output_type="parameterScore[]",
        parameters=(
            *_SERIES_PARAMETERS,
            {
                "name": "algorithm",
                "label": "模型 / Model",
                "type": "select",
                "required": True,
                "default": "arima",
                "options": list(_FORECAST_ALGORITHMS[:13]),
            },
            {
                "name": "searchMethod",
                "label": "搜索方法 / Search",
                "type": "select",
                "required": True,
                "default": "grid",
                "options": ["grid", "random", "bayes", "nevergrad"],
            },
            {
                "name": "parameterSpace",
                "label": "参数空间 / Parameter space",
                "type": "array",
                "required": True,
                "default": [
                    {"name": "p", "type": "choice", "values": [1, 2]},
                    {"name": "d", "type": "choice", "values": [0, 1]},
                    {"name": "q", "type": "choice", "values": [1, 2]},
                ],
            },
            {
                "name": "metric",
                "label": "目标指标 / Metric",
                "type": "string",
                "required": True,
                "default": "smape",
            },
            {
                "name": "trials",
                "label": "试验数 / Trials",
                "type": "integer",
                "required": False,
                "default": 12,
                "minimum": 1,
                "maximum": 1000,
            },
            {
                "name": "trainFraction",
                "label": "训练集比例 / Train fraction",
                "type": "number",
                "required": True,
                "default": 0.8,
                "minimum": 0.1,
                "maximum": 0.95,
                "step": 0.05,
            },
        ),
    ),
    KatsCapabilitySpec(
        operation="simulate",
        label="Kats 时间序列模拟",
        description="生成 ARIMA、趋势、季节、噪声、水平漂移和趋势漂移模拟序列。",
        icon="Waves",
        input_type="trigger",
        output_type="timeSeries[]",
        parameters=(
            {
                "name": "mode",
                "label": "模拟方式 / Mode",
                "type": "select",
                "required": True,
                "default": "components",
                "options": ["components", "arima", "level_shift", "trend_shift"],
            },
            {
                "name": "n",
                "label": "长度 / Length",
                "type": "integer",
                "required": True,
                "default": 240,
                "minimum": 5,
                "maximum": 100000,
            },
            {
                "name": "freq",
                "label": "频率 / Frequency",
                "type": "string",
                "required": True,
                "default": "D",
            },
            {
                "name": "start",
                "label": "开始时间 / Start",
                "type": "string",
                "required": False,
                "default": "2025-01-01",
            },
            {
                "name": "seed",
                "label": "随机种子 / Seed",
                "type": "integer",
                "required": False,
                "default": 17,
            },
            {
                "name": "simulationParams",
                "label": "模拟参数 / Params",
                "type": "object",
                "required": False,
                "default": {
                    "trend": 0.1,
                    "seasonality": 2.0,
                    "period": "7D",
                    "noise": 0.2,
                },
            },
        ),
    ),
    KatsCapabilitySpec(
        operation="advanced",
        label="Kats 高级公共 API",
        description=(
            "通过受限目标白名单调用 Kats 集成、GlobalModel、Nowcasting、"
            "Reconciliation、Meta-learning、检测器模型和高级工具。"
        ),
        icon="Braces",
        input_type="unknown",
        output_type="unknown",
        parameters=(
            *_SERIES_PARAMETERS,
            {
                "name": "target",
                "label": "公共目标 / Public target",
                "type": "string",
                "required": True,
                "default": "model.arima",
            },
            {
                "name": "constructor",
                "label": "构造参数 / Constructor",
                "type": "object",
                "required": False,
                "default": {
                    "data": {"$series": True},
                    "params": {
                        "$target": "params.arima",
                        "kwargs": {"p": 1, "d": 1, "q": 1},
                    },
                },
            },
            {
                "name": "calls",
                "label": "方法链 / Calls",
                "type": "array",
                "required": True,
                "default": [{"method": "fit"}, {"method": "predict", "kwargs": {"steps": 12}}],
            },
        ),
    ),
)

KATS_TOOL_IDS = frozenset(spec.tool_id for spec in KATS_CAPABILITY_SPECS)


def kats_tool_capabilities() -> list[WorkflowToolCapability]:
    version_pin = WorkflowCapabilityVersionPin(
        package="opencli-kats-runtime",
        packageVersion=KATS_PACKAGE_VERSION,
        capabilityVersion=KATS_CONTRACT_VERSION,
        provenance="verified",
    )
    return [
        WorkflowToolCapability(
            id=spec.tool_id,
            label=spec.label,
            description=spec.description,
            status="runnable",
            provider=KATS_NAME,
            inputPorts=[WorkflowToolCapabilityPort(name="in", type=spec.input_type)],
            outputPorts=[WorkflowToolCapabilityPort(name="out", type=spec.output_type)],
            executor=WorkflowToolCapabilityExecutor(
                mode=KATS_EXECUTOR_MODE,
                description="Calls the pinned, isolated Kats compatibility runtime.",
                params={"operation": spec.operation},
            ),
            versionPin=version_pin,
            tags=[
                "tool",
                "timeseries",
                "kats",
                spec.operation,
                "forecasting",
                "anomaly-detection",
            ],
            manifest={
                "schema": f"tool-capability.kats-{spec.operation}.v1",
                "runtime": {"binding": "workflow.external-tool.capability"},
                "resources": ["kats_runtime", "run_trace"],
                "permissions": ["runtime_tool_call"],
                "upstream": {
                    "repository": "https://github.com/facebookresearch/Kats",
                    "name": KATS_NAME,
                    "version": KATS_VERSION,
                    "commit": KATS_COMMIT,
                },
                "trace": {
                    "events": [
                        "tool_call_started",
                        "partial:outputItemCount",
                        "tool_call_completed",
                        "completed",
                    ]
                },
                "canvas": {"node": True},
                "nodeCatalog": {
                    "id": spec.tool_id,
                    "authority": "backend",
                    "origin": "tool-capability",
                    "category": "processing",
                    "kind": "action",
                    "capability": "store",
                },
                "presentation": {
                    "icon": spec.icon,
                    "parameters": list(spec.parameters),
                },
            },
        )
        for spec in KATS_CAPABILITY_SPECS
    ]


class KatsRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


async def execute_kats_operation(
    operation: str,
    input_items: list[dict[str, Any]],
    params: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.kats_runtime_timeout_seconds) as client:
            response = await client.post(
                f"{settings.kats_runtime_url.rstrip('/')}/v1/execute",
                json={
                    "operation": operation,
                    "inputItems": input_items,
                    "params": params,
                },
            )
    except (httpx.HTTPError, ValueError) as error:
        raise KatsRuntimeError(
            "kats_runtime_unavailable",
            "The pinned Kats runtime is unavailable.",
        ) from error

    try:
        payload = response.json()
    except ValueError as error:
        raise KatsRuntimeError(
            "kats_runtime_invalid_response",
            "The Kats runtime returned a non-JSON response.",
        ) from error

    if response.status_code >= 400:
        error = payload.get("error") if isinstance(payload, dict) else None
        error = error if isinstance(error, dict) else {}
        raise KatsRuntimeError(
            str(error.get("code") or "kats_runtime_failed"),
            str(error.get("message") or "The Kats operation failed."),
            error.get("details") if isinstance(error.get("details"), dict) else {},
        )
    if not isinstance(payload, dict):
        raise KatsRuntimeError(
            "kats_runtime_invalid_response",
            "The Kats runtime returned an invalid contract.",
        )
    engine = payload.get("engine")
    if (
        payload.get("contractVersion") != KATS_CONTRACT_VERSION
        or not isinstance(engine, dict)
        or engine.get("name") != KATS_NAME
        or engine.get("version") != KATS_VERSION
        or engine.get("commit") != KATS_COMMIT
    ):
        raise KatsRuntimeError(
            "kats_runtime_pin_mismatch",
            "The Kats runtime does not match the pinned engine identity.",
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise KatsRuntimeError(
            "kats_runtime_invalid_response",
            "The Kats runtime response is missing its result object.",
        )
    return result
