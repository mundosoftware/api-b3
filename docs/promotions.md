# Promotions and native StoreKit redemption

Trade Alert imports Apple one-time offer codes into SQLite and manages them through a reusable admin panel. The source CSV remains a local deployment secret and is ignored by Git.

## Black Friday 2026 defaults

- Campaign: `black-friday-2026`
- Product: `lifetime_unlock`
- Brazil offer price: R$ 29.90
- Display discount: approximately 40%
- Starts: November 1, 2026
- Ends: December 31, 2026 at 23:59:59 in `America/Fortaleza`
- Home modal, optional “don’t show again,” and Plans placement are enabled.
- CSV: configured by `PROMOTION_CODES_CSV_PATH`

Database initialization imports every non-empty CSV row idempotently. Expected rows are `code,redemption_url` with no required header. Importing never resets an administrator’s enabled, reserved, or redeemed state.

## Admin panel

Open `/admin/promotions`. The page keeps the admin token in browser `localStorage` and sends it only in the `X-Admin-Token` header. The protected APIs support:

- campaign enable/disable;
- creation of additional disabled campaigns and browser-side CSV import;
- start/end dates, product, price, discount, localized title/body/CTA copy;
- home and paywall visibility;
- whether Home offers a “don’t show again” toggle;
- individual code enable/disable;
- available, reserved, and redeemed counts;
- the user and StoreKit transaction associated with a reported redemption.

Never paste the token into a URL. Serve the panel over HTTPS.

## App behavior

The iOS app checks both StoreKit transaction history and server telemetry. A user with any prior in-app purchase is ineligible. For an eligible user, the server atomically reserves an enabled code before returning an offer. Home suppression is stored server-side and does not hide the promotion from Plans when paywall visibility is enabled.

The app derives a localized estimate using the StoreKit product’s storefront price and the configured discount percentage. Apple’s native redemption/payment sheet is authoritative for the exact regional price, taxes, eligibility, and code validity.

The CTA copies the reserved code and opens StoreKit’s native offer-code redemption sheet. A verified offer-code transaction unlocks the product immediately and links the reserved code, app user, and transaction in SQLite. Failures are localized in the app and sent to the existing IAP telemetry endpoint.

Apple does not provide an API to prefill a specific code in the redemption sheet or validate a code without attempting redemption. “Available” therefore means enabled and unallocated in Trade Alert; Apple performs final validation.

## Native review and trial extension

Apple prohibits requiring or rewarding a rating/review in exchange for app functionality. Trade Alert therefore grants one automatic seven-day engagement extension to an active server trial independently of any review outcome. The server guarantees idempotency. A native review request becomes locally eligible on a later launch after 24 hours, is requested at most once by the app, and may still be suppressed by StoreKit.

The app cannot determine whether the user submitted a review, and access never depends on that result.

## Production hardening

The current app identity is a device-generated UUID and the server trusts StoreKit-verified transaction data reported by the app, consistent with the existing IAP implementation. Before using a high-value or much larger code pool, add App Attest and App Store Server Notifications V2 / App Store Server API verification to prevent fabricated identities, reservation exhaustion, and spoofed redemption reports.
