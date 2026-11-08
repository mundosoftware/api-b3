//
//  ContentView.swift
//  Trade Altert
//
//  Created by Nonato Sousa on 02/08/26.
//

import StoreKit
import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @EnvironmentObject private var language: AppLanguage
    @EnvironmentObject private var purchases: PurchaseStore
    @Environment(\.requestReview) private var requestReview
    @State private var showOneSignalIntegrationAlert = false
    @State private var showTrialEndingAlert = false
    @State private var showTrialPlansSheet = false
    @State private var pushSubscriptionObserver: OneSignalPushSubscriptionObserver?
    @State private var didBootstrap = false
    @State private var didShowTrialEndingAlert = false
    @State private var showHomePromotion = false
    @State private var showTrialExtensionConfirmation = false

    var body: some View {
        Group {
            if purchases.hasAccess {
                appTabs
            } else if purchases.hasResolvedAccess {
                PaywallView()
            } else {
                StoreAccessLoadingView()
            }
        }
        .task {
            CompanionWatchSyncService.shared.start(model: model)
            await purchases.load(userId: model.userId)
            showHomePromotion = purchases.availablePromotion?.showOnHome == true
            syncWatchAccessState()
            refreshTrialEndingAlert()
        }
        .task(id: purchases.hasAccess) {
            syncWatchAccessState()
            guard purchases.hasAccess, !didBootstrap else { return }
            await model.bootstrap()
            didBootstrap = true
            syncWatchAccessState()
            refreshOneSignalIntegrationAlert()
            refreshTrialEndingAlert()
        }
        .onChange(of: purchases.trialStatus?.remainingDays) { _, _ in
            syncWatchAccessState()
            refreshTrialEndingAlert()
        }
        .onChange(of: purchases.purchasedProductIDs) { _, _ in
            syncWatchAccessState()
        }
        .onChange(of: purchases.paidAccessExpiresAt) { _, _ in
            syncWatchAccessState()
        }
        .onChange(of: purchases.availablePromotion?.id) { _, _ in
            showHomePromotion = purchases.availablePromotion?.showOnHome == true
        }
        .onChange(of: purchases.trialExtensionDaysGranted) { _, days in
            guard days > 0 else { return }
            showTrialExtensionConfirmation = true
        }
        .onChange(of: purchases.shouldRequestNativeReview) { _, shouldRequest in
            guard shouldRequest else { return }
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(3))
                requestReview()
                purchases.consumeNativeReviewRequest()
            }
        }
        .onChange(of: model.shouldShowPurchasePlansFromWatch) { _, shouldShow in
            guard shouldShow else { return }
            showTrialPlansSheet = true
            model.shouldShowPurchasePlansFromWatch = false
        }
        .onChange(of: model.iosNotificationsEnabled) { _, _ in
            guard purchases.hasAccess else { return }
            refreshOneSignalIntegrationAlert()
        }
        .sheet(isPresented: $showTrialPlansSheet) {
            PurchasePlansSheetView()
                .presentationDetents([.large])
                .interactiveDismissDisabled(false)
        }
        .sheet(isPresented: $showHomePromotion) {
            if let promotion = purchases.availablePromotion {
                PromotionOfferView(promotion: promotion, context: .home)
                    .presentationDetents([.medium, .large])
            }
        }
        .offerCodeRedemption(isPresented: $purchases.isPresentingOfferCodeRedemption) { result in
            Task {
                await purchases.handleOfferCodeRedemptionPresentation(result)
            }
        }
        .alert(language.text("review.extension.title"), isPresented: $showTrialExtensionConfirmation) {
            Button(language.text("action.ok"), role: .cancel) {}
        } message: {
            Text(
                String(
                    format: language.text("review.extension.message"),
                    purchases.trialExtensionDaysGranted
                )
            )
        }
        .alert(language.text("paywall.trial.one_day.title"), isPresented: $showTrialEndingAlert) {
            Button(language.text("action.cancel"), role: .cancel) {}
            Button(language.text("paywall.trial.one_day.cta")) {
                showTrialPlansSheet = true
            }
        } message: {
            Text(language.text("paywall.trial.one_day.message"))
        }
        .alert(language.text("title.error"), isPresented: Binding(
            get: { model.errorMessage != nil },
            set: { if !$0 { model.errorMessage = nil } }
        )) {
            Button(language.text("action.ok"), role: .cancel) {}
        } message: {
            Text(model.errorMessage ?? "")
        }
    }

    private var appTabs: some View {
        TabView {
            NavigationStack {
                TrackedCompaniesView()
            }
            .tabItem {
                Label(language.text("tab.tracked"), systemImage: "star")
            }

            NavigationStack {
                SearchView()
            }
            .tabItem {
                Label(language.text("tab.search"), systemImage: "magnifyingglass")
            }

            NavigationStack {
                NotificationSettingsView()
            }
            .tabItem {
                Label(language.text("tab.settings"), systemImage: "gearshape")
            }
        }
        .onAppear(perform: configureOneSignalVerification)
        .alert(language.text("title.almost_ready"), isPresented: $showOneSignalIntegrationAlert) {
            Button(language.text("action.allow_notifications")) {
                Task {
                    await model.updateIOSNotificationsEnabled(true)
                    refreshOneSignalIntegrationAlert()
                }
            }
            Button(language.text("action.not_now"), role: .cancel) {
                showOneSignalIntegrationAlert = false
            }
        } message: {
            Text(language.text("message.notification_permission"))
        }
    }

    private func configureOneSignalVerification() {
        guard pushSubscriptionObserver == nil else { return }

        let observer = OneSignalService.shared.makePushSubscriptionObserver {
            showOneSignalIntegrationAlert = false
            model.handleServerSubscriptionAvailable()
        }

        pushSubscriptionObserver = observer
        OneSignalService.shared.addPushSubscriptionObserver(observer)
        observer.evaluate(subscriptionId: OneSignalService.shared.currentPushSubscriptionId)
    }

    private func refreshOneSignalIntegrationAlert() {
        Task { @MainActor in
            showOneSignalIntegrationAlert = await shouldShowOneSignalIntegrationAlert()
        }
    }

    private func refreshTrialEndingAlert() {
        guard purchases.hasAccess, purchases.isTrialActive else { return }
        guard purchases.trialDaysLeft == 1 else {
            didShowTrialEndingAlert = false
            return
        }
        guard !didShowTrialEndingAlert else { return }

        didShowTrialEndingAlert = true
        showTrialEndingAlert = true
    }

    private func syncWatchAccessState() {
        CompanionWatchSyncService.shared.sendAccessState(
            userId: model.userId,
            hasAccess: purchases.hasAccess,
            paidAccess: purchases.hasPaidAccess,
            paidAccessExpiresAt: purchases.paidAccessExpiresAt,
            trialDaysLeft: purchases.isTrialActive ? purchases.trialDaysLeft : nil
        )
    }

    @MainActor
    private func shouldShowOneSignalIntegrationAlert() async -> Bool {
        guard model.iosNotificationsEnabled else { return false }
        guard !OneSignalService.shared.hasUsablePushSubscription else { return false }
        let isAuthorized = await OneSignalService.shared.hasNotificationAuthorization()
        return !isAuthorized
    }
}

