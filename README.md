# Trade Alert

FastAPI backend plus SwiftUI iOS/watchOS clients for tracking B3 tickers, saving favorites, configuring price/percentage alerts, receiving OneSignal push notifications, and using AI Outlook decision support.

## What Changed

- Added a SQLite-backed API for users, watch devices, companies, favorites, alert rules, and notification logs.
- Added a lightweight alert scheduler that fetches each due ticker once per cycle and evaluates every user rule that depends on that ticker.
- Added OneSignal server integration for standalone watchOS APNs token registration and user-targeted push delivery.
- Added AI Outlook candle analysis and decision support using Yahoo chart candles, Kronos-compatible forecasting, cached prediction results, and support/resistance visual data for the native iOS app.
- Added per-user AI Outlook activation plus a global admin feature flag, maintenance state, FTUE disclosure, telemetry visibility, and localized PT-BR/EN iOS copy.
- Added a `watchos/B3TickerWatch` SwiftUI source tree for ticker search, favorites, alert creation, and watch push registration.
- Added `scripts/run_ai_local.sh` for local AI Outlook validation and updated `scripts/deploy_vps.sh` for one-command VPS deployment with Kronos runtime setup.
- Kept the legacy `/get-ticker/{ticker}`, `/get-tickers`, and `/get-stocks-by-order/{order}` routes.

## Backend

Run locally with the deployment script:

```bash
cp local.env.example local.env
./scripts/deploy_vps.sh local
```

For setup without starting the server:

```bash
sudo bash scripts/deploy_vps.sh local --no-start
```

Local mode creates `venv`, installs dependencies, initializes SQLite at `LOCAL_DATABASE_PATH`, disables the background checker and OneSignal by default through `LOCAL_CHECK_LOOP_ENABLED=false` and `LOCAL_ONESIGNAL_ENABLED=false`, then starts Uvicorn with reload.

Important env vars:

- `DATABASE_PATH`: SQLite file path, default `database/app.db`.
- `ONESIGNAL_APP_ID`: OneSignal app id for the iOS companion app, configured with APNs Bundle ID `com.mundosoftware.tradealert`.
- `ONESIGNAL_REST_API_KEY`: OneSignal REST API key for the iOS companion app.
- `ONESIGNAL_WATCH_APP_ID`: separate OneSignal app id for standalone watchOS, configured with APNs Bundle ID `com.mundosoftware.tradealert.watchkitapp`.
- `ONESIGNAL_WATCH_REST_API_KEY`: OneSignal REST API key for the standalone watchOS app.
- `ADMIN_TOKEN`: required header value for `POST /admin/run-checks` when set.
- `CHECK_LOOP_SECONDS`: background scheduler interval.
- `QUOTE_CACHE_TTL_SECONDS`: quote cache age before a live refresh.
- `AI_OUTLOOK_GLOBAL_ENABLED`: initial global AI Outlook availability seeded into the database.
- `AI_OUTLOOK_WORKER_ENABLED`: starts the persisted AI Outlook job worker.
- `AI_OUTLOOK_WORKER_POLL_SECONDS`: idle polling interval for queued AI Outlook jobs.
- `AI_OUTLOOK_JOB_MAX_ATTEMPTS`: total job attempts, default `3` for one initial run plus two retries.
- `AI_OUTLOOK_RETRY_DELAY_SECONDS`: delay before retrying a failed AI Outlook attempt.
- `CANDLE_CACHE_TTL_SECONDS`: Yahoo chart candle cache age.
- `PREDICTION_CACHE_TTL_SECONDS`: AI Outlook prediction cache age.
- `KRONOS_ENABLED`: enables Kronos-backed forecasting when its source/dependencies are available.
- `KRONOS_REQUIRED`: fails AI Outlook requests instead of falling back when Kronos cannot run.
- `KRONOS_INSTALL`: deploy script option to clone/update Kronos on the VPS.
- `KRONOS_REPO_PATH`: local Kronos checkout path, defaulted by deploy scripts when omitted.
- `KRONOS_MODEL_NAME`: default `NeoQuasar/Kronos-base`.
- `KRONOS_TOKENIZER_NAME`: default `NeoQuasar/Kronos-Tokenizer-base`.
- `KRONOS_MAX_CONTEXT`, `KRONOS_SAMPLE_COUNT`, `KRONOS_TEMPERATURE`, `KRONOS_TOP_P`, `KRONOS_DEVICE`: Kronos inference controls.
- `KRONOS_CACHE_DIR`, `HF_HOME`, `TORCH_HOME`: model/cache locations for VPS deployment.

Main endpoints:

