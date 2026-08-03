import SwiftUI

struct WatchSettingsView: View {
    @EnvironmentObject private var language: AppLanguage

    var body: some View {
        Form {
            Section(language.text("section.language")) {
                Picker(language.text("section.language"), selection: $language.code) {
                    ForEach(AppLanguageCode.allCases) { code in
                        Text(code.displayName).tag(code)
                    }
                }
            }
        }
        .navigationTitle(language.text("tab.settings"))
    }
}
