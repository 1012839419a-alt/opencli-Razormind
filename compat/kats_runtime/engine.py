"""Small HTTP-facing adapter over the public facebookresearch/Kats APIs."""

from __future__ import annotations

import dataclasses
import importlib
import math
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any

KATS_NAME = "facebookresearch/kats"
KATS_VERSION = "0.2.0"
KATS_COMMIT = "4145be4e5c962a06f15e833830f134d7758a7467"
CONTRACT_VERSION = "opencli.kats.runtime.v1"
MAX_POINTS = 100_000
MAX_CALLS = 20

FORECAST_TARGETS: dict[str, tuple[str, str, str]] = {
    "arima": ("kats.models.arima", "ARIMAModel", "ARIMAParams"),
    "sarima": ("kats.models.sarima", "SARIMAModel", "SARIMAParams"),
    "holtwinters": (
        "kats.models.holtwinters",
        "HoltWintersModel",
        "HoltWintersParams",
    ),
    "theta": ("kats.models.theta", "ThetaModel", "ThetaParams"),
    "prophet": ("kats.models.prophet", "ProphetModel", "ProphetParams"),
    "linear": ("kats.models.linear_model", "LinearModel", "LinearModelParams"),
    "quadratic": (
        "kats.models.quadratic_model",
        "QuadraticModel",
        "QuadraticModelParams",
    ),
    "var": ("kats.models.var", "VARModel", "VARParams"),
    "bayesian_var": (
        "kats.models.bayesian_var",
        "BayesianVAR",
        "BayesianVARParams",
    ),
    "stlf": ("kats.models.stlf", "STLFModel", "STLFParams"),
    "lstm": ("kats.models.lstm", "LSTMModel", "LSTMParams"),
    "ml_ar": ("kats.models.ml_ar", "MLARModel", "MLARParams"),
    "neuralprophet": (
        "kats.models.neuralprophet",
        "NeuralProphetModel",
        "NeuralProphetParams",
    ),
    "harmonic_regression": (
        "kats.models.harmonic_regression",
        "HarmonicRegressionModel",
        "HarmonicRegressionParams",
    ),
    "simple_heuristic": (
        "kats.models.simple_heuristic_model",
        "SimpleHeuristicModel",
        "SimpleHeuristicModelParams",
    ),
    "nowcasting": (
        "kats.models.nowcasting.nowcasting",
        "NowcastingModel",
        "NowcastingParams",
    ),
    "nowcasting_plus": (
        "kats.models.nowcasting.nowcastingplus",
        "NowcastingPlusModel",
        "NowcastingParams",
    ),
}

DETECTOR_TARGETS: dict[str, tuple[str, str]] = {
    "cusum": ("kats.detectors.cusum_detection", "CUSUMDetector"),
    "bocpd": ("kats.detectors.bocpd", "BOCPDetector"),
    "robust_stat": ("kats.detectors.robust_stat_detection", "RobustStatDetector"),
    "outlier": ("kats.detectors.outlier", "OutlierDetector"),
    "multivariate": ("kats.detectors.outlier", "MultivariateAnomalyDetector"),
    "trend_mk": ("kats.detectors.trend_mk", "MKDetector"),
    "acf": ("kats.detectors.seasonality", "ACFDetector"),
    "fft": ("kats.detectors.seasonality", "FFTDetector"),
    "hourly_ratio": (
        "kats.detectors.hourly_ratio_detection",
        "HourlyRatioDetector",
    ),
    "dtw": ("kats.detectors.dtwcpd", "DTWCPDDetector"),
}

