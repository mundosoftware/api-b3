//
//  ContentView.swift
//  Trade Altert
//
//  Created by Nonato Sousa on 02/08/26.
//

import StoreKit
import SwiftUI
import UIKit

struct ContentView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @EnvironmentObject private var language: AppLanguage
    @EnvironmentObject private var purchases: PurchaseStore
    @Environment(\.requestReview) private var requestReview
    @Environment(\.openURL) private var openURL
    @Environment(\.scenePhase) private var scenePhase
    @State private var showOneSignalIntegrationAlert = false
    @State private var showTrialEndingAlert = false
    @State private var showTrialPlansSheet = false
    @State private var pushSubscriptionObserver: OneSignalPushSubscriptionObserver?
    @State private var didBootstrap = false
    @State private var didShowTrialEndingAlert = false
    @State private var showHomePromotion = false
    @State private var showTrialExtensionConfirmation = false
    @State private var nativeReviewTask: Task<Void, Never>?

    var body: some View {
        ZStack {
            alertContent
                .allowsHitTesting(model.presentedAppUpdate == nil)
                .accessibilityHidden(model.presentedAppUpdate != nil)

            if let update = model.presentedAppUpdate {
                AppUpdateModalOverlay(
                    update: update,
                    onUpdate: { openAppStore(for: update) },
                    onLater: {
                        model.dismissAppUpdate(update)
                        Task {
                            await model.recordAppUpdateInteraction(
                                "later_tapped",
                                update: update
                            )
                        }
                    }
                )
                .transition(.opacity.combined(with: .scale(scale: 0.96)))
                .zIndex(100)
            }
        }
        .animation(.spring(response: 0.32, dampingFraction: 0.88), value: model.presentedAppUpdate?.id)
    }

    private var accessContent: some View {
        Group {
            if purchases.hasAccess {
                appTabs
            } else if purchases.hasResolvedAccess {
                PaywallView()
            } else {
                StoreAccessLoadingView()
            }
        }
    }

    private var lifecycleContent: some View {
        accessContent
        .task {
            CompanionWatchSyncService.shared.start(model: model)
            await purchases.load(userId: model.userId)
            await model.checkForAppUpdate()
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
        .onChange(of: purchases.availablePromotion?.showOnHome) { _, showOnHome in
            showHomePromotion = showOnHome == true
        }
        .onChange(of: purchases.trialExtensionDaysGranted) { _, days in
            guard days > 0 else { return }
            showTrialExtensionConfirmation = true
        }
        .onChange(of: purchases.shouldRequestNativeReview) { _, shouldRequest in
            guard shouldRequest else { return }
            scheduleNativeReviewRequest()
        }
        .onChange(of: model.presentedAppUpdate?.id) { _, updateID in
            guard updateID == nil, purchases.shouldRequestNativeReview else { return }
            scheduleNativeReviewRequest()
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
        .onChange(of: scenePhase) { _, phase in
            guard phase == .active else { return }
            Task {
                await model.checkForAppUpdate()
            }
        }
    }

    private var sheetContent: some View {
        lifecycleContent
        .sheet(isPresented: $showTrialPlansSheet.queuedBehindAppUpdate(model.presentedAppUpdate)) {
            PurchasePlansSheetView()
                .presentationDetents([.large])
                .interactiveDismissDisabled(false)
        }
        .sheet(isPresented: $showHomePromotion.queuedBehindAppUpdate(model.presentedAppUpdate)) {
            if let promotion = purchases.availablePromotion {
                PromotionOfferView(promotion: promotion, context: .home)
                    .presentationDetents([.medium, .large])
            }
        }
    }

    private var alertContent: some View {
        sheetContent
        .offerCodeRedemption(
            isPresented: $purchases.isPresentingOfferCodeRedemption
                .queuedBehindAppUpdate(model.presentedAppUpdate)
        ) { result in
            Task {
                await purchases.handleOfferCodeRedemptionPresentation(result)
            }
        }
        .alert(
            language.text("review.extension.title"),
            isPresented: $showTrialExtensionConfirmation
                .queuedBehindAppUpdate(model.presentedAppUpdate)
        ) {
            Button(language.text("action.ok"), role: .cancel) {}
        } message: {
            Text(
                String(
                    format: language.text("review.extension.message"),
                    purchases.trialExtensionDaysGranted
                )
            )
        }
        .alert(
            language.text("paywall.trial.one_day.title"),
            isPresented: $showTrialEndingAlert
                .queuedBehindAppUpdate(model.presentedAppUpdate)
        ) {
            Button(language.text("action.cancel"), role: .cancel) {}
            Button(language.text("paywall.trial.one_day.cta")) {
                showTrialPlansSheet = true
            }
        } message: {
            Text(language.text("paywall.trial.one_day.message"))
        }
        .alert(language.text("title.error"), isPresented: errorAlertBinding) {
            Button(language.text("action.ok"), role: .cancel) {}
        } message: {
            Text(model.errorMessage ?? "")
        }
    }

    private var errorAlertBinding: Binding<Bool> {
        Binding(
            get: {
                model.presentedAppUpdate == nil && model.errorMessage != nil
            },
            set: { visible in
                if model.presentedAppUpdate != nil && !visible {
                    return
                }
                if !visible {
                    model.errorMessage = nil
                }
            }
        )
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
        .alert(
            language.text("title.almost_ready"),
            isPresented: $showOneSignalIntegrationAlert
                .queuedBehindAppUpdate(model.presentedAppUpdate)
        ) {
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

    private func scheduleNativeReviewRequest() {
        nativeReviewTask?.cancel()
        nativeReviewTask = Task { @MainActor in
            try? await Task.sleep(for: .seconds(3))
            guard !Task.isCancelled,
                  model.presentedAppUpdate == nil,
                  purchases.shouldRequestNativeReview else {
                return
            }
            requestReview()
            purchases.consumeNativeReviewRequest()
        }
    }

    private func openAppStore(for update: AppUpdateDecision) {
        Task {
            await model.recordAppUpdateInteraction("update_tapped", update: update)
        }
        guard let url = URL(string: update.storeURL) else {
            Task {
                await model.recordAppUpdateInteraction("store_open_failed", update: update)
            }
            return
        }

        openURL(url) { accepted in
            Task { @MainActor in
                if accepted {
                    model.dismissAppUpdate(update)
                } else {
                    await model.recordAppUpdateInteraction(
                        "store_open_failed",
                        update: update
                    )
                }
            }
        }
    }

    @MainActor
    private func shouldShowOneSignalIntegrationAlert() async -> Bool {
        guard model.iosNotificationsEnabled else { return false }
        guard !OneSignalService.shared.hasUsablePushSubscription else { return false }
        let isAuthorized = await OneSignalService.shared.hasNotificationAuthorization()
        return !isAuthorized
    }
}

private struct AppUpdateModalOverlay: View {
    let update: AppUpdateDecision
    let onUpdate: () -> Void
    let onLater: () -> Void

    var body: some View {
        ZStack {
            Color.black.opacity(0.48)
                .ignoresSafeArea()

            AppUpdatePromptView(
                update: update,
                onUpdate: onUpdate,
                onLater: onLater
            )
            .padding(.horizontal, 24)
            .padding(.vertical, 32)
        }
        .contentShape(Rectangle())
        .accessibilityAddTraits(.isModal)
    }
}

struct AppUpdatePromptView: View {
    let update: AppUpdateDecision
    let onUpdate: () -> Void
    let onLater: () -> Void

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: update.isHardUpdate ? "arrow.down.circle.fill" : "sparkles")
                .font(.system(size: 48, weight: .semibold))
                .foregroundStyle(.blue)
                .symbolRenderingMode(.hierarchical)

            VStack(spacing: 10) {
                Text(update.text.title)
                    .font(.title2.bold())
                    .multilineTextAlignment(.center)
                Text(update.text.message)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Button(action: onUpdate) {
                Text(update.text.updateCTA)
                    .font(.headline)
                    .foregroundStyle(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                    .frame(maxWidth: .infinity)
                    .frame(height: 24)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)

            if !update.isHardUpdate {
                Button(action: onLater) {
                    Text(update.text.laterCTA)
                        .font(.headline)
                        .foregroundStyle(.white)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                        .frame(maxWidth: .infinity)
                        .frame(height: 24)
                }
                .buttonStyle(.borderedProminent)
                .tint(Color.red.opacity(0.82))
                .controlSize(.large)
            }
        }
        .padding(28)
        .frame(maxWidth: 440)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 28, style: .continuous)
                .stroke(Color.white.opacity(0.16), lineWidth: 1)
        }
        .shadow(color: .black.opacity(0.24), radius: 28, y: 12)
    }
}

