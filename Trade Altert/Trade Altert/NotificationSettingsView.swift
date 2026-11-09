import StoreKit
import SwiftUI

struct NotificationSettingsView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @EnvironmentObject private var language: AppLanguage
    @EnvironmentObject private var purchases: PurchaseStore
    @State private var showPlansSheet = false
    #if DEBUG
    @AppStorage(AppConfig.apiEnvironmentStorageKey)
    private var apiEnvironmentRawValue = AppConfig.APIEnvironment.production.rawValue
    #endif

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

            Section(language.text("section.plans")) {
                if purchases.products.isEmpty {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                } else {
                    ForEach(purchases.products, id: \.id) { product in
                        HStack(alignment: .center) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(planTitle(for: product))
                                    .font(.headline)
                                Text(product.displayPrice)
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            }

                            Spacer()

                            Text(planStatusText(for: product))
                                .font(.caption.bold())
                                .foregroundStyle(planStatusColor(for: product))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(planStatusColor(for: product).opacity(0.12), in: Capsule())
                        }
                    }
                }

                Text(activePlanSummary())
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                Button {
                    showPlansSheet = true
                } label: {
                    Text(language.text("action.plans"))
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.borderless)
            }

            Section {
                Picker(language.text("section.language"), selection: $language.code) {
                    ForEach(AppLanguageCode.allCases) { code in
                        Text(code.displayName).tag(code)
                    }
                }
                .pickerStyle(.segmented)
            } header: {
                Text(language.text("section.language"))
            } footer: {
                Text(CompanionDeviceSnapshot.current.displayVersion)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            #if DEBUG
            Section(language.text("section.server")) {
                Toggle(
                    language.text("server.use_development"),
                    isOn: Binding(
                        get: {
                            apiEnvironmentRawValue == AppConfig.APIEnvironment.development.rawValue
                        },
                        set: { enabled in
                            apiEnvironmentRawValue = enabled
                                ? AppConfig.APIEnvironment.development.rawValue
                                : AppConfig.APIEnvironment.production.rawValue
                        }
                    )
                )
                .tint(.orange)

                LabeledContent(
                    language.text("label.mode"),
                    value: AppConfig.apiEnvironment == .development
                        ? language.text("label.development")
                        : language.text("label.production")
                )
                LabeledContent(language.text("label.api"), value: AppConfig.apiBaseURL.absoluteString)
                Text(language.text("server.development_notice"))
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if let promotion = purchases.availablePromotion,
                   promotion.allowHomeSuppression {
                    Toggle(
                        promotion.text.homeSuppressionLabel,
                        isOn: Binding(
                            get: { !promotion.showOnHome },
                            set: { hidden in
                                Task {
                                    await purchases.setPromotionHiddenOnHome(
                                        promotion,
                                        hidden: hidden
                                    )
                                }
                            }
                        )
                    )
                    Text(language.text("promotion.settings.home_visibility_help"))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            #endif
        }
        .navigationTitle(language.text("tab.settings"))
        .disabled(model.isLoading || purchases.isLoadingProducts)
        .sheet(isPresented: $showPlansSheet.queuedBehindAppUpdate(model.presentedAppUpdate)) {
            PurchasePlansSheetView()
                .presentationDetents([.large])
                .interactiveDismissDisabled(false)
        }
        .task {
            await purchases.load(userId: model.userId)
        }
        #if DEBUG
        .onChange(of: apiEnvironmentRawValue) { _, _ in
            Task {
                await model.reloadForAPIEnvironmentChange()
                await purchases.load(userId: model.userId)
            }
        }
        #endif
    }

    private func planTitle(for product: Product) -> String {
        switch product.id {
        case PurchaseStore.ProductID.proYear:
            return language.text("paywall.product.pro_year.title")
        case PurchaseStore.ProductID.proMonth:
            return language.text("paywall.product.pro_month.title")
        case PurchaseStore.ProductID.lifetimeUnlock:
            return language.text("paywall.product.lifetime.title")
        default:
            return product.displayName
        }
    }

    private func planStatusText(for product: Product) -> String {
        if purchases.purchasedProductIDs.contains(product.id) {
            return language.text("status.active")
        }

        if purchases.legacyPaidAccess && product.id == PurchaseStore.ProductID.lifetimeUnlock {
            return language.text("status.active")
        }

        return language.text("status.available")
    }

    private func planStatusColor(for product: Product) -> Color {
        if purchases.purchasedProductIDs.contains(product.id) || (purchases.legacyPaidAccess && product.id == PurchaseStore.ProductID.lifetimeUnlock) {
            return .green
        }

        return .blue
    }

    private func activePlanSummary() -> String {
        if purchases.legacyPaidAccess {
            return language.text("status.legacy")
        }

        if purchases.isTrialActive {
            let daysLeft = purchases.trialDaysLeft
            if daysLeft == 1 {
                return language.text("status.trial_day_left")
            }
            return String(format: language.text("status.trial_days_left"), daysLeft)
        }

        let activeProducts = purchases.products.filter { product in
            purchases.purchasedProductIDs.contains(product.id)
        }

        guard !activeProducts.isEmpty else {
            return language.text("status.none")
        }

        let names = activeProducts.map(planTitle)
        return String(format: language.text("status.active_summary"), names.joined(separator: ", "))
    }
}
