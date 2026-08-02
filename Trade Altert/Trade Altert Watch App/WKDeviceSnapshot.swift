import Foundation
import WatchKit

struct WKDeviceSnapshot {
    let model: String
    let systemVersion: String
    let appVersion: String

    static var current: WKDeviceSnapshot {
        let device = WKInterfaceDevice.current()
        let bundle = Bundle.main
        return WKDeviceSnapshot(
            model: device.model,
            systemVersion: device.systemVersion,
            appVersion: bundle.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        )
    }
}
