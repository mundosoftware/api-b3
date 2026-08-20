//
//  ContentView.swift
//  Trade Altert
//
//  Created by Nonato Sousa on 02/08/26.
//

import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @EnvironmentObject private var language: AppLanguage
    @EnvironmentObject private var purchases: PurchaseStore
    @State private var showOneSignalIntegrationAlert = false
    @State private var showTrialEndingAlert = false
    @State private var showTrialPlansSheet = false
    @State private var pushSubscriptionObserver: OneSignalPushSubscriptionObserver?
    @State private var didBootstrap = false
    @State private var didShowTrialEndingAlert = false

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
            await purchases.load(userId: model.userId)
            refreshTrialEndingAlert()
        }
        .task(id: purchases.hasAccess) {
            guard purchases.hasAccess, !didBootstrap else { return }
            await model.bootstrap()
            didBootstrap = true
            refreshOneSignalIntegrationAlert()
            refreshTrialEndingAlert()
        }
        .onChange(of: purchases.trialStatus?.remainingDays) { _, _ in
            refreshTrialEndingAlert()
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

    @MainActor
    private func shouldShowOneSignalIntegrationAlert() async -> Bool {
        guard model.iosNotificationsEnabled else { return false }
        guard !OneSignalService.shared.hasUsablePushSubscription else { return false }
        let isAuthorized = await OneSignalService.shared.hasNotificationAuthorization()
        return !isAuthorized
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
