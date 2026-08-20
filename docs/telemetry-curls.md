# Telemetry cURL Reference

These examples are Postman-importable. Copy one `curl` command at a time.

Postman collection: [`telemetry-postman-collection.json`](telemetry-postman-collection.json).

Replace these placeholders:

- `{{API_BASE}}`: replace this documentation IP with your deployed API URL.
- `{{ADMIN_TOKEN}}`: the value from `{{ADMIN_TOKEN}}` in `local.env`.
- `{{USER_ID}}`: the app user id to inspect.
- `{{TICKER}}`: ticker to inspect.
- `{{PRODUCT_ID}}`: StoreKit product id, for example `pro_year`, `pro_month`, or `lifetime_unlock`.

The server-owned trial product id is `trial_7_days`.

Record a paywall view from the app:

```bash
curl --request POST "{{API_BASE}}/users/{{USER_ID}}/iap/telemetry" \
  --header "Content-Type: application/json" \
  --data '{
    "event_type": "paywall_view",
    "platform": "ios",
    "environment": "production",
    "app_version": "1.2.0",
    "device_model": "iPhone",
    "device_os": "iOS 18.6",
    "language": "pt"
  }'
```

Record loaded StoreKit products, including the yearly trial and promotional offer:

```bash
curl --request POST "{{API_BASE}}/users/{{USER_ID}}/iap/telemetry" \
  --header "Content-Type: application/json" \
  --data '{
    "event_type": "products_loaded",
    "product_id": "pro_year",
    "product_type": "auto_renewable_subscription",
    "subscription_group_id": "22314965",
    "offer_id": "start_promo",
    "offer_type": "promotional",
    "storefront": "BRA",
    "currency_code": "BRL",
    "display_price": "R$ 24,90",
    "price": 24.90,
    "trial_days": 7,
    "status": "available",
    "platform": "ios",
    "environment": "production",
    "app_version": "1.2.0",
    "language": "pt"
  }'
```

Record a StoreKit product loading failure:

```bash
curl --request POST "{{API_BASE}}/users/{{USER_ID}}/iap/telemetry" \
  --header "Content-Type: application/json" \
  --data '{
    "event_type": "product_unavailable",
    "product_id": "pro_year",
    "status": "missing",
    "reason": "storekit_product_not_loaded",
    "message": "Could not load Pro Yearly from the App Store. Loaded products: lifetime_unlock, pro_month",
    "platform": "ios",
    "environment": "sandbox"
  }'
```

Record a successful purchase or trial enrollment:

```bash
curl --request POST "{{API_BASE}}/users/{{USER_ID}}/iap/telemetry" \
  --header "Content-Type: application/json" \
  --data '{
    "event_type": "purchase_succeeded",
    "product_id": "pro_year",
    "product_type": "auto_renewable_subscription",
    "transaction_id": "2000000000000001",
    "original_transaction_id": "2000000000000001",
    "status": "verified",
    "platform": "ios",
    "environment": "production"
  }'
```

Record a restore result:

```bash
curl --request POST "{{API_BASE}}/users/{{USER_ID}}/iap/telemetry" \
  --header "Content-Type: application/json" \
  --data '{
    "event_type": "restore_succeeded",
    "product_id": "lifetime_unlock",
    "product_type": "non_consumable",
    "status": "entitlement_active",
    "platform": "ios",
    "environment": "production"
  }'
```

Request a server-owned seven-day trial or an extension after expiry:

```bash
curl --request POST "{{API_BASE}}/users/{{USER_ID}}/iap/trial" \
  --header "Content-Type: application/json"
```

List asks to extend an expired seven-day trial:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-trial-extension-asks?user_id={{USER_ID}}&limit=50" \
  --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List current server-owned trials with current time, elapsed days and remaining days:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-trials?status=active&limit=50" \
  --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List one user's server-owned trial:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-trials?user_id={{USER_ID}}&limit=50" \
  --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

Extend a server-owned trial by three days:

```bash
curl --request POST "{{API_BASE}}/admin/telemetry/iap-trials/{{USER_ID}}/adjust" \
  --header "X-Admin-Token: {{ADMIN_TOKEN}}" \
  --header "Content-Type: application/json" \
  --data '{"days": 3, "reason": "support_extension"}'
```

Deduct days from a server-owned trial. If the deduction is greater than the remaining time, the server ends the trial immediately:

```bash
curl --request POST "{{API_BASE}}/admin/telemetry/iap-trials/{{USER_ID}}/adjust" \
  --header "X-Admin-Token: {{ADMIN_TOKEN}}" \
  --header "Content-Type: application/json" \
  --data '{"days": -10, "reason": "manual_deduction"}'
```

List IAP and subscription telemetry:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-events?user_id={{USER_ID}}&product_id={{PRODUCT_ID}}&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List unavailable StoreKit product diagnostics:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-events?event_type=product_unavailable&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List buying attempts, including purchase started, pending, succeeded, failed, cancelled and restore attempts:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-buying-attempts?user_id={{USER_ID}}&product_id={{PRODUCT_ID}}&hours=24&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List only purchase attempts, excluding restore attempts:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-buying-attempts?include_restore=false&hours=24&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List subscribed or paying users derived from the latest active entitlement telemetry:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-paying-users?environment=production&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List subscribed or paying users for one StoreKit product:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-paying-users?product_id={{PRODUCT_ID}}&environment=production&limit=50" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List subscription and IAP success/failure outcomes grouped by product, status and reason:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-outcomes?outcome=all&hours=24" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List subscription and IAP failures with reason counts:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-outcomes?outcome=failure&product_id={{PRODUCT_ID}}&hours=24" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

List subscription and IAP successes:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-outcomes?outcome=success&hours=24" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

Summarize recent IAP and subscription telemetry:

```bash
curl --request GET "{{API_BASE}}/admin/telemetry/iap-summary?user_id={{USER_ID}}&hours=24" --header "X-Admin-Token: {{ADMIN_TOKEN}}"
```

The IAP paying-user and outcome endpoints are operational telemetry derived from app-posted StoreKit events. Use App Store Server API or StoreKit transaction verification as the source of truth for billing enforcement.

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
