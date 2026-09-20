# Meta WhatsApp template integration

Trade Alert emits 23 operational event names through six approved WhatsApp
templates. Universal Notifier uses template delivery by default and does not
fall back to free-form text when a template is missing or rejected.

| Template | Producer events |
| --- | --- |
| `un_trade_alert_user_created_v1` | `user.created` |
| `un_trade_alert_iap_event_v1` | Purchase, restore, subscription, renewal, cancellation, expiration, revocation, and refund events under `iap.*` |
| `un_trade_alert_trial_event_v1` | `iap.trial_status`, `iap.trial_started`, `iap.trial_extension_requested`, `iap.trial_adjusted` |
| `un_trade_alert_ai_outlook_event_v1` | `ai_outlook.attempt`, `ai_outlook.failed`, `ai_outlook.succeeded` |
| `un_trade_alert_alert_failure_v1` | `alert.failure` |
| `un_trade_alert_push_failure_v1` | `notification.failure` |

## Provision and roll out

1. Run `./scripts/install_project_dependencies.sh` and open
   `.deps/Universal-Notifier`.
2. Import
   `postman/Trade-Alert-Meta-Templates.postman_collection.json` into Postman.
3. Put `access_token` and `waba_id` in a private Postman environment, select the
   exact `template_language`, and run each request in **Create
   approved-template candidates** once.
4. Use **Template status** until all six exact template names and the configured
   language report `APPROVED`. A successful create response is not approval.
5. Set these values in the notifier's private `.env.local`:

   ```ini
   WHATSAPP_ENABLED=true
   WHATSAPP_DELIVERY_MODE=template
   WHATSAPP_TEMPLATE_LANGUAGE=en_US
   WHATSAPP_PHONE_NUMBER_ID=...
   WHATSAPP_ACCESS_TOKEN=...
   WHATSAPP_DESTINATION_NUMBER=...
   ```

6. Run `npm test` inside `.deps/Universal-Notifier`, then deploy Trade Alert.
   Deployment rejects text mode or an incomplete 23-event Trade Alert catalog.
7. Confirm `/readyz`, send the Postman smoke request to an opted-in destination,
   and inspect `/v1/status` or `/metrics` for the template name and result.

Template delivery permits business-initiated messages outside the 24-hour
customer-service window, but it does not waive opt-in, template approval,
quality, category, rate, or account restrictions.

## Failure behavior

- Unknown Trade Alert event names are logged and are not queued by the Python
  producer.
- Unknown runtime mappings and Meta 4xx rejections are terminal failures.
- Timeouts, transport errors, HTTP 429, and provider 5xx responses are retried.
- A rejected template is never resent as free-form text.
- Successful dedupe keys remain persisted across notifier restarts.
