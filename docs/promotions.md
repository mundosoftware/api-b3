# Promotions and native StoreKit redemption

Trade Alert imports Apple one-time offer codes into SQLite and manages them through a reusable admin panel. The source CSV remains a local secret and is ignored by Git, but it is not required to deploy the API. Codes can be imported later from the admin panel.

## Black Friday 2026 defaults

- Campaign: `black-friday-2026`
- Product: `lifetime_unlock`
- Brazil offer price: R$ 29.90
- Display discount: approximately 40%
- Starts: November 1, 2026
- Ends: December 31, 2026 at 23:59:59 in `America/Fortaleza`
- Home modal, optional “don’t show again,” and Plans placement are enabled.
- CSV: configured by `PROMOTION_CODES_CSV_PATH`

When the configured CSV exists at runtime, database initialization imports every non-empty row idempotently. Expected rows are `code,redemption_url` with no required header. A missing file is accepted and creates no codes; administrators can import it later through the panel. Importing never resets an administrator’s enabled, reserved, or redeemed state.

## Admin panel

Open `/admin` in production or `/dev/admin` in the development deployment. The legacy `/admin/promotions` page URL redirects to `/admin`. The page keeps the admin token in browser `localStorage` and sends it only in the `X-Admin-Token` header. The protected APIs support:

- campaign enable/disable;
- creation of additional disabled campaigns and browser-side CSV import;
- start/end dates, product, price, discount, localized title/body/CTA copy;
- localized and independently visible body, Plans notice, App Store price disclaimer,
  automatic-copy instruction, native redemption-sheet notice, and valid-until label;
- home and paywall visibility;
- whether Home offers a “don’t show again” toggle;
- individual code enable/disable;
- available, reserved, and redeemed counts;
- the user and StoreKit transaction associated with a reported redemption.

The same panel now uses a collapsible Material Icons sidebar for Overview, Promotions, App versions, and Telemetry. Its visible version appears immediately above Logout as `v.1.2.0`, derived during deployment from the nearest reachable Git tag matching `RELEASE_1.2.0`. Logout stays at the bottom of the sidebar and clears the locally stored admin token. The telemetry area covers the safe operational/read endpoints in `docs/telemetry-postman-collection.json`; direct WhatsApp test delivery and synthetic-user creation remain Postman-only to avoid accidental notifications.

The valid-until copy uses `[date]` as a placeholder for the campaign end date, formatted
with the language selected in the app. Existing campaigns receive the previous built-in
Portuguese and English copy during database migration, with all six text blocks visible.

Promotion telemetry has dedicated raw-event and summary datasets. It records Home modal
and paywall-card impressions, modal closes, manual and automatic code copies, changes to
“don't show again,” redeem CTA taps, native App Store sheet presentation/outcome, and
confirmed redemptions. Summary rates use promotion impressions as the denominator and can
be filtered by campaign, user, environment, and time window in the panel.

## iOS version updates

The App versions tab controls the iOS semantic-version target, App Store URL, localized Portuguese/English message and CTA text, and whether the prompt is soft or hard. The seeded policy is disabled at `1.2.0`.

- A soft update shows Update and Later. Selecting Later hides that target for the current app session.
- A hard update removes Later and cannot be dismissed; opening the App Store does not clear it when the user returns.
- The prompt is attached to the app root, so it covers Home, Search, Settings, loading, and paywall states.
- `modal_shown`, `update_tapped`, `later_tapped`, and `store_open_failed` are stored in app-update telemetry and are available from the panel and Postman collection.

The update policy API compares SemVer precedence. Build metadata does not affect precedence, and an equal or newer installed version never receives an update prompt.

Never paste the token into a URL. Serve the panel over HTTPS.

## App behavior

The iOS app checks both StoreKit transaction history and server telemetry. A user with any prior in-app purchase is ineligible. For an eligible user, the server atomically reserves an enabled code before returning an offer. Home suppression is stored server-side and does not hide the promotion from Plans when paywall visibility is enabled.

The app derives a localized estimate using the StoreKit product’s storefront price and the configured discount percentage. Apple’s native redemption/payment sheet is authoritative for the exact regional price, taxes, eligibility, and code validity.

The CTA copies the reserved code and opens StoreKit’s native offer-code redemption sheet. A verified offer-code transaction unlocks the product immediately and links the reserved code, app user, and transaction in SQLite. Failures are localized in the app and sent to the existing IAP telemetry endpoint; promotion-funnel interactions are sent to the dedicated promotion telemetry endpoint.

Apple does not provide an API to prefill a specific code in the redemption sheet or validate a code without attempting redemption. “Available” therefore means enabled and unallocated in Trade Alert; Apple performs final validation.

## Native review and trial extension

Apple prohibits requiring or rewarding a rating/review in exchange for app functionality. Trade Alert therefore grants one automatic seven-day engagement extension to an active server trial independently of any review outcome. The server guarantees idempotency. A native review request becomes locally eligible on a later launch after 24 hours, is requested at most once by the app, and may still be suppressed by StoreKit.

The app cannot determine whether the user submitted a review, and access never depends on that result.

## Production hardening

The current app identity is a device-generated UUID and the server trusts StoreKit-verified transaction data reported by the app, consistent with the existing IAP implementation. Before using a high-value or much larger code pool, add App Attest and App Store Server Notifications V2 / App Store Server API verification to prevent fabricated identities, reservation exhaustion, and spoofed redemption reports.
