import SwiftUI

struct NotificationSettingsView: View {
    @EnvironmentObject private var model: CompanionAppModel

    var body: some View {
        Form {
            Section("Delivery") {
                Toggle(
                    isOn: Binding(
                        get: { model.iosNotificationsEnabled },
                        set: { model.setIOSNotificationsEnabled($0) }
                    )
                ) {
                    Label("iPhone", systemImage: "iphone")
                }

                Toggle(
                    isOn: Binding(
                        get: { model.watchNotificationsEnabled },
                        set: { model.setWatchNotificationsEnabled($0) }
                    )
                ) {
                    Label("Apple Watch", systemImage: "applewatch")
                }
            }

            Section("Devices") {
                LabeledContent("iPhone", value: model.iosRegistrationStatus)
                LabeledContent("Apple Watch", value: model.watchRegistrationStatus)
            }

            Section("Server") {
                LabeledContent("Mode", value: AppConfig.environment == .debug ? "Debug" : "Production")
                LabeledContent("API", value: AppConfig.apiBaseURL.absoluteString)
            }
        }
        .navigationTitle("Notifications")
        .disabled(model.isLoading)
    }
}
