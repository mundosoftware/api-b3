"""Pure calculations used by the experiment and its tests."""

from __future__ import annotations

import math
from typing import Any


RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def percent_change(base: float, value: float) -> float:
    return 0.0 if base == 0 else (value - base) / base * 100.0


def price_from_return(last_close: float, return_percent: float) -> float:
    return last_close * (1.0 + return_percent / 100.0)


def compose_candidates(
    *,
    last_close: float,
    terminal_return: float,
    low_return: float,
    high_return: float,
    direction: str,
    direction_probabilities: dict[str, float],
    materiality_score: float,
    evidence_sufficient: float,
) -> dict[str, Any]:
    """Create the three candidate returns exactly as defined in the experiment plan."""
    low_return, high_return = sorted((float(low_return), float(high_return)))
    terminal_return = clamp(float(terminal_return), low_return, high_return)
    probabilities = {key: float(value) for key, value in direction_probabilities.items()}
    directional_signal = probabilities.get("bullish", 0.0) - probabilities.get("bearish", 0.0)
    materiality = clamp(float(materiality_score) / 3.0, 0.0, 1.0)
    sufficiency = clamp(float(evidence_sufficient), 0.0, 1.0)

    if direction == "bullish":
        scenario_return = high_return
    elif direction == "bearish":
        scenario_return = low_return
    else:
        scenario_return = terminal_return

    room = high_return - terminal_return if directional_signal >= 0 else terminal_return - low_return
    adjusted_return = clamp(
        terminal_return + directional_signal * materiality * sufficiency * room,
        low_return,
        high_return,
    )

    candidates = {
        "kronos": _candidate(last_close, terminal_return),
        "semantic_scenario": _candidate(last_close, scenario_return),
        "rule_adjusted": _candidate(last_close, adjusted_return),
    }
    return {
        "inputs": {
            "E": terminal_return,
            "L": low_return,
            "H": high_return,
            "p_bullish": probabilities.get("bullish", 0.0),
            "p_bearish": probabilities.get("bearish", 0.0),
            "d": directional_signal,
            "materiality_score": float(materiality_score),
            "m": materiality,
            "evidence_sufficient": sufficiency,
            "room": room,
        },
        "semantic_return_proxy": directional_signal * materiality * sufficiency,
        "candidates": candidates,
    }


def _candidate(last_close: float, return_percent: float) -> dict[str, float]:
    return {
        "return_percent": round(float(return_percent), 8),
        "target_price": round(price_from_return(last_close, return_percent), 8),
    }


def choose_final_candidate(preferred_variant: str, candidates: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    selected = preferred_variant if preferred_variant in candidates else "kronos"
    return selected, dict(candidates[selected])


def quantitative_summary(
    candles: list[dict[str, Any]],
    forecast: list[dict[str, Any]],
    horizon: int,
    selected_return: float,
) -> dict[str, Any]:
    closes = [float(row["close"]) for row in candles]
    last_close = closes[-1]
    low_return = percent_change(last_close, min(float(row["low"]) for row in forecast))
    high_return = percent_change(last_close, max(float(row["high"]) for row in forecast))
    log_returns = [
        math.log(current / previous)
        for previous, current in zip(closes[-60:], closes[-59:], strict=False)
        if previous > 0 and current > 0
    ]
    daily_volatility = _standard_deviation(log_returns) * 100.0
    realized_volatility = daily_volatility * math.sqrt(252)
    range_width = high_return - low_return
    threshold = max(0.75, daily_volatility * math.sqrt(horizon) * 0.35)
    if selected_return >= threshold:
        outlook = "bullish"
    elif selected_return <= -threshold:
        outlook = "bearish"
    else:
        outlook = "neutral"
    if range_width >= 12 or realized_volatility >= 50:
        risk = "high"
    elif range_width >= 6 or realized_volatility >= 28:
        risk = "medium"
    else:
        risk = "low"
    return {
        "outlook": outlook,
        "quantitative_risk": risk,
        "outlook_threshold_percent": round(threshold, 8),
        "daily_volatility_percent": round(daily_volatility, 8),
        "realized_volatility_percent": round(realized_volatility, 8),
        "forecast_range_width_percent": round(range_width, 8),
    }


def combine_risk(quantitative_risk: str, jev_score: float) -> str:
    if jev_score >= 1.5:
        jev_risk = "high"
    elif jev_score >= 0.5:
        jev_risk = "medium"
    else:
        jev_risk = "low"
    return max((quantitative_risk, jev_risk), key=lambda value: RISK_ORDER[value])


def deterministic_warnings(stage1: dict[str, Any], stage2: dict[str, Any], threshold: float = 0.70) -> list[str]:
    warnings = [
        "Experimental output only; this is not a buy or sell recommendation.",
        "Jev judgment clarity describes answer-distribution concentration, not forecast accuracy.",
    ]
    sufficiency = float(stage1.get("nouls", {}).get("evidence_sufficient", 0.0))
    if sufficiency < 0.50:
        warnings.append("Ticker-specific textual evidence is insufficient; the final result falls back conservatively.")
    labels = {
        "demand_improving": "Evidence indicates a material demand change.",
        "cost_pressure": "Evidence indicates meaningful cost pressure.",
        "regulatory_legal_risk": "Evidence indicates regulatory or legal risk.",
        "liquidity_risk": "Evidence indicates liquidity risk.",
        "operational_risk": "Evidence indicates operational risk.",
        "governance_risk": "Evidence indicates governance risk.",
    }
    for key, message in labels.items():
        if float(stage1.get("nouls", {}).get(key, 0.0)) >= threshold:
            warnings.append(message)
    if float(stage2.get("nouls", {}).get("evidence_conflict", 0.0)) >= threshold:
        warnings.append("Textual evidence and the numerical forecast contain a meaningful conflict.")
    return warnings


def candidate_metrics(last_close: float, target: float, actual: float | None) -> dict[str, Any]:
    if actual is None:
        return {
            "terminal_error_percent": None,
            "absolute_percentage_error": None,
            "direction_correct": None,
        }
    error = percent_change(actual, target)
    target_direction = _sign(target - last_close)
    actual_direction = _sign(actual - last_close)
    return {
        "terminal_error_percent": round(error, 8),
        "absolute_percentage_error": round(abs(error), 8),
        "direction_correct": target_direction == actual_direction,
    }


def _sign(value: float, tolerance: float = 1e-9) -> int:
    return 1 if value > tolerance else -1 if value < -tolerance else 0


def _standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = sum(values) / len(values)
    return math.sqrt(sum((value - average) ** 2 for value in values) / (len(values) - 1))
