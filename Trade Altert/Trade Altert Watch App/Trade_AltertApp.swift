//
//  Trade_AltertApp.swift
//  Trade Altert Watch App
//
//  Created by Nonato Sousa on 02/08/26.
//

import SwiftUI
import WatchKit

@main
struct Trade_Altert_Watch_AppApp: App {
    @WKExtensionDelegateAdaptor(ExtensionDelegate.self) var extensionDelegate
    @StateObject private var model = AppModel.shared
    @StateObject private var language = AppLanguage.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
                .environmentObject(language)
                .environment(\.locale, language.locale)
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