extension Binding where Value == Bool {
    /// Keeps a pending presentation queued while the app-update modal has priority.
    func queuedBehindAppUpdate(_ update: AppUpdateDecision?) -> Binding<Bool> {
        Binding(
            get: { update == nil && wrappedValue },
            set: { isPresented in
                // SwiftUI may write `false` while dismissing a lower-priority system
                // presentation. Preserve its intent so it can resume after the update.
                if update != nil && !isPresented {
                    return
                }
                wrappedValue = isPresented
            }
        )
    }
}

enum PromotionPresentationContext: String {
    case home
    case paywall
}

extension PromotionOffer {
    func localizedEndDate(locale: Locale) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: endsAt) ?? ISO8601DateFormatter().date(from: endsAt)
        guard let date else { return endsAt }

        let localizedFormatter = DateFormatter()
        localizedFormatter.locale = locale
        localizedFormatter.timeZone = .current
        localizedFormatter.dateStyle = .long
        localizedFormatter.timeStyle = .short
        return localizedFormatter.string(from: date)
    }

    func localizedValidUntilText(locale: Locale) -> String {
        text.validUntil.replacingOccurrences(
            of: "[date]",
            with: localizedEndDate(locale: locale)
        )
    }
}

struct PromotionOfferView: View {
    @EnvironmentObject private var purchases: PurchaseStore
    @EnvironmentObject private var language: AppLanguage
    @EnvironmentObject private var model: CompanionAppModel
    @Environment(\.dismiss) private var dismiss