# Advanced jobs are deliberately reflective but not arbitrary: every import target
# and callable method is explicitly allowlisted here.
PUBLIC_TARGETS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    **{
        "model." + alias: (module, model, ("fit", "predict"))
        for alias, (module, model, _params) in FORECAST_TARGETS.items()
    },
    **{
        "params." + alias: (module, params, ())
        for alias, (module, _model, params) in FORECAST_TARGETS.items()
    },
    **{
        "detector." + alias: (module, target, ("detector", "fit_predict"))
        for alias, (module, target) in DETECTOR_TARGETS.items()
    },
    "ensemble.kats": (
        "kats.models.ensemble.kats_ensemble",
        "KatsEnsemble",
        ("fit", "predict"),
    ),
    "ensemble.median": (
        "kats.models.ensemble.median_ensemble",
        "MedianEnsembleModel",
        ("fit", "predict"),
    ),
    "ensemble.weighted_average": (
        "kats.models.ensemble.weighted_avg_ensemble",
        "WeightedAvgEnsemble",
        ("fit", "predict"),
    ),
    "global.model": (
        "kats.models.globalmodel.model",
        "GMModel",
        ("fit", "predict", "train"),
    ),
    "global.ensemble": (
        "kats.models.globalmodel.ensemble",
        "GMEnsemble",
        ("fit", "predict", "train"),
    ),
    "reconciliation.base_model": (
        "kats.models.reconciliation.base_models",
        "BaseTHModel",
        (),
    ),
    "reconciliation.aggregate": (
        "kats.models.reconciliation.base_models",
        "GetAggregateTS",
        ("aggregate",),
    ),
    "reconciliation.temporal_hierarchy": (
        "kats.models.reconciliation.thm",
        "TemporalHierarchicalModel",
        ("fit", "predict", "median_validation", "get_S", "get_W"),
    ),
    "features.standard": (
        "kats.tsfeatures.tsfeatures",
        "TsFeatures",
        ("transform",),
    ),
    "features.calendar": (
        "kats.tsfeatures.tsfeatures",
        "TsCalenderFeatures",
        ("transform",),
    ),
    "features.fourier": (
        "kats.tsfeatures.tsfeatures",
        "TsFourierFeatures",
        ("transform",),
    ),
    "decomposition.timeseries": (
        "kats.utils.decomposition",
        "TimeSeriesDecomposition",
        ("decomposer",),
    ),
    "decomposition.seasonality": (
        "kats.utils.decomposition",
        "SeasonalityHandler",
        ("remove_seasonality", "add_seasonality"),
    ),
    "backtest.simple": (
        "kats.utils.backtesters",
        "KatsSimpleBacktester",
        ("run_backtester", "get_errors"),
    ),
    "backtest.rolling_origin": (
        "kats.utils.backtesters",
        "BackTesterRollingOrigin",
        ("run_backtest",),
    ),
    "backtest.expanding_window": (
        "kats.utils.backtesters",
        "BackTesterExpandingWindow",
        ("run_backtest",),
    ),
    "backtest.rolling_window": (
        "kats.utils.backtesters",
        "BackTesterRollingWindow",
        ("run_backtest",),
    ),
    "backtest.fixed_window": (
        "kats.utils.backtesters",
        "BackTesterFixedWindow",
        ("run_backtest",),
    ),
    "backtest.cross_validation": (
        "kats.utils.backtesters",
        "CrossValidation",
        ("run_cv",),
    ),
    "tuning.grid": (
        "kats.utils.time_series_parameter_tuning",
        "GridSearch",
        ("generate_evaluate_new_parameter_values", "list_parameter_value_scores"),
    ),
    "tuning.random": (
        "kats.utils.time_series_parameter_tuning",
        "RandomSearch",
        ("generate_evaluate_new_parameter_values", "list_parameter_value_scores"),
    ),
    "tuning.bayesian": (
        "kats.utils.time_series_parameter_tuning",
        "BayesianOptSearch",
        ("generate_evaluate_new_parameter_values", "list_parameter_value_scores"),
    ),
    "tuning.nevergrad": (
        "kats.utils.time_series_parameter_tuning",
        "NevergradOptSearch",
        ("generate_evaluate_new_parameter_values", "list_parameter_value_scores"),
    ),
    "meta.metadata": (
        "kats.models.metalearner.get_metadata",
        "GetMetaData",
        ("get_meta_data",),
    ),
    "meta.model_select": (
        "kats.models.metalearner.metalearner_modelselect",
        "MetaLearnModelSelect",
        ("predict", "train"),
    ),
    "meta.predictability": (
        "kats.models.metalearner.metalearner_predictability",
        "MetaLearnPredictability",
        ("predict", "train"),
    ),
    "meta.hpt": (
        "kats.models.metalearner.metalearner_hpt",
        "MetaLearnHPT",
        ("predict", "train"),
    ),
    "detector_model.cusum": (
        "kats.detectors.cusum_model",
        "CUSUMDetectorModel",
        ("fit", "predict"),
    ),
    "detector_model.bocpd": (
        "kats.detectors.bocpd_model",
        "BocpdDetectorModel",
        ("fit", "predict"),
    ),
    "detector_model.bocpd_trend": (
        "kats.detectors.bocpd_model",
        "BocpdTrendDetectorModel",
        ("fit", "predict"),
    ),
    "detector_model.prophet": (
        "kats.detectors.prophet_detector",
        "ProphetDetectorModel",
        ("fit", "predict"),
    ),
    "detector_model.prophet_trend": (
        "kats.detectors.prophet_detector",
        "ProphetTrendDetectorModel",
        ("fit", "predict"),
    ),
    "detector_model.stat_sig": (
        "kats.detectors.stat_sig_detector",
        "StatSigDetectorModel",
        ("fit", "predict"),
    ),
    "simulator": (
        "kats.utils.simulator",
        "Simulator",
        (
            "add_trend",
            "add_noise",
            "add_seasonality",
            "stl_sim",
            "arima_sim",
            "level_shift_sim",
            "level_shift_multivariate_indep_sim",
            "trend_shift_sim",
        ),
    ),
}


