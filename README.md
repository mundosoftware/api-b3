# B3 Watch API

FastAPI backend plus a SwiftUI watchOS client for tracking B3 tickers, saving favorites, configuring price/percentage alerts, and receiving OneSignal push notifications.

## What Changed

- Added a SQLite-backed API for users, watch devices, companies, favorites, alert rules, and notification logs.
- Added a lightweight alert scheduler that fetches each due ticker once per cycle and evaluates every user rule that depends on that ticker.
- Added OneSignal server integration for standalone watchOS APNs token registration and user-targeted push delivery.
- Added a `watchos/B3TickerWatch` SwiftUI source tree for ticker search, favorites, alert creation, and watch push registration.
- Added `scripts/deploy_vps.sh` for one-command VPS deployment over SSH.
- Kept the legacy `/get-ticker/{ticker}`, `/get-tickers`, and `/get-stocks-by-order/{order}` routes.

## Backend

Run locally with the deployment script:

```bash
cp local.env.example local.env
./scripts/deploy_vps.sh local
```

For setup without starting the server:

```bash
./scripts/deploy_vps.sh local --no-start
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

Main endpoints:

- `GET /companies/search?q=PETR&limit=25`
- `GET /companies/{ticker}?refresh=true`
- `PUT /users/{user_id}`
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

When OneSignal/APNs reports stale push subscriptions during alert delivery, the server deletes the matching OneSignal subscriptions and removes the corresponding `user_devices` rows. This is the reliable cleanup point for uninstalls: Apple can delay invalid-token reporting, so removal may happen only after later send attempts. The explicit unregister endpoint is for cases where a client can still call the API, such as logout or a deliberate local notification cleanup.

Alert rules support:

- `metric`: `price` or `percent`
- `operator`: `gte` or `lte`
- `threshold`: target price or percent change
- `weekdays`: ISO weekday numbers, Monday `1` through Sunday `7`
- `start_time` and `end_time`: `HH:MM`
- `frequency_minutes`: minimum interval between checks for that rule
- `cooldown_minutes`: minimum interval between repeated notifications

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
./scripts/deploy_vps.sh vps
```

The script installs system packages, syncs the project, creates a Python venv, writes the remote `local.env`, installs a systemd service with one Uvicorn worker, and starts the API behind nginx when `PUBLIC_SERVER_PORT` differs from `SERVER_PORT` or HTTPS is enabled.

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
