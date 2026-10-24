"""Two-pass TypeSafe/Jev adapter with cacheable, redacted request provenance."""

from __future__ import annotations

import os
import time
from typing import Any, Protocol

from . import JEV_MODEL
from .storage import JsonCache


STAGE1_QUESTION_SPECS: dict[str, dict[str, Any]] = {
    "semantic_direction": {
        "type": "choice",
        "instructions": "Considering only the supplied ticker-specific documents, what direction do they support for the supplied forecast horizon? Choose insufficient when the evidence does not support a directional judgment.",
        "criteria": {
            "bullish": "Evidence supports a positive price direction.",
            "neutral": "Evidence supports no material directional change.",
            "bearish": "Evidence supports a negative price direction.",
            "insufficient": "Evidence is missing, irrelevant, or too ambiguous for a direction.",
        },
    },
    "materiality": {
        "type": "score",
        "instructions": "How material is the supplied information for this issuer and horizon?",
        "criteria": [
            "Routine or immaterial information",
            "Potentially relevant but limited likely impact",
            "Material information with plausible price impact",
            "Potentially transformative information",
        ],
    },
    "evidence_sufficient": {
        "type": "noul",
        "instructions": "Do the documents contain enough current, ticker-specific information to make a semantic judgment?",
    },
    "demand_improving": {"type": "noul", "instructions": "Does the evidence indicate improving demand for the issuer?"},
    "cost_pressure": {"type": "noul", "instructions": "Does the evidence indicate material cost pressure?"},
    "regulatory_legal_risk": {"type": "noul", "instructions": "Does the evidence indicate material regulatory or legal risk?"},
    "liquidity_risk": {"type": "noul", "instructions": "Does the evidence indicate material liquidity or financing risk?"},
    "operational_risk": {"type": "noul", "instructions": "Does the evidence indicate material operational risk?"},
    "governance_risk": {"type": "noul", "instructions": "Does the evidence indicate material governance risk?"},
}


STAGE2_QUESTION_SPECS: dict[str, dict[str, Any]] = {
    "preferred_variant": {
        "type": "choice",
        "instructions": "Which concrete candidate target is best supported by the evidence and numerical forecast? Choose insufficient if the evidence cannot distinguish the candidates. Do not invent another target.",
        "criteria": {
            "kronos": "Use the unchanged Kronos terminal target.",
            "semantic_scenario": "Use the deterministic low/base/high target selected by the Stage-1 direction.",
            "rule_adjusted": "Use the deterministic probability-weighted target calculated by code.",
            "insufficient": "The supplied state cannot support a candidate preference.",
        },
    },
    "supports_kronos": {"type": "noul", "instructions": "Does the evidence support the unchanged Kronos candidate?"},
    "supports_semantic_scenario": {"type": "noul", "instructions": "Does the evidence support the semantic-scenario candidate?"},
    "supports_rule_adjusted": {"type": "noul", "instructions": "Does the evidence support the rule-adjusted candidate?"},
    "combined_risk": {
        "type": "score",
        "instructions": "Rate combined uncertainty and downside risk for displaying this result.",
        "criteria": [
            "Low: evidence is coherent, forecast range is limited, and no material risk signal dominates",
            "Medium: meaningful uncertainty, a moderate risk signal, or some disagreement is present",
            "High: severe uncertainty, strong downside risk, material contradiction, or unstable evidence is present",
        ],
    },
    "evidence_conflict": {"type": "noul", "instructions": "Is there a meaningful contradiction between the textual evidence and the numerical forecast?"},
}


