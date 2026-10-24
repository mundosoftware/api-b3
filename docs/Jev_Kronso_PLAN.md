# Jev Post-Forecast Experiment

## Summary

Keep Kronos as the sole candle forecaster and use Jev as a post-forecast semantic judgment layer. This follows TypeSafe’s guidance—turn natural-language evidence into probabilistic features that ordinary code combines with structured data—without training another model. [TypeSafe use-case guidance](https://docs.typesafe.ai/concepts/use-case-map)

Each AI Outlook result will expose three experimental variants:

1. `kronos_jev`: unchanged Kronos target with Jev-refined outlook, risk, drivers, and warnings.
2. `jev_scenario`: Jev selects a downside, base, or upside target calculated from the Kronos range.
3. `jev_rule_adjusted`: code applies a bounded, transparent adjustment derived from Jev probabilities.

The iOS app will compare them through a segmented selector. The chart always retains the genuine Kronos path and overlays a marker for a differing Jev target.

## Backend and Evidence Pipeline

- Add a pluggable market-evidence service:
  - Yahoo Finance search provides up to six recent headline records per ticker; do not scrape article bodies.
  - CVM IPE provides up to six relevant disclosures, including material facts, market communications, financial information, and administration meetings. Sync the current and previous annual ZIP archives daily; CVM updates current data weekly. [Official CVM IPE dataset](https://dados.cvm.gov.br/dataset/cia_aberta-doc-ipe)
  - Resolve stock ticker to CNPJ/CVM code through an isolated B3 company-directory adapter, verify the exact ticker, and cache the mapping. If resolution fails—or for unsupported ETFs, FIIs, and BDRs—continue with Yahoo evidence only.
  - Extract text from supported CVM HTML/text/PDF documents; use metadata only for unsupported or scanned documents.
  - Include only evidence published at or before the analysis timestamp. Use a lookback of `clamp(horizon × interval_days, 7, 90)` calendar days, a maximum of 12 deduplicated documents, and a 24,000-character total evidence budget.

- Persist evidence and inference state in idempotently migrated SQLite tables:
  - `company_regulatory_ids` for ticker/CNPJ/CVM mappings.
  - `market_evidence` for normalized, deduplicated headlines and disclosures.
  - `jev_analysis_cache` keyed by state hash, pinned model, and question-set version.
  - `ai_outlook_variant_predictions` for later outcome evaluation.
  - `ai_outlook_variant_selections` for the latest selection and selection-change count per job.

- Add `JevPostForecastAnalyzer` after Kronos inference and before the current decision-payload composition in [`src/ai_analysis.py`](/Users/nonatosousa/Documents/Dev/Fullstack/Trade-Alert/src/ai_analysis.py:300). Send one structured state containing the ticker, interval, horizon, Kronos target/range, technical indicators, three price candidates, and evidence documents.

- Ask all Jev questions in one request:
  - `combined_outlook`: Choice among `bullish`, `neutral`, `bearish`, and `insufficient`.
  - `scenario`: Choice among `downside`, `base`, `upside`, and `insufficient`.
  - `materiality`: four-level Score from routine to transformative.
  - `semantic_risk`: three-level Score with concrete low/medium/high conditions.
  - Nouls for forecast support, improving demand, cost pressure, regulatory/legal risk, liquidity risk, operational risk, and governance risk.
  - Store the full probabilities, Score values, confidence, model version, token usage, and question-set version. Produce user text from deterministic templates; Jev does not generate summaries or warnings.

- Use the synchronous `typesafe-sdk` client because AI Outlook already runs in a worker thread. Configure two retries, a 10-second timeout, server-side credentials, production logging without request bodies, and a pinned `jev-1.13.0` model. [TypeSafe Python SDK](https://docs.typesafe.ai/sdk/python)

## Variant Composition and Public Interfaces

Let `P` be the last close, `K` the Kronos target, `E` its expected percentage change, and `L/H` the existing forecast-low/high percentages.

- `kronos_jev`:
  - Target remains `K`.
  - Use Jev’s combined outlook unless it returns `insufficient`; otherwise retain the current deterministic outlook.
  - Convert semantic risk to low/medium/high using Score boundaries `<0.5`, `<1.5`, and `≥1.5`, then take the more conservative of semantic and existing quantitative risk.
  - Append versioned warning templates for risk Nouls at or above `0.70` and a contradiction warning when forecast-support probability is at or below `0.30`.

- `jev_scenario`:
  - Downside candidate: `P × (1 + L/100)`.
  - Base candidate: `K`.
  - Upside candidate: `P × (1 + H/100)`.
  - Use Jev’s scenario Choice; `insufficient` falls back to base.
  - Recalculate expected change and classify outlook with the existing volatility-aware threshold. Reuse the conservative semantic risk and warnings.

- `jev_rule_adjusted`:
  - Direction `d = p(bullish) − p(bearish)`.
  - Materiality `m = clamp(materiality_score / 3, 0, 1)`.
  - Available room is `H − E` when `d ≥ 0`, otherwise `E − L`.
  - Adjusted return is `clamp(E + d × m × room, L, H)`.
  - Target is `P × (1 + adjusted_return/100)`.
  - `insufficient` or missing evidence sets `d = 0`, preserving the Kronos target.

- Preserve every existing top-level field in `DecisionSupportOut` for older clients. Extend [`src/models.py`](/Users/nonatosousa/Documents/Dev/Fullstack/Trade-Alert/src/models.py:58) with optional:
  - `variants: list[DecisionVariantOut]`
  - `semantic_analysis: SemanticAnalysisOut | None`
  - `evidence: list[EvidenceItemOut]`
  - Variant IDs are exactly `kronos_jev`, `jev_scenario`, and `jev_rule_adjusted`.
  - Variant fields include availability/fallback state, target, expected change, outlook, risk, `evidence_clarity`, deterministic text, and marker price.
  - Never expose Jev confidence as forecast confidence; label Choice confidence as “Evidence clarity.”

- Add:
  - `PUT /users/{user_id}/ai-outlook/jobs/{job_id}/variant-selection` to upsert the selected variant without creating event spam.
  - `GET /admin/telemetry/ai-outlook/variants` to report selection counts and completed target-error metrics by variant, interval, and horizon.

- Add configuration for TypeSafe credentials/model/timeouts and evidence limits. Seed a separate `ai_outlook_jev_experiment` feature flag as disabled. With the flag disabled, no evidence or Jev calls occur. With Jev unavailable, `kronos_jev` falls back visibly to the existing result and the other two variants are disabled.

## iOS, Evaluation, and Rollout

- Update [`CompanyDetailView.swift`](/Users/nonatosousa/Documents/Dev/Fullstack/Trade-Alert/Trade%20Altert/Trade%20Altert/CompanyDetailView.swift:714) with:
  - An “Experimental Jev comparison” label and segmented selector for Kronos, Scenario, and Adjustment.
  - The selected variant drives target, percentage, outlook, risk, summary, action, drivers, and warnings.
  - “Evidence clarity” replaces “Confidence” for variant data.
  - The Kronos line remains unchanged; add a labeled target marker at the final forecast timestamp when the selected target differs.
  - A compact evidence section shows up to five titles, publishers, dates, and external links.
  - Disable unavailable segments and explain whether the cause is no evidence, configuration, or a service failure.
  - Localized Portuguese and English labels, while preserving existing investment-risk disclosures.

- Record each generated variant against the final Kronos forecast timestamp. An hourly evaluator groups due records by ticker/interval, fetches candles once, and uses the first actual candle at or after the target timestamp. Persist percentage error, absolute percentage error, and directional correctness idempotently.

- Update deployment scripts, environment examples, README, publisher copy, and privacy disclosures to cover TypeSafe processing, Yahoo headlines, CVM documents, experimental variants, and selection/outcome telemetry.

## Test Plan and Defaults

- Unit-test evidence cutoff, deduplication, ticker/CVM resolution, text limits, malformed documents, and metadata-only fallback.
- Test the Jev state and typed-answer mapping with a fake client; verify one call drives all variants and cached inputs make no call.
- Test every price formula, range bound, insufficient-evidence fallback, conservative risk rule, warning threshold, and invalid/non-finite value rejection.
- Verify old cached responses and older clients remain valid because all new response fields are optional.
- Test jobs with TypeSafe disabled, missing keys, timeout, rate limit, malformed response, no evidence, and complete success.
- Test selection upserts and outcome evaluation for daily, weekly, and monthly horizons, including delayed/missing candles and repeated evaluator runs.
- Test iOS decoding with old/new payloads, selector behavior, disabled variants, localization, evidence links, and target-marker placement.
- Acceptance requires unchanged Kronos candles, no leaked API key or document bodies in logs, operational fallback on every external failure, and admin metrics for both forecast outcomes and user selections.

Defaults: experiment flag off; TypeSafe optional; model pinned to `jev-1.13.0`; Yahoo headline-only news; CVM full text when extractable; Portuguese evidence sent unchanged with English questions; 15-minute Yahoo/Jev caches; daily CVM sync; no trained model; all Jev-derived prices explicitly labeled experimental rather than calibrated forecasts.
