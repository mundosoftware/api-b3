# B3TickerWatch

This folder contains the SwiftUI watchOS client for the B3 Watch API.

## Setup

1. In Xcode, create a new watchOS App target named `B3TickerWatch`.
2. Add the Swift files from `watchos/B3TickerWatch` to the Watch App target.
3. Set `AppConfig.apiBaseURL` to the VPS URL, for example `http://203.0.113.10:8000`.
4. Enable Push Notifications for the Watch App target.
5. Set `AppConfig.deviceEnvironment` to `development` for debug/ad-hoc builds and `production` for App Store/TestFlight builds.

The watch app registers for APNs and sends the watch APNs token to the server. The server keeps the OneSignal REST API key private and registers the watch subscription with OneSignal.