class JevClient(Protocol):
    def evaluate(self, state: dict[str, Any], question_specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
        ...


class TypeSafeJevClient:
    def __init__(self, *, model: str = JEV_MODEL, timeout: float = 20.0):
        if not os.environ.get("TYPESAFE_API_KEY", "").strip():
            raise RuntimeError("TYPESAFE_API_KEY is required for Jev calls")
        self.model = model
        self.timeout = timeout

    def evaluate(self, state: dict[str, Any], question_specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
        try:
            from typesafe_sdk import Choice, Noul, RetryPolicy, Score, TypeSafeClient
        except ImportError as exc:
            raise RuntimeError("Install experiments/jev_post_forecast/requirements.txt into venv") from exc

        questions: dict[str, Any] = {}
        for name, spec in question_specs.items():
            if spec["type"] == "choice":
                questions[name] = Choice(instructions=spec["instructions"], criteria=spec["criteria"])
            elif spec["type"] == "score":
                questions[name] = Score(instructions=spec["instructions"], criteria=spec["criteria"])
            else:
                questions[name] = Noul(instructions=spec["instructions"])
        started = time.perf_counter()
        with TypeSafeClient(model=self.model, timeout=self.timeout, retry=RetryPolicy(max_retries=2)) as client:
            response = client.system_one(state=state, questions=questions)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        payload = response.model_dump(mode="json")
        payload["request_id"] = getattr(response, "request_id", None)
        payload["latency_ms"] = round(elapsed_ms, 3)
        return payload


class JevService:
    def __init__(self, client: JevClient, cache: JsonCache, *, model: str = JEV_MODEL):
        self.client = client
        self.cache = cache
        self.model = model

    def stage1(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._call("stage1", state, STAGE1_QUESTION_SPECS)

    def stage2(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._call("stage2", state, STAGE2_QUESTION_SPECS)

    def _call(self, pass_name: str, state: dict[str, Any], specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
        request = {"model": self.model, "pass": pass_name, "state": state, "questions": specs}
        cached = self.cache.get("jev", request)
        if cached:
            return cached
        if self.cache.offline:
            return self.cache.require("jev", request)
        raw = self.client.evaluate(state, specs)
        result = {
            "request": request,
            "response": normalize_response(raw, specs),
            "raw_response": _redact(raw),
        }
        self.cache.put("jev", request, result)
        return result


def normalize_response(raw: dict[str, Any], specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    answers = raw.get("answers")
    if not isinstance(answers, dict):
        raise ValueError("Malformed Jev response: answers must be an object")
    normalized: dict[str, Any] = {"choices": {}, "scores": {}, "nouls": {}}
    for name, spec in specs.items():
        answer = answers.get(name)
        if not isinstance(answer, dict):
            raise ValueError(f"Malformed Jev response: missing answer {name}")
        kind = spec["type"]
        if kind == "choice":
            choice = str(answer.get("choice", ""))
            probabilities = _probabilities(answer.get("probabilities"), spec["criteria"])
            if choice not in spec["criteria"]:
                raise ValueError(f"Malformed Jev response: invalid choice for {name}")
            normalized["choices"][name] = {
                "choice": choice,
                "probabilities": probabilities,
                "confidence": float(answer.get("confidence", 0.0)),
            }
        elif kind == "score":
            score = float(answer.get("score"))
            probabilities = _score_probabilities(answer.get("probabilities"), len(spec["criteria"]))
            if not 0 <= score <= len(spec["criteria"]) - 1:
                raise ValueError(f"Malformed Jev response: invalid score for {name}")
            normalized["scores"][name] = {
                "score": score,
                "probabilities": probabilities,
                "confidence": float(answer.get("confidence", 0.0)),
            }
        else:
            value = float(answer.get("noul"))
            if not 0 <= value <= 1:
                raise ValueError(f"Malformed Jev response: invalid noul for {name}")
            normalized["nouls"][name] = value
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    input_tokens = int(usage.get("input_tokens") or 0)
    normalized.update(
        {
            "model": str(raw.get("model") or JEV_MODEL),
            "request_id": raw.get("request_id"),
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": int(usage.get("output_tokens") or 0),
            },
            "latency_ms": float(raw.get("latency_ms") or 0.0),
            "estimated_cost_usd": round(input_tokens * 0.042 / 1_000_000, 8),
        }
    )
    return normalized


def _probabilities(value: Any, choices: dict[str, Any]) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError("Malformed Jev response: choice probabilities must be an object")
    result = {name: float(value.get(name, 0.0)) for name in choices}
    _validate_distribution(result)
    return result


def _score_probabilities(value: Any, count: int) -> dict[str, float]:
    if isinstance(value, list):
        result = {str(index): float(item) for index, item in enumerate(value)}
    elif isinstance(value, dict):
        result = {str(index): float(value.get(str(index), value.get(index, 0.0))) for index in range(count)}
    else:
        raise ValueError("Malformed Jev response: score probabilities must be an object or list")
    _validate_distribution(result)
    return result


def _validate_distribution(probabilities: dict[str, float]) -> None:
    if any(value < 0 or value > 1 for value in probabilities.values()):
        raise ValueError("Malformed Jev response: invalid probability")
    total = sum(probabilities.values())
    if not 0.98 <= total <= 1.02:
        raise ValueError("Malformed Jev response: probabilities do not sum to one")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(token in str(key).lower() for token in ("authorization", "api_key", "apikey", "token", "secret")) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
