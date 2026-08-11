# Trade Altert

This folder contains the native iOS companion app, the standalone-capable watchOS app, and the OneSignal notification service extension.

## Setup

1. Set `AppConfig.apiBaseURL` in both app targets to the VPS URL, for example `https://203.0.113.10`.
2. Set the watch app `AppConfig.deviceEnvironment` to `development` for debug/ad-hoc builds and `production` for App Store/TestFlight builds.
3. Keep Push Notifications enabled for the iOS and watchOS targets.

The watch app can run independently of the iOS app. It requests watchOS notification permission, registers directly with APNs, and sends the watch APNs token to the server. The server keeps the OneSignal REST API key private and registers the watch subscription with OneSignal.
When the iOS companion is paired and reachable, the watch shares its server user id through WatchConnectivity so the iOS notification toggles control the same alert account. Without the iPhone, the watch keeps using its own local user id and direct server/API path.

## OneSignal SDK

The iOS companion target initializes the OneSignal iOS SDK in `OneSignalService` with App ID `ea51ef99-29e6-4d18-8e10-7e36dabfb66e`.
The app target has Push Notifications, remote-notification background mode, and the shared app group entitlement configured for OneSignal.
The `OneSignalNotificationServiceExtension` target is embedded into the iOS app and uses `OneSignalExtension` to process rich notifications.
The iOS companion app registers its OneSignal subscription with the server and exposes iPhone and Apple Watch notification toggles.
Standalone watch notifications use the watch APNs token, whose topic is the watch app bundle ID `com.mundosoftware.tradealert.watchkitapp`. Configure a separate OneSignal app for that bundle and set `ONESIGNAL_WATCH_APP_ID` plus `ONESIGNAL_WATCH_REST_API_KEY` on the server. Reusing the iOS OneSignal app for the watch token causes APNs `DeviceTokenNotForTopic` failures.