- `GET /health`
- `GET /features/ai-outlook`
- `GET /companies/search?q=PETR&limit=25`
- `GET /companies/{ticker}?refresh=true`
- `GET /companies/{ticker}/candles?range=6mo&interval=1d`
- `GET /companies/{ticker}/ai-analysis?horizon=10&range=6mo&refresh=true`
- `POST /users/{user_id}/ai-outlook/jobs`
- `GET /users/{user_id}/ai-outlook/jobs/{job_id}`
- `DELETE /users/{user_id}/ai-outlook/jobs/{job_id}`
- `PUT /users/{user_id}`
- `GET /users/{user_id}/notification-preferences`
- `PUT /users/{user_id}/notification-preferences`
- `POST /users/{user_id}/devices/watchos`
- `POST /users/{user_id}/devices/ios`
- `POST /users/{user_id}/devices/{ios|watchos}/unregister`
- `GET /users/{user_id}/favorites`
- `POST /users/{user_id}/favorites`
- `DELETE /users/{user_id}/favorites/{ticker}`
- `GET /users/{user_id}/alerts?ticker=PETR4`
- `POST /users/{user_id}/alerts`
- `PATCH /users/{user_id}/alerts/{alert_id}`
- `DELETE /users/{user_id}/alerts/{alert_id}`
- `POST /admin/run-checks`
- `GET /admin/features/ai-outlook`
- `PUT /admin/features/ai-outlook`
- `GET /admin/telemetry/alert-status`
- `GET /admin/telemetry/alert-runs`
- `GET /admin/telemetry/alert-events`
- `GET /admin/telemetry/ai-outlook/jobs`
- `GET /admin/telemetry/ai-outlook/usage`
- `GET /admin/telemetry/notifications`
- `GET /admin/telemetry/devices`
- `GET /admin/telemetry/users`
- `GET /admin/telemetry/failures`

When OneSignal/APNs reports stale push subscriptions during alert delivery, the server deletes the matching OneSignal subscriptions and removes the corresponding `user_devices` rows. This is the reliable cleanup point for uninstalls: Apple can delay invalid-token reporting, so removal may happen only after later send attempts. The explicit unregister endpoint is for cases where a client can still call the API, such as logout or a deliberate local notification cleanup.

Telemetry endpoints require the same `X-Admin-Token` as `POST /admin/run-checks`. cURL examples are in `docs/telemetry-curls.md`.

## AI Outlook

AI Outlook is off for each user by default. The iOS app shows the benefits, Kronos paper/source links, and a centered text CTA that can activate or deactivate the feature for that user. First activation presents a disclosure that AI output can be wrong, market data can be stale, and the result is decision support rather than investment advice. When the global admin flag is disabled, the app shows the AI Outlook maintenance UI and the backend returns the public feature state from `GET /features/ai-outlook`.

The backend fetches free Yahoo chart candles, caches candle and prediction results in SQLite, runs Kronos when configured, and stores AI Outlook work in persisted jobs. The iOS app creates a job through `POST /users/{user_id}/ai-outlook/jobs`, polls `GET /users/{user_id}/ai-outlook/jobs/{job_id}`, and receives a push notification when the job succeeds or exhausts retries. The deployed worker processes one AI Outlook job at a time, retries failed jobs twice by default, and returns the decision-support payload in the job `result` when complete. If Kronos is unavailable and `KRONOS_REQUIRED=false`, the service uses the statistical fallback so the UI and local tests still work.

Local AI validation:

```bash
sudo bash scripts/run_ai_local.sh --install-kronos
```

Useful options:

- `--no-start`: install, test, and initialize the database without starting Uvicorn.
- `--skip-tests`: skip the unit test run.
- `--ticker PETR4`: change the smoke-test ticker shown after startup.
- `--host 127.0.0.1 --port 8000`: change the local bind address.

The script installs `requirements.txt`, optionally installs `requirements-ai.txt`, clones or updates Kronos under `.deps/Kronos`, initializes `database/local-ai.db`, and starts `uvicorn main:app --reload`.

Admin control:

```bash
curl --request PUT "$API_BASE/admin/features/ai-outlook" \
  --header "X-Admin-Token: $ADMIN_TOKEN" \
  --header "Content-Type: application/json" \
  --data '{"enabled": false}'
```

The global flag controls availability for every user. Per-user activation remains stored as `ai_outlook_enabled` in notification preferences and appears in admin telemetry/device reports.

The Postman collection in `docs/telemetry-postman-collection.json` includes `/health`, public AI Outlook availability, admin enable/disable calls, and user preference telemetry for `ai_outlook_enabled`.

Alert rules support:

