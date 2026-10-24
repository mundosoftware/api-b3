"""Self-contained HTML and CSV output for human review."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .storage import write_json


def write_artifacts(run: dict[str, Any], output_dir: Path, *, write_run: bool = True) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_path = output_dir / "run.json"
    if write_run:
        write_json(run_path, run)
    csv_path = output_dir / "cases.csv"
    csv_path.write_text(cases_csv(run), encoding="utf-8")
    html_path = output_dir / "index.html"
    html = render_report(run)
    _assert_report_safe(html)
    html_path.write_text(html, encoding="utf-8")
    return {"run": run_path, "csv": csv_path, "html": html_path}


def cases_csv(run: dict[str, Any]) -> str:
    columns = [
        "run_id",
        "case_id",
        "ticker",
        "case_kind",
        "analysis_cutoff",
        "outcome_status",
        "variant",
        "selected",
        "last_close",
        "target_price",
        "return_percent",
        "actual_target_price",
        "terminal_error_percent",
        "absolute_percentage_error",
        "direction_correct",
        "improvement_vs_kronos_ape",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for case in run.get("cases", []):
        for name, candidate in case.get("candidates", {}).items():
            metrics = candidate.get("metrics", {})
            writer.writerow(
                {
                    "run_id": run.get("run_id"),
                    "case_id": case.get("case_id"),
                    "ticker": case.get("ticker"),
                    "case_kind": case.get("case_kind"),
                    "analysis_cutoff": case.get("analysis_cutoff"),
                    "outcome_status": case.get("outcome_status"),
                    "variant": name,
                    "selected": name == case.get("selection", {}).get("selected_variant"),
                    "last_close": case.get("last_close"),
                    "target_price": candidate.get("target_price"),
                    "return_percent": candidate.get("return_percent"),
                    "actual_target_price": case.get("actual_target_price"),
                    "terminal_error_percent": metrics.get("terminal_error_percent"),
                    "absolute_percentage_error": metrics.get("absolute_percentage_error"),
                    "direction_correct": metrics.get("direction_correct"),
                    "improvement_vs_kronos_ape": candidate.get("improvement_vs_kronos_ape"),
                }
            )
    return buffer.getvalue()


def render_report(run: dict[str, Any]) -> str:
    try:
        from plotly.offline import get_plotlyjs
    except ImportError as exc:
        raise RuntimeError("plotly is required; install the experiment requirements") from exc
    environment = Environment(
        loader=FileSystemLoader(Path(__file__).with_name("templates")),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["json_pretty"] = lambda value: json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    environment.filters["pct"] = lambda value: "—" if value is None else f"{float(value):+.2f}%"
    environment.filters["num"] = lambda value: "—" if value is None else f"{float(value):,.2f}"
    template = environment.get_template("report.html.j2")
    charts = {case["case_id"]: _chart_payload(case) for case in run.get("cases", [])}
    return template.render(
        run=run,
        charts=charts,
        plotly_js=get_plotlyjs(),
        run_json=json.dumps(run, ensure_ascii=False).replace("</", "<\\/"),
    )


def _chart_payload(case: dict[str, Any]) -> dict[str, str]:
    case_id = re.sub(r"[^A-Za-z0-9_-]", "-", case["case_id"])
    history = case.get("historical_candles", [])
    forecast = case.get("forecast", [])
    realized = case.get("realized_future", [])
    price_traces: list[dict[str, Any]] = [
        {
            "name": "Historical close",
            "type": "scatter",
            "mode": "lines",
            "x": [row["timestamp"] for row in history],
            "y": [row["close"] for row in history],
            "line": {"color": "#64748b", "width": 2},
        },
        {
            "name": "Kronos path",
            "type": "scatter",
            "mode": "lines+markers",
            "x": [row["timestamp"] for row in forecast],
            "y": [row["close"] for row in forecast],
            "line": {"color": "#0ea5e9", "dash": "dot", "width": 2},
        },
    ]
    if realized:
        price_traces.append(
            {
                "name": "Realized path",
                "type": "scatter",
                "mode": "lines+markers",
                "x": [row["timestamp"] for row in realized],
                "y": [row["close"] for row in realized],
                "line": {"color": "#22c55e", "width": 3},
            }
        )
    target_x = forecast[-1]["timestamp"] if forecast else case["analysis_cutoff"]
    colors = {"kronos": "#0ea5e9", "semantic_scenario": "#f59e0b", "rule_adjusted": "#a855f7"}
    for name, candidate in case.get("candidates", {}).items():
        selected = name == case.get("selection", {}).get("selected_variant")
        price_traces.append(
            {
                "name": f"{name}{' (selected)' if selected else ''}",
                "type": "scatter",
                "mode": "markers",
                "x": [target_x],
                "y": [candidate["target_price"]],
                "marker": {"color": colors.get(name, "#94a3b8"), "size": 15 if selected else 10, "symbol": "diamond"},
            }
        )
    stage1 = case["jev_stage1"]["response"]
    stage2 = case["jev_stage2"]["response"]
    bars: list[tuple[str, float, str]] = []
    bars.extend((f"direction · {name}", value, "Stage 1 direction") for name, value in stage1["choices"]["semantic_direction"]["probabilities"].items())
    bars.extend((f"materiality · {name}", value, "Stage 1 materiality") for name, value in stage1["scores"]["materiality"]["probabilities"].items())
    bars.extend((f"variant · {name}", value, "Stage 2 variant") for name, value in stage2["choices"]["preferred_variant"]["probabilities"].items())
    bars.extend((f"risk · {name}", value, "Stage 2 risk") for name, value in stage2["scores"]["combined_risk"]["probabilities"].items())
    bars.extend(
        (f"risk signal · {name}", value, "Stage 1 risk signals")
        for name, value in stage1["nouls"].items()
        if name in {"cost_pressure", "regulatory_legal_risk", "liquidity_risk", "operational_risk", "governance_risk"}
    )
    bars.extend((f"support · {name.removeprefix('supports_')}", value, "Candidate support") for name, value in stage2["nouls"].items() if name.startswith("supports_"))
    groups = list(dict.fromkeys(group for _, _, group in bars))
    probability_traces = [
        {
            "name": group,
            "type": "bar",
            "orientation": "h",
            "x": [value for _, value, item_group in bars if item_group == group],
            "y": [label for label, _, item_group in bars if item_group == group],
        }
        for group in groups
    ]
    return {
        "price_id": f"price-{case_id}",
        "price_data": json.dumps(price_traces, ensure_ascii=False).replace("</", "<\\/"),
        "price_layout": json.dumps(
            {
                "height": 420,
                "margin": {"l": 58, "r": 24, "t": 18, "b": 55},
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(0,0,0,0)",
                "font": {"color": "#cbd5e1"},
                "xaxis": {"gridcolor": "#243147"},
                "yaxis": {"title": "Price (BRL)", "gridcolor": "#243147"},
                "legend": {"orientation": "h", "y": -0.2},
                "hovermode": "x unified",
            }
        ),
        "probability_id": f"probability-{case_id}",
        "probability_data": json.dumps(probability_traces, ensure_ascii=False).replace("</", "<\\/"),
        "probability_layout": json.dumps(
            {
                "height": max(440, len(bars) * 27),
                "barmode": "group",
                "margin": {"l": 190, "r": 24, "t": 18, "b": 45},
                "paper_bgcolor": "rgba(0,0,0,0)",
                "plot_bgcolor": "rgba(0,0,0,0)",
                "font": {"color": "#cbd5e1"},
                "xaxis": {"range": [0, 1], "title": "Probability", "gridcolor": "#243147"},
                "yaxis": {"automargin": True},
            }
        ),
    }


def _assert_report_safe(html: str) -> None:
    lowered = html.lower()
    forbidden = ("authorization: bearer", '"authorization"', '"api_key"', "typesafe_api_key")
    if any(item in lowered for item in forbidden):
        raise ValueError("Refusing to write report containing credential-like data")
