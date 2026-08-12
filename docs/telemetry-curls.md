# Telemetry cURL Reference

These examples are Postman-importable. Copy one `curl` command at a time.

Replace these placeholders:

- `{{API_BASE}}`: replace this documentation IP with your deployed API URL.
- `{{ADMIN_TOKEN}}`: the value from `{{ADMIN_TOKEN}}` in `local.env`.
- `{{USER_ID}}`: the app user id to inspect.
- `{{TICKER}}`: ticker to inspect.

Run a check cycle manually:

```bash
curl --request POST "{{API_BASE}}/admin/run-checks" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List live alert due/skipped status, including server UTC time and rule-local time:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/alert-status?user_id={{USER_ID}}&ticker=PETR4&enabled=true&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

Check a specific moment. This example is 10:00 BRT, which is 13:00 UTC:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/alert-status?user_id={{USER_ID}}&ticker=PETR4&now=2026-08-12T13:00:00Z" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List alert scheduler runs:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/alert-runs?limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List failed scheduler runs only:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/alert-runs?status=error&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List alert event logs:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/alert-events?user_id={{USER_ID}}&ticker=PETR4&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List alert failures only:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/alert-events?event_type=failure&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List quote lookup failures:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/alert-events?event_type=failure&reason=quote_lookup_failed&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List notification logs:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/notifications?user_id={{USER_ID}}&ticker=PETR4&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List notification failures only:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/notifications?failures_only=true&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List registered devices with token IDs masked:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/devices?user_id={{USER_ID}}&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List only watchOS devices:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/devices?user_id={{USER_ID}}&platform=watchos&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List combined failures and reasons from alert events plus notification logs:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/failures?user_id={{USER_ID}}&ticker=PETR4&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

User devices

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/devices?user_id={{USER_ID}}&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

User preferences

```bash
curl --request GET "{{API_BASE}}/users/{{USER_ID}}/notification-preferences"
```