import SwiftUI

struct NotificationSettingsView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @EnvironmentObject private var language: AppLanguage

    var body: some View {
        Form {
            Section(language.text("section.delivery")) {
                Toggle(
                    isOn: Binding(
                        get: { model.iosNotificationsEnabled },
                        set: { model.setIOSNotificationsEnabled($0) }
                    )
                ) {
                    Label(language.text("label.iphone"), systemImage: "iphone")
                }

                Toggle(
                    isOn: Binding(
                        get: { model.watchNotificationsEnabled },
                        set: { model.setWatchNotificationsEnabled($0) }
                    )
                ) {
                    Label(language.text("label.apple_watch"), systemImage: "applewatch")
                }
            }

            Section(language.text("section.devices")) {
                LabeledContent(language.text("label.iphone"), value: model.iosRegistrationStatus)
                LabeledContent(language.text("label.apple_watch"), value: model.watchRegistrationStatus)
            }

            Section(language.text("section.language")) {
                Picker(language.text("section.language"), selection: $language.code) {
                    ForEach(AppLanguageCode.allCases) { code in
                        Text(code.displayName).tag(code)
                    }
                }
                .pickerStyle(.segmented)
            }

            #if DEBUG
            Section(language.text("section.server")) {
                LabeledContent(
                    language.text("label.mode"),
                    value: AppConfig.environment == .debug
                        ? language.text("label.debug")
                        : language.text("label.production")
                )
                LabeledContent(language.text("label.api"), value: AppConfig.apiBaseURL.absoluteString)
            }
            #endif
        }
        .navigationTitle(language.text("title.notifications"))
        .disabled(model.isLoading)
    }
}
