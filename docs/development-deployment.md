# VPS development environment

The VPS development deployment is isolated from production while sharing the existing public HTTPS listener.

| Concern | Production | Development |
| --- | --- | --- |
| Public API | `https://<VPS_HOST>` | `https://<VPS_HOST>/dev` |
| systemd service | `b3-watch-api` | `b3-watch-api-dev` |
| Internal port | `8000` | `8001` |
| Application directory | `/opt/b3-watch-api` | `/opt/b3-watch-api-dev` |
| SQLite database | `database/app.db` | `database/app-dev.db` |
| Kronos/model cache | production app directory | development app directory |
| Alert polling | enabled by production configuration | disabled by default |
| OneSignal and WhatsApp | production configuration | disabled by default |

## Deploy

Keep the production settings in `local.env`; the script derives development values from them or uses the optional `DEV_*` overrides documented in `local.env.example`.

```bash
bash scripts/deploy_vps.sh vps-dev local.env
```

The deployment:

1. Verifies that the production service and public `/health` endpoint are healthy.
2. Synchronizes source into the development application directory.
3. Creates a separate Python environment, database, model source, and caches.
4. Starts the development systemd service on loopback port 8001.
5. adds nginx routing for `/dev/` while keeping `/` routed to production.
6. Verifies the internal development API, public `/dev/health`, feature routes, and production health again.

Useful URLs:

- API: `https://<VPS_HOST>/dev`
- Health: `https://<VPS_HOST>/dev/health`
- OpenAPI: `https://<VPS_HOST>/dev/docs`
- Promotions: `https://<VPS_HOST>/dev/admin/promotions`

## iOS Debug switch

Debug builds show a **Server** section under Settings. Enabling **Use development server** persists the choice on that debug installation and reloads the user, favorites, preferences, StoreKit-related backend state, and promotions from `/dev`.

Release builds always use the production endpoint. The `/dev` URL and selection branch are compiled only into Debug builds.

## Promotion-code safety

Development imports `Promotions/development-offer-codes.csv`, which contains intentionally invalid placeholder codes for testing availability, UI, clipboard, and error handling without consuming production Apple codes. To test a successful StoreKit redemption, configure dedicated non-production test codes and point `DEV_PROMOTION_CODES_CSV_PATH` at their CSV. Never reuse the production code export in the development database.

## Push testing

Development notification delivery is disabled by default. If push delivery must be tested, use separate OneSignal applications and credentials and explicitly set `DEV_ONESIGNAL_ENABLED=true`. Do not point development at production OneSignal applications or Universal Notifier.