enum PromotionPresentationContext {
    case home
    case paywall
}

extension PromotionOffer {
    var localizedEndDate: String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: endsAt) ?? ISO8601DateFormatter().date(from: endsAt)
        return date?.formatted(date: .long, time: .shortened) ?? endsAt
    }
}

struct PromotionOfferView: View {
    @EnvironmentObject private var purchases: PurchaseStore
    @EnvironmentObject private var language: AppLanguage
    @Environment(\.dismiss) private var dismiss

    let promotion: PromotionOffer
    let context: PromotionPresentationContext
    @State private var hideOnHome = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Image(systemName: "tag.fill")
                        .font(.system(size: 34, weight: .bold))
                        .foregroundStyle(.orange)
                    Spacer()
                    if context == .home {
                        Button { dismiss() } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.title2)
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }

                Text(promotion.text.title)
                    .font(.largeTitle.bold())
                Text(promotion.text.body)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(String(format: language.text("promotion.valid_until"), promotion.localizedEndDate))
                    .font(.subheadline.bold())

                VStack(alignment: .leading, spacing: 4) {
                    Text(purchases.localizedPromotionPrice(promotion))
                        .font(.system(size: 38, weight: .bold, design: .rounded))
                    Text(String(format: language.text("promotion.discount"), promotion.discountPercent))
                        .font(.headline)
                        .foregroundStyle(.green)
                    Text(language.text("promotion.price_authority"))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                VStack(alignment: .leading, spacing: 7) {
                    Text(language.text("promotion.code.copied_instruction"))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Text(promotion.code)
                        .font(.system(.title3, design: .monospaced).weight(.semibold))
                        .textSelection(.enabled)
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
                }

                if context == .home && promotion.allowHomeSuppression {
                    Toggle(promotion.text.homeSuppressionLabel, isOn: $hideOnHome)
                        .onChange(of: hideOnHome) { _, hidden in
                            Task {
                                await purchases.setPromotionHiddenOnHome(
                                    promotion,
                                    hidden: hidden
                                )
                            }
                        }
                    Text(promotion.text.plansNotice)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Button {
                    dismiss()
                    Task {
                        try? await Task.sleep(for: .milliseconds(350))
                        await purchases.beginPromotionRedemption(
                            promotion,
                            hideOnHome: context == .home && hideOnHome
                        )
                    }
                } label: {
                    Label(promotion.text.ctaLabel, systemImage: "apple.logo")
                        .font(.headline)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .tint(.orange)

                Text(language.text("promotion.native_sheet_notice"))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(24)
            .frame(maxWidth: 620)
            .frame(maxWidth: .infinity)
        }
        .background(Color(.systemGroupedBackground))
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
            .environmentObject(CompanionAppModel.shared)
            .environmentObject(AppLanguage.shared)
            .environmentObject(PurchaseStore.shared)
    }
}