class KatsOperationError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code


class KatsRuntime:
    def identity(self) -> dict[str, str]:
        return {
            "name": KATS_NAME,
            "version": KATS_VERSION,
            "commit": KATS_COMMIT,
        }

    def capabilities(self) -> dict[str, Any]:
        return {
            "operations": [
                "forecast",
                "detect",
                "features",
                "decompose",
                "backtest",
                "tune",
                "simulate",
                "advanced",
            ],
            "forecastAlgorithms": sorted(FORECAST_TARGETS),
            "detectors": sorted(DETECTOR_TARGETS),
            "publicTargets": sorted(PUBLIC_TARGETS),
        }

    def execute(
        self,
        operation: str,
        input_items: list[dict[str, Any]],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        handlers = {
            "forecast": self._forecast,
            "detect": self._detect,
            "features": self._features,
            "decompose": self._decompose,
            "backtest": self._backtest,
            "tune": self._tune,
            "simulate": self._simulate,
            "advanced": self._advanced,
        }
        handler = handlers.get(operation)
        if handler is None:
            raise KatsOperationError(
                "operation_not_supported",
                "Unsupported Kats operation.",
                {"operation": operation, "supported": sorted(handlers)},
            )
        try:
            result = handler(input_items, dict(params))
        except KatsOperationError:
            raise
        except (ImportError, ModuleNotFoundError) as error:
            raise KatsOperationError(
                "optional_dependency_unavailable",
                "A dependency required by this Kats capability is unavailable.",
                {"operation": operation, "dependency": str(error)},
                status_code=409,
            ) from error
        except Exception as error:
            raise KatsOperationError(
                "kats_execution_failed",
                str(error) or "Kats execution failed.",
                {"operation": operation, "errorType": type(error).__name__},
            ) from error
        return {
            "schema": "kats.result.v1",
            "source": KATS_NAME,
            "operation": operation,
            "status": "ok",
            "data": _jsonable(result),
        }

    def _forecast(
        self, input_items: list[dict[str, Any]], params: dict[str, Any]
    ) -> Any:
        algorithm = str(params.get("algorithm") or "arima")
        target = FORECAST_TARGETS.get(algorithm)
        if target is None:
            raise KatsOperationError(
                "forecast_model_not_supported",
                "Unsupported forecast model.",
                {"algorithm": algorithm, "supported": sorted(FORECAST_TARGETS)},
            )
        data = _time_series_data(input_items, params)
        module_name, model_name, params_name = target
        module = importlib.import_module(module_name)
        model_params = getattr(module, params_name)(
            **_mapping(params.get("modelParams"), "modelParams")
        )
        model = getattr(module, model_name)(data=data, params=model_params)
        model.fit(**_mapping(params.get("fitParams"), "fitParams"))
        predict_params = _mapping(params.get("predictParams"), "predictParams")
        predict_params.setdefault(
            "steps", _bounded_int(params.get("steps", 12), 1, 10_000)
        )
        if params.get("freq") and "freq" not in predict_params:
            predict_params["freq"] = str(params["freq"])
        return model.predict(**predict_params)

    def _detect(self, input_items: list[dict[str, Any]], params: dict[str, Any]) -> Any:
        algorithm = str(params.get("algorithm") or "cusum")
        target = DETECTOR_TARGETS.get(algorithm)
        if target is None:
            raise KatsOperationError(
                "detector_not_supported",
                "Unsupported Kats detector.",
                {"algorithm": algorithm, "supported": sorted(DETECTOR_TARGETS)},
            )
        data = _time_series_data(input_items, params)
        module_name, class_name = target
        detector = getattr(importlib.import_module(module_name), class_name)(
            data,
            **_mapping(params.get("constructorParams"), "constructorParams"),
        )
        return detector.detector(
            **_mapping(params.get("detectorParams"), "detectorParams")
        )

    def _features(
        self, input_items: list[dict[str, Any]], params: dict[str, Any]
    ) -> Any:
        feature_params = _mapping(params.get("featureParams"), "featureParams")
        selected = params.get("selectedFeatures")
        if isinstance(selected, list) and selected:
            feature_params["selected_features"] = [str(value) for value in selected]
        features_cls = importlib.import_module("kats.tsfeatures.tsfeatures").TsFeatures
        return features_cls(**feature_params).transform(
            _time_series_data(input_items, params)
        )

    def _decompose(
        self, input_items: list[dict[str, Any]], params: dict[str, Any]
    ) -> Any:
        decomposition_cls = importlib.import_module(
            "kats.utils.decomposition"
        ).TimeSeriesDecomposition
        decomposer = decomposition_cls(
            _time_series_data(input_items, params),
            decomposition=str(params.get("decomposition") or "additive"),
            method=str(params.get("method") or "STL"),
            **_mapping(params.get("decompositionParams"), "decompositionParams"),
        )
        return decomposer.decomposer()

    def _backtest(
        self, input_items: list[dict[str, Any]], params: dict[str, Any]
    ) -> Any:
        data = _time_series_data(input_items, params)
        model_class, model_params = _model_class_and_params(params)
        partition_module = importlib.import_module("kats.utils.datapartition")
        backtest_module = importlib.import_module("kats.utils.backtesters")
        partition = partition_module.SimpleDataPartition(
            train_frac=_fraction(params.get("trainFraction", 0.8)),
            multi=False,
        )
        metrics = params.get("metrics")
        scorer = (
            [str(metric) for metric in metrics]
            if isinstance(metrics, list) and metrics
            else ["smape", "mape"]
        )
        backtester = backtest_module.KatsSimpleBacktester(
            datapartition=partition,
            scorer=scorer,
            model_params=model_params,
            model_class=model_class,
            multi=False,
        )
        backtester.run_backtester(data)
        return backtester.get_errors()

    def _tune(self, input_items: list[dict[str, Any]], params: dict[str, Any]) -> Any:
        data = _time_series_data(input_items, params)
        algorithm = str(params.get("algorithm") or "arima")
        target = FORECAST_TARGETS.get(algorithm)
        if target is None:
            raise KatsOperationError(
                "forecast_model_not_supported",
                "Unsupported forecast model for tuning.",
                {"algorithm": algorithm},
            )
        space = params.get("parameterSpace")
        if not isinstance(space, list) or not space:
            raise KatsOperationError(
                "parameter_space_required",
                "parameterSpace must be a non-empty Ax-style parameter list.",
            )
        metric = str(params.get("metric") or "smape")
        train_fraction = _fraction(params.get("trainFraction", 0.8))
        module_name, model_name, params_name = target
        model_module = importlib.import_module(module_name)
        model_class = getattr(model_module, model_name)
        params_class = getattr(model_module, params_name)
        partition_cls = importlib.import_module(
            "kats.utils.datapartition"
        ).SimpleDataPartition
        backtester_cls = importlib.import_module(
            "kats.utils.backtesters"
        ).KatsSimpleBacktester

        def evaluate(candidate: dict[str, Any]) -> dict[str, float]:
            backtester = backtester_cls(
                datapartition=partition_cls(train_frac=train_fraction, multi=False),
                scorer=[metric],
                model_params=params_class(**candidate),
                model_class=model_class,
                multi=False,
            )
            backtester.run_backtester(data)
            result = backtester.get_errors()
            summary = getattr(result, "summary_errors", None)
            if not isinstance(summary, dict) or metric not in summary:
                raise ValueError("Backtester did not return the requested metric.")
            return {metric: float(summary[metric])}

        tuning = importlib.import_module("kats.utils.time_series_parameter_tuning")
        search_enum = importlib.import_module("kats.consts").SearchMethodEnum
        search_method = str(params.get("searchMethod") or "grid")
        enum_by_name = {
            "grid": search_enum.GRID_SEARCH,
            "random": search_enum.RANDOM_SEARCH_UNIFORM,
            "bayes": search_enum.BAYES_OPT,
            "nevergrad": search_enum.NEVERGRAD,
        }
        selected = enum_by_name.get(search_method)
        if selected is None:
            raise KatsOperationError(
                "search_method_not_supported",
                "Unsupported Kats search method.",
                {"searchMethod": search_method, "supported": sorted(enum_by_name)},
            )
        search = tuning.SearchMethodFactory.create_search_method(
            parameters=space,
            selected_search_method=selected,
            objective_name=metric,
            evaluation_function=evaluate,
            seed=int(params.get("seed", 17)),
            multiprocessing=False,
        )
        trials = _bounded_int(params.get("trials", 12), 1, 1000)
        search.generate_evaluate_new_parameter_values(
            evaluate,
            arm_count=-1 if search_method == "grid" else trials,
        )
        return search.list_parameter_value_scores()

    def _simulate(
        self, _input_items: list[dict[str, Any]], params: dict[str, Any]
    ) -> Any:
        import numpy as np

        simulator_cls = importlib.import_module("kats.utils.simulator").Simulator
        np.random.seed(int(params.get("seed", 17)))
        simulator = simulator_cls(
            n=_bounded_int(params.get("n", 240), 5, MAX_POINTS),
            freq=str(params.get("freq") or "D"),
            start=params.get("start"),
        )
        mode = str(params.get("mode") or "components")
        simulation_params = _mapping(params.get("simulationParams"), "simulationParams")
        if mode == "arima":
            return simulator.arima_sim(**simulation_params)
        if mode == "level_shift":
            simulation_params.setdefault("random_seed", int(params.get("seed", 17)))
            return simulator.level_shift_sim(**simulation_params)
        if mode == "trend_shift":
            simulation_params.setdefault("random_seed", int(params.get("seed", 17)))
            return simulator.trend_shift_sim(**simulation_params)
        if mode != "components":
            raise KatsOperationError(
                "simulation_mode_not_supported",
                "Unsupported simulation mode.",
                {"mode": mode},
            )
        simulator.add_trend(float(simulation_params.get("trend", 0.1)))
        simulator.add_seasonality(
            float(simulation_params.get("seasonality", 2.0)),
            period=simulation_params.get("period", "7D"),
        )
        simulator.add_noise(float(simulation_params.get("noise", 0.2)))
        return simulator.stl_sim()

    def _advanced(
        self, input_items: list[dict[str, Any]], params: dict[str, Any]
    ) -> Any:
        target_name = str(params.get("target") or "")
        target_spec = PUBLIC_TARGETS.get(target_name)
        if target_spec is None:
            raise KatsOperationError(
                "public_target_not_supported",
                "The requested Kats public target is not allowlisted.",
                {"target": target_name, "supported": sorted(PUBLIC_TARGETS)},
            )
        module_name, class_name, methods = target_spec
        data = _time_series_data(input_items, params, required=False)
        constructor = _mapping(params.get("constructor"), "constructor")
        resolved_constructor = _resolve_descriptors(constructor, data)
        instance = getattr(importlib.import_module(module_name), class_name)(
            **resolved_constructor
        )
        calls = params.get("calls")
        if not isinstance(calls, list) or not calls:
            return instance
        if len(calls) > MAX_CALLS:
            raise KatsOperationError(
                "too_many_method_calls",
                "The advanced Kats job exceeds the method-call limit.",
                {"maxCalls": MAX_CALLS},
            )
        last_result: Any = instance
        for call in calls:
            if not isinstance(call, dict):
                raise KatsOperationError(
                    "invalid_method_call", "Each call must be an object."
                )
            method_name = str(call.get("method") or "")
            if method_name not in methods:
                raise KatsOperationError(
                    "method_not_allowed",
                    "The method is not allowed for this Kats target.",
                    {
                        "target": target_name,
                        "method": method_name,
                        "allowed": list(methods),
                    },
                )
            kwargs = _mapping(call.get("kwargs"), "calls[].kwargs")
            result = getattr(instance, method_name)(
                **_resolve_descriptors(kwargs, data)
            )
            if result is not None:
                last_result = result
        return last_result


def _model_class_and_params(params: dict[str, Any]) -> tuple[Any, Any]:
    algorithm = str(params.get("algorithm") or "arima")
    target = FORECAST_TARGETS.get(algorithm)
    if target is None:
        raise KatsOperationError(
            "forecast_model_not_supported",
            "Unsupported forecast model.",
            {"algorithm": algorithm},
        )
    module_name, model_name, params_name = target
    module = importlib.import_module(module_name)
    return (
        getattr(module, model_name),
        getattr(module, params_name)(
            **_mapping(params.get("modelParams"), "modelParams")
        ),
    )


def _time_series_data(
    input_items: list[dict[str, Any]],
    params: dict[str, Any],
    required: bool = True,
) -> Any:
    import pandas as pd

    records = params.get("series")
    if not isinstance(records, list) or not records:
        records = _series_records_from_inputs(input_items)
    if not records:
        if not required:
            return None
        raise KatsOperationError(
            "time_series_required",
            "Provide params.series or upstream items containing time-series points.",
        )
    if len(records) > MAX_POINTS:
        raise KatsOperationError(
            "time_series_too_large",
            "The time series exceeds the runtime point limit.",
            {"maxPoints": MAX_POINTS, "pointCount": len(records)},
            status_code=413,
        )
    time_field = str(params.get("timeField") or "time")
    value_field = params.get("valueField") or "value"
    value_fields = (
        [str(value) for value in value_field]
        if isinstance(value_field, list)
        else [str(value_field)]
    )
    rows: list[dict[str, Any]] = []
    for _index, record in enumerate(records):
        if not isinstance(record, dict):
            rows.append({"time": None, "value": record})
            continue
        row: dict[str, Any] = {"time": _path_value(record, time_field)}
        for field in value_fields:
            row[field if len(value_fields) > 1 else "value"] = _path_value(
                record, field
            )
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame["time"].isna().all():
        frame["time"] = pd.date_range(
            start=params.get("start") or "1970-01-01",
            periods=len(frame),
            freq=str(params.get("freq") or "D"),
        )
    else:
        frame["time"] = pd.to_datetime(frame["time"], utc=True).dt.tz_localize(None)
    for column in frame.columns:
        if column != "time":
            frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame.sort_values("time", inplace=True)
    time_series_cls = importlib.import_module("kats.consts").TimeSeriesData
    return time_series_cls(frame.reset_index(drop=True))


def _series_records_from_inputs(input_items: list[dict[str, Any]]) -> list[Any]:
    records: list[Any] = []
    for item in input_items:
        candidate: Any = item
        if isinstance(item, dict):
            for key in ("series", "points", "items"):
                if isinstance(item.get(key), list):
                    records.extend(item[key])
                    candidate = None
                    break
            if candidate is None:
                continue
            for wrapper in ("normalizedData", "raw"):
                wrapped = item.get(wrapper)
                if isinstance(wrapped, dict):
                    for key in ("series", "points", "items"):
                        if isinstance(wrapped.get(key), list):
                            records.extend(wrapped[key])
                            candidate = None
                            break
                    if candidate is not None:
                        candidate = wrapped
                if candidate is None:
                    break
        if candidate is not None:
            records.append(candidate)
    return records


def _resolve_descriptors(value: Any, data: Any) -> Any:
    if isinstance(value, list):
        return [_resolve_descriptors(item, data) for item in value]
    if not isinstance(value, dict):
        return value
    if value.get("$series") is True:
        if data is None:
            raise KatsOperationError(
                "time_series_required",
                "This advanced Kats descriptor requires a time series.",
            )
        return data
    if "$target" in value:
        target_name = str(value["$target"])
        target = PUBLIC_TARGETS.get(target_name)
        if target is None:
            raise KatsOperationError(
                "public_target_not_supported",
                "A nested Kats target is not allowlisted.",
                {"target": target_name},
            )
        module_name, class_name, _methods = target
        kwargs = _mapping(value.get("kwargs"), "$target.kwargs")
        return getattr(importlib.import_module(module_name), class_name)(
            **_resolve_descriptors(kwargs, data)
        )
    if "$array" in value:
        import numpy as np

        return np.asarray(_resolve_descriptors(value["$array"], data))
    if "$dataframe" in value:
        import pandas as pd

        return pd.DataFrame(_resolve_descriptors(value["$dataframe"], data))
    return {key: _resolve_descriptors(item, data) for key, item in value.items()}


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise KatsOperationError(
            "invalid_parameter",
            field + " must be an object.",
            {"field": field},
        )
    return dict(value)


def _path_value(value: Mapping[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise KatsOperationError(
            "invalid_integer",
            "Expected an integer parameter.",
            {"value": value},
        ) from error
    if parsed < minimum or parsed > maximum:
        raise KatsOperationError(
            "integer_out_of_range",
            "Integer parameter is outside the allowed range.",
            {"value": parsed, "minimum": minimum, "maximum": maximum},
        )
    return parsed


def _fraction(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise KatsOperationError(
            "invalid_fraction", "Expected a numeric fraction."
        ) from error
    if not 0 < parsed < 1:
        raise KatsOperationError(
            "fraction_out_of_range",
            "Fraction must be between zero and one.",
            {"value": parsed},
        )
    return parsed


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]

    module = type(value).__module__.split(".", 1)[0]
    if module == "numpy":
        if hasattr(value, "item"):
            try:
                return _jsonable(value.item())
            except ValueError:
                pass
        if hasattr(value, "tolist"):
            return _jsonable(value.tolist())
    if module == "pandas":
        if hasattr(value, "to_dict") and hasattr(value, "columns"):
            return _jsonable(value.to_dict(orient="records"))
        if hasattr(value, "tolist"):
            return _jsonable(value.tolist())
    if value.__class__.__name__ == "TimeSeriesData" and hasattr(value, "to_dataframe"):
        return _jsonable(value.to_dataframe())
    if hasattr(value, "_asdict"):
        return _jsonable(value._asdict())
    if hasattr(value, "__dict__"):
        public = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_") and not callable(item)
        }
        if public:
            return _jsonable(public)
    return str(value)