- `metric`: `price` or `percent`
- `operator`: `gte` or `lte`
- `threshold`: target price or percent change
- `weekdays`: ISO weekday numbers, Monday `1` through Sunday `7`
- `start_time` and `end_time`: `HH:MM`
- `frequency_minutes`: minimum interval between checks for that rule
- `cooldown_minutes`: minimum interval between repeated notifications

## iOS

The native iOS app source is under `Trade Altert/Trade Altert`.

AI Outlook appears in the company detail screen. It loads the global feature flag, keeps user activation off by default through `ai_outlook_enabled`, shows the activation benefits and Kronos research/source links, displays the FTUE disclosure on first activation, shows loading states while fetching or changing the day range, and renders historical/forecast candle support data from `/companies/{ticker}/ai-analysis`. If the admin disables AI Outlook globally, the section switches to the maintenance UI.

Set `AppConfig.apiBaseURL` to the deployed VPS URL, for example `https://203.0.113.10`.

## watchOS

The watch app source is under `watchos/B3TickerWatch`.

1. Create a watchOS App target in Xcode named `B3TickerWatch`.
2. Add the Swift files from `watchos/B3TickerWatch` to the Watch App target.
3. Set `AppConfig.apiBaseURL` to the deployed VPS URL, for example `https://203.0.113.10`.
4. Enable Push Notifications for the Watch App target.
5. Use `development` for debug/ad-hoc builds and `production` for TestFlight/App Store in `AppConfig.deviceEnvironment`.

Standalone watchOS uses APNs directly on the watch. The watch sends its APNs token to this API, and the server registers that token with OneSignal so the REST API key never ships in the watch app.
The watch APNs token belongs to the watch app bundle, so it must be registered in a separate OneSignal app whose Apple APNs settings use `com.mundosoftware.tradealert.watchkitapp`. Do not reuse the iOS OneSignal app configured for `com.mundosoftware.tradealert`; APNs will reject watch-only sends with `DeviceTokenNotForTopic`.

## VPS Deploy

Create a local `local.env` from `local.env.example`, fill the VPS and OneSignal values, then run:

```bash
sudo bash scripts/deploy_vps.sh vps
```

The script installs system packages, syncs the project, creates a Python venv, writes the remote `local.env`, installs a systemd service with one Uvicorn worker, and starts the API behind nginx when `PUBLIC_SERVER_PORT` differs from `SERVER_PORT` or HTTPS is enabled.

When `KRONOS_INSTALL=true`, the deploy script also installs `requirements-ai.txt`, clones or updates Kronos at `${APP_DIR}/.deps/Kronos`, creates Hugging Face/Torch cache directories under `${APP_DIR}/.cache/kronos` by default, and writes the AI Outlook/Kronos env vars into the remote `local.env`. The initial `AI_OUTLOOK_GLOBAL_ENABLED` value seeds the database; later admin changes are persisted through `/admin/features/ai-outlook`.

For Oracle Cloud, keep the Python API private on `SERVER_PORT=8000`, expose nginx on `HTTP_SERVER_PORT=80` for certificate validation, and expose HTTPS on `HTTPS_SERVER_PORT=443`. With that setup, the public API URL is `https://<VPS_HOST>` and the health URL is `https://<VPS_HOST>/health`; do not use `:8000` unless Oracle ingress also allows port 8000.

The deploy script waits for `http://127.0.0.1:<SERVER_PORT>/health` from inside the VPS, then verifies the public health URL from your machine. If the internal check passes but the public URL fails, check Oracle ingress rules and any OS firewall for `80/tcp` and `443/tcp`. By default `HOST_FIREWALL_ALLOW_PORTS=80,443` attempts to open both ports through UFW when present and iptables when UFW is absent; set `HOST_FIREWALL_ALLOW_PORTS=false` to skip that step.

HTTPS uses a Let's Encrypt IP address certificate requested with Certbot's `--ip-address` and `--preferred-profile shortlived` flags. These certificates are valid for about six days, so the deploy script installs a systemd renewal timer named `<SERVICE_NAME>-cert-renew.timer`.

Useful remote diagnostics:

```bash
sudo systemctl status b3-watch-api --no-pager -l
sudo journalctl -u b3-watch-api -n 120 --no-pager
sudo ss -ltnp | grep ':8000 '
sudo ss -ltnp | grep ':80 '
sudo systemctl status nginx --no-pager -l
sudo systemctl list-timers '*cert-renew*'
sudo ufw status verbose
sudo iptables -S INPUT
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1/health
curl -fsS https://127.0.0.1/health -k
curl -fsS https://203.0.113.10/health
```

This is designed for a small single-node VPS with 1 vCPU and 6 GB RAM. Use the IP address directly; no domain is required.