    let promotion: PromotionOffer
    let context: PromotionPresentationContext
    @State private var hideOnHome = false
    @State private var didStartRedemption = false

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
                if promotion.text.showBody {
                    Text(promotion.text.body)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if promotion.text.showValidUntil {
                    Text(promotion.localizedValidUntilText(locale: language.locale))
                        .font(.subheadline.bold())
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(purchases.localizedPromotionPrice(promotion))
                        .font(.system(size: 38, weight: .bold, design: .rounded))
                    Text(String(format: language.text("promotion.discount"), promotion.discountPercent))
                        .font(.headline)
                        .foregroundStyle(.green)
                    if promotion.text.showPriceAuthority {
                        Text(promotion.text.priceAuthority)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                PromotionCodeCopyNotice(promotion: promotion, context: context)

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
                }
                if context == .home && promotion.text.showPlansNotice {
                    Text(promotion.text.plansNotice)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Button {
                    didStartRedemption = true
                    dismiss()
                    Task {
                        try? await Task.sleep(for: .milliseconds(350))
                        await purchases.beginPromotionRedemption(
                            promotion,
                            context: context.rawValue
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

                if promotion.text.showNativeSheetNotice {
                    Text(promotion.text.nativeSheetNotice)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(24)
            .frame(maxWidth: 620)
            .frame(maxWidth: .infinity)
        }
        .background(Color(.systemGroupedBackground))
        .onAppear {
            Task {
                await purchases.recordPromotionInteraction(
                    "modal_shown",
                    promotion: promotion,
                    context: context.rawValue
                )
            }
        }
        .onDisappear {
            guard !didStartRedemption, model.presentedAppUpdate == nil else { return }
            Task {
                await purchases.recordPromotionInteraction(
                    "modal_closed",
                    promotion: promotion,
                    context: context.rawValue
                )
            }
        }
    }
}

struct PromotionCodeCopyNotice: View {
    @EnvironmentObject private var language: AppLanguage
    @EnvironmentObject private var purchases: PurchaseStore
    let promotion: PromotionOffer
    let context: PromotionPresentationContext
    @State private var didCopy = false
    @State private var resetFeedbackTask: Task<Void, Never>?

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            if promotion.text.showCopyInstruction {
                Text(promotion.text.copyInstruction)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(language.text("promotion.code.label"))
                        .font(.caption.bold())
                        .foregroundStyle(.secondary)
                    Text(promotion.code)
                        .font(.system(.title3, design: .monospaced).weight(.semibold))
                        .textSelection(.enabled)
                }

                Spacer(minLength: 8)

                Button(action: copyCode) {
                    Label(
                        language.text(didCopy ? "promotion.code.copied" : "promotion.code.copy"),
                        systemImage: didCopy ? "checkmark.circle.fill" : "doc.on.doc.fill"
                    )
                    .font(.subheadline.bold())
                }
                .buttonStyle(.bordered)
                .tint(didCopy ? .green : .orange)
                .contentTransition(.symbolEffect(.replace))
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 12))
        }
        .onDisappear {
            resetFeedbackTask?.cancel()
        }
    }

    private func copyCode() {
        let feedback = UINotificationFeedbackGenerator()
        feedback.prepare()
        UIPasteboard.general.string = promotion.code
        feedback.notificationOccurred(.success)
        Task {
            await purchases.recordPromotionInteraction(
                "copy_code_tapped",
                promotion: promotion,
                context: context.rawValue
            )
        }

        resetFeedbackTask?.cancel()
        withAnimation(.snappy) {
            didCopy = true
        }
        resetFeedbackTask = Task { @MainActor in
            try? await Task.sleep(for: .seconds(2))
            guard !Task.isCancelled else { return }
            withAnimation(.easeOut(duration: 0.2)) {
                didCopy = false
            }
        }
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
