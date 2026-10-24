# Local Jev post-forecast experiment

This package is a local research harness. It does not import from or write to the iOS app, FastAPI routes, the production schema, workers, or deployment configuration. Kronos inference, fusion, caching, and reporting run locally on CPU. Jev calls TypeSafe's hosted API.

## Setup

From the project root, using the existing virtual environment:

```bash
venv/bin/python -m pip install -r requirements.txt
venv/bin/python -m pip install -r requirements-ai.txt
venv/bin/python -m pip install -r experiments/jev_post_forecast/requirements.txt
export TYPESAFE_API_KEY="..."
```

The key is read by the official SDK and is never added to requests stored by the experiment, `run.json`, CSV, or HTML.

## Run

```bash
scripts/run_jev_kronos_experiment.sh
scripts/run_jev_kronos_experiment.sh --mode live --tickers PETR4 --horizon 10
scripts/run_jev_kronos_experiment.sh --mode historical --refresh
scripts/run_jev_kronos_experiment.sh --mode all --offline
```

`--offline` forbids retrieval and model calls, so all Yahoo, CVM, document-text, and Jev cache entries must already exist. `--refresh` bypasses caches. The two flags are mutually exclusive.

To preview the report without a key, network access, or Kronos:

```bash
scripts/run_jev_kronos_experiment.sh \
  --mode report-only \
  --input experiments/jev_post_forecast/fixtures/report_run.json \
  --output artifacts/jev-post-forecast/fixture-preview
```

For a completed run, regenerating the report in place performs no calculation, network, or model call:

```bash
scripts/run_jev_kronos_experiment.sh --mode report-only \
  --input artifacts/jev-post-forecast/<run-id>/run.json
```

Outputs are ignored by Git:

- `.cache/jev-post-forecast/`: downloaded inputs, extracted text, and redacted Jev request/response records.
- `artifacts/jev-post-forecast/<run-id>/run.json`: complete calculations and provenance.
- `artifacts/jev-post-forecast/<run-id>/cases.csv`: one row per candidate.
- `artifacts/jev-post-forecast/<run-id>/index.html`: self-contained report with inline Plotly.
- `review.json`: downloaded from the report after ratings are entered; the form also persists in browser `localStorage`.

## Validation

```bash
venv/bin/python -m unittest discover -s experiments/jev_post_forecast/tests -v
```

Optional integration tests are opt-in because they can make network calls or load Kronos:

```bash
RUN_JEV_KRONOS_INTEGRATION=1 venv/bin/python -m unittest \
  experiments.jev_post_forecast.tests.test_integration -v
```

The historical panel is deliberately small and descriptive. Use it to assess evidence quality, coherence, stability, downside behavior, warning usefulness, latency, cost, and failure rates—not to claim statistical validation.
