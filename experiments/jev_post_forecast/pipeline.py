"""Experiment orchestration. Nothing here writes to production services or databases."""

from __future__ import annotations

import os
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.ai_analysis import KronosForecaster, PredictionError, percent_change
from src.config import Settings
from src.database import normalize_ticker

from . import EXPERIMENT_VERSION, JEV_MODEL, KRONOS_MODEL
from .evidence import (
    EvidenceCollector,
    disclosure_time,
    enforce_evidence_limits,
    evidence_state,
    is_relevant_disclosure,
    parse_datetime,
    select_historical_cases,
)
from .fusion import (
    candidate_metrics,
    choose_final_candidate,
    combine_risk,
    compose_candidates,
    deterministic_warnings,
    quantitative_summary,
)
from .jev import JevClient, JevService, TypeSafeJevClient
from .storage import JsonCache


DEFAULT_TICKERS = ("PETR4", "VALE3", "ITUB4")


class OfflineClient:
    def evaluate(self, state: dict[str, Any], question_specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
        raise RuntimeError("Offline mode attempted an uncached Jev call")


class KronosRunner:
    def __init__(self, project_root: Path, *, seed: int, sample_count: int = 4):
        self.seed = seed
        self.settings = Settings(
            kronos_repo_path=str(project_root / ".deps" / "Kronos"),
            kronos_model_name=KRONOS_MODEL,
            kronos_tokenizer_name="NeoQuasar/Kronos-Tokenizer-base",
            kronos_max_context=512,
            kronos_sample_count=sample_count,
            kronos_temperature=1.0,
            kronos_top_p=0.9,
            kronos_device="cpu",
        )
        self.forecaster = KronosForecaster(self.settings)

    def forecast(self, candles: list[dict[str, Any]], horizon: int) -> tuple[list[dict[str, Any]], float]:
        try:
            import numpy as np
            import torch

            np.random.seed(self.seed)
            torch.manual_seed(self.seed)
        except ImportError as exc:
            raise PredictionError(f"Kronos dependencies are missing: {exc}") from exc
        started = time.perf_counter()
        forecast = self.forecaster.forecast(candles[-512:], "1d", horizon)
        return forecast, round((time.perf_counter() - started) * 1000.0, 3)


class ExperimentRunner:
    def __init__(
        self,
        *,
        project_root: Path,
        cache: JsonCache,
        seed: int = 17,
        jev_client: JevClient | None = None,
        evidence_collector: EvidenceCollector | None = None,
        kronos_runner: KronosRunner | None = None,
    ):
        self.project_root = project_root
        self.cache = cache
        self.seed = seed
        self.evidence = evidence_collector or EvidenceCollector(cache)
        client = jev_client or (OfflineClient() if cache.offline else TypeSafeJevClient())
        self.jev = JevService(client, cache)
        self.kronos = kronos_runner or KronosRunner(project_root, seed=seed)

    def run(self, *, mode: str, tickers: list[str], horizon: int, run_id: str) -> dict[str, Any]:
        started_at = _now()
        cases: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        normalized_tickers = [normalize_ticker(value) for value in tickers]
        for ticker in normalized_tickers:
            try:
                candles = self.evidence.candles(ticker)
                if len(candles) < 100 + horizon:
                    raise ValueError(f"{ticker} has only {len(candles)} usable daily candles")
                years = sorted(
                    {parse_datetime(row["timestamp"]).year for row in candles if parse_datetime(row["timestamp"])},
                    reverse=True,
                )
                records = self.evidence.cvm_records(ticker, years)
                if mode in {"historical", "all"}:
                    self._historical_cases(ticker, candles, records, horizon, cases, failures)
                if mode in {"live", "all"}:
                    try:
                        cases.append(self._live_case(ticker, candles, records, horizon))
                    except Exception as exc:  # isolate cases so the report explains partial runs
                        failures.append(_failure(ticker, "live", exc))
            except Exception as exc:
                failures.append(_failure(ticker, mode, exc))

        finished_at = _now()
        run = {
            "schema_version": 1,
            "experiment_version": EXPERIMENT_VERSION,
            "run_id": run_id,
            "mode": mode,
            "tickers": normalized_tickers,
            "horizon": horizon,
            "seed": self.seed,
            "started_at": started_at,
            "finished_at": finished_at,
            "provenance": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "kronos_model": KRONOS_MODEL,
                "kronos_tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
                "kronos_device": "cpu",
                "kronos_context": 512,
                "kronos_sample_count": 4,
                "jev_model_requested": JEV_MODEL,
                "jev_input_price_per_million_tokens_usd": 0.042,
                "candle_source": "Yahoo Finance chart API",
                "evidence_sources": ["Yahoo headline metadata", "CVM IPE"],
                "api_key_recorded": False,
            },
            "summary": summarize(cases, failures),
            "cases": cases,
            "failures": failures,
        }
        return run

    def _historical_cases(
        self,
        ticker: str,
        candles: list[dict[str, Any]],
        records: list[dict[str, Any]],
        horizon: int,
        cases: list[dict[str, Any]],
        failures: list[dict[str, Any]],
    ) -> None:
        selected = select_historical_cases(candles, records, horizon=horizon, count=2)
        if len(selected) < 2:
            failures.append(
                {
                    "ticker": ticker,
                    "case_kind": "historical",
                    "error_type": "InsufficientHistoricalCases",
                    "message": f"Expected 2 completed CVM cases, found {len(selected)}",
                }
            )
        for index, selection in enumerate(selected, start=1):
            cutoff = str(selection["cutoff"])
            eligible = [
                record
                for record in records
                if is_relevant_disclosure(record)
                and disclosure_time(record)
                and parse_datetime(cutoff)
                and disclosure_time(record) <= parse_datetime(cutoff)
            ]
            documents = enforce_evidence_limits(self.evidence.cvm_documents(eligible, limit=6))
            try:
                cases.append(
                    self._evaluate_case(
                        case_id=f"{ticker}-historical-{index}-{cutoff[:10]}",
                        ticker=ticker,
                        kind="historical",
                        evidence_label="CVM-only",
                        cutoff=cutoff,
                        candles=selection["context"],
                        realized=selection["realized"],
                        evidence=documents,
                        horizon=horizon,
                        anchor_disclosure=selection["disclosure"],
                    )
                )
            except Exception as exc:
                failures.append(_failure(ticker, "historical", exc, case_id=f"{ticker}-historical-{index}-{cutoff[:10]}"))

    def _live_case(
        self,
        ticker: str,
        candles: list[dict[str, Any]],
        records: list[dict[str, Any]],
        horizon: int,
    ) -> dict[str, Any]:
        cutoff = _now()
        cutoff_time = parse_datetime(cutoff)
        current_records = [
            record for record in records if disclosure_time(record) and cutoff_time and disclosure_time(record) <= cutoff_time
        ]
        yahoo_documents = self.evidence.yahoo_news(ticker, limit=6)
        cvm_documents = self.evidence.cvm_documents(current_records, limit=6)
        documents = enforce_evidence_limits([*yahoo_documents, *cvm_documents])
        return self._evaluate_case(
            case_id=f"{ticker}-live-{cutoff[:10]}",
            ticker=ticker,
            kind="live",
            evidence_label="Yahoo headlines + CVM",
            cutoff=cutoff,
            candles=candles,
            realized=[],
            evidence=documents,
            horizon=horizon,
            anchor_disclosure=None,
        )

    def _evaluate_case(
        self,
        *,
        case_id: str,
        ticker: str,
        kind: str,
        evidence_label: str,
        cutoff: str,
        candles: list[dict[str, Any]],
        realized: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        horizon: int,
        anchor_disclosure: dict[str, Any] | None,
    ) -> dict[str, Any]:
        cutoff_time = parse_datetime(cutoff)
        for document in evidence:
            published = parse_datetime(document.get("published_at"))
            if kind == "historical" and published and cutoff_time and published > cutoff_time:
                raise AssertionError("Historical evidence was delivered after the analysis cutoff")
        forecast, kronos_latency_ms = self.kronos.forecast(candles, horizon)
        last_close = float(candles[-1]["close"])
        terminal_return = percent_change(last_close, float(forecast[-1]["close"]))
        low_return = percent_change(last_close, min(float(row["low"]) for row in forecast))
        high_return = percent_change(last_close, max(float(row["high"]) for row in forecast))
        evidence_payload = evidence_state(evidence, ticker, cutoff, kind, horizon)

        stage1_call = self.jev.stage1(evidence_payload)
        stage1 = stage1_call["response"]
        direction_answer = stage1["choices"]["semantic_direction"]
        materiality_answer = stage1["scores"]["materiality"]
        fusion = compose_candidates(
            last_close=last_close,
            terminal_return=terminal_return,
            low_return=low_return,
            high_return=high_return,
            direction=direction_answer["choice"],
            direction_probabilities=direction_answer["probabilities"],
            materiality_score=materiality_answer["score"],
            evidence_sufficient=stage1["nouls"]["evidence_sufficient"],
        )
        kronos_state = {
            "last_close": last_close,
            "terminal_return_percent": fusion["inputs"]["E"],
            "forecast_low_return_percent": fusion["inputs"]["L"],
            "forecast_high_return_percent": fusion["inputs"]["H"],
            "forecast_path": forecast,
            "horizon": horizon,
        }
        stage2_state = {
            "evidence": evidence_payload,
            "kronos": kronos_state,
            "stage1_answers": stage1,
            "candidate_targets_calculated_by_code": fusion["candidates"],
            "instruction": "Judge only the three supplied code-calculated targets; do not create a new numeric target.",
        }
        stage2_call = self.jev.stage2(stage2_state)
        stage2 = stage2_call["response"]
        preferred = stage2["choices"]["preferred_variant"]["choice"]
        selected_name, selected = choose_final_candidate(preferred, fusion["candidates"])
        quantitative = quantitative_summary(candles, forecast, horizon, selected["return_percent"])
        risk_score = stage2["scores"]["combined_risk"]["score"]
        final_risk = combine_risk(quantitative["quantitative_risk"], risk_score)
        actual = float(realized[-1]["close"]) if realized else None
        baseline_ape = candidate_metrics(last_close, fusion["candidates"]["kronos"]["target_price"], actual)[
            "absolute_percentage_error"
        ]
        candidates: dict[str, Any] = {}
        for name, candidate in fusion["candidates"].items():
            metrics = candidate_metrics(last_close, candidate["target_price"], actual)
            improvement = None
            if baseline_ape is not None and metrics["absolute_percentage_error"] is not None:
                improvement = round(baseline_ape - metrics["absolute_percentage_error"], 8)
            candidates[name] = {**candidate, "metrics": metrics, "improvement_vs_kronos_ape": improvement}
        return {
            "case_id": case_id,
            "ticker": ticker,
            "case_kind": kind,
            "evidence_label": evidence_label,
            "analysis_cutoff": cutoff,
            "market_data_cutoff": str(candles[-1]["timestamp"]),
            "outcome_status": "known" if realized else "not_yet_known",
            "horizon": horizon,
            "last_close": round(last_close, 8),
            "actual_target_price": round(actual, 8) if actual is not None else None,
            "anchor_disclosure": anchor_disclosure,
            "historical_candles": candles[-80:],
            "forecast": forecast,
            "realized_future": realized,
            "evidence": evidence,
            "evidence_coverage": {
                "document_count": len(evidence),
                "character_count": sum(int(item.get("character_count", 0)) for item in evidence),
                "full_text_count": sum(item.get("content_mode") == "full_text" for item in evidence),
                "metadata_count": sum(item.get("content_mode") == "metadata" for item in evidence),
            },
            "kronos": {
                **kronos_state,
                "model": KRONOS_MODEL,
                "device": "cpu",
                "sample_count": 4,
                "seed": self.seed,
                "latency_ms": kronos_latency_ms,
            },
            "jev_stage1": stage1_call,
            "formula_audit": fusion,
            "candidates": candidates,
            "jev_stage2": stage2_call,
            "selection": {
                "jev_preferred_variant": preferred,
                "selected_variant": selected_name,
                "fallback_used": preferred == "insufficient",
                "target_price": selected["target_price"],
                "return_percent": selected["return_percent"],
                "outlook": quantitative["outlook"],
                "risk": final_risk,
                "quantitative_risk": quantitative["quantitative_risk"],
                "jev_risk_score": risk_score,
                "judgment_clarity": stage2["choices"]["preferred_variant"]["confidence"],
            },
            "quantitative_audit": quantitative,
            "warnings": deterministic_warnings(stage1, stage2),
        }


