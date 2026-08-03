import UIKit

struct CompanionDeviceSnapshot {
    let model: String
    let systemVersion: String
    let appVersion: String

    static var current: CompanionDeviceSnapshot {
        let bundle = Bundle.main
        let version = bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        let build = bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String
        let appVersion = [version, build].compactMap { $0 }.joined(separator: " ")

        return CompanionDeviceSnapshot(
            model: UIDevice.current.model,
            systemVersion: UIDevice.current.systemVersion,
            appVersion: appVersion.isEmpty ? "unknown" : appVersion
        )
    }
}
