import SwiftUI
import UserNotifications
import WatchKit

@main
struct B3TickerWatchApp: App {
    @WKExtensionDelegateAdaptor(ExtensionDelegate.self) var extensionDelegate
    @StateObject private var model = AppModel.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
                .task {
                    await model.bootstrap()
                }
        }
    }
}

final class ExtensionDelegate: NSObject, WKExtensionDelegate {
    func didRegisterForRemoteNotifications(withDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task {
            await AppModel.shared.registerDevice(apnsToken: token)
        }
    }

    func didFailToRegisterForRemoteNotificationsWithError(_ error: Error) {
        Task { @MainActor in
            AppModel.shared.errorMessage = error.localizedDescription
        }
    }
}