def summarize(cases: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    stages = [case[stage]["response"] for case in cases for stage in ("jev_stage1", "jev_stage2")]
    input_tokens = sum(item["usage"]["input_tokens"] for item in stages)
    return {
        "case_count": len(cases),
        "historical_case_count": sum(case["case_kind"] == "historical" for case in cases),
        "live_case_count": sum(case["case_kind"] == "live" for case in cases),
        "failure_count": len(failures),
        "jev_input_tokens": input_tokens,
        "jev_estimated_cost_usd": round(input_tokens * 0.042 / 1_000_000, 8),
        "jev_latency_ms": round(sum(item["latency_ms"] for item in stages), 3),
        "kronos_latency_ms": round(sum(case["kronos"]["latency_ms"] for case in cases), 3),
        "evidence_documents": sum(case["evidence_coverage"]["document_count"] for case in cases),
    }


def _failure(ticker: str, kind: str, exc: Exception, case_id: str | None = None) -> dict[str, Any]:
    name = type(exc).__name__
    status = getattr(exc, "status", None)
    if status == 429:
        name = "RateLimitError"
    elif "timeout" in str(exc).lower():
        name = "TimeoutError"
    message = str(exc)
    api_key = os.environ.get("TYPESAFE_API_KEY", "")
    if api_key:
        message = message.replace(api_key, "[REDACTED]")
    return {
        "ticker": ticker,
        "case_kind": kind,
        "case_id": case_id,
        "error_type": name,
        "message": message,
    }


def require_runtime_credentials(mode: str, offline: bool) -> None:
    if mode != "report-only" and not offline and not os.environ.get("TYPESAFE_API_KEY", "").strip():
        raise RuntimeError("TYPESAFE_API_KEY is required. Use --offline only with a populated local cache.")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
