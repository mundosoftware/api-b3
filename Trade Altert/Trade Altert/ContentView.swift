//
//  ContentView.swift
//  Trade Altert
//
//  Created by Nonato Sousa on 02/08/26.
//

import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @State private var showOneSignalIntegrationAlert = false
    @State private var pushSubscriptionObserver: OneSignalPushSubscriptionObserver?

    var body: some View {
        TabView {
            NavigationStack {
                TrackedCompaniesView()
            }
            .tabItem {
                Label("Tracked", systemImage: "star")
            }

            NavigationStack {
                SearchView()
            }
            .tabItem {
                Label("Search", systemImage: "magnifyingglass")
            }

            NavigationStack {
                NotificationSettingsView()
            }
            .tabItem {
                Label("Notifications", systemImage: "bell")
            }
        }
        .onAppear(perform: configureOneSignalVerification)
        .task {
            await model.bootstrap()
            refreshOneSignalIntegrationAlert()
        }
        .onChange(of: model.iosNotificationsEnabled) { _ in
            refreshOneSignalIntegrationAlert()
        }
        .alert("Quase pronto", isPresented: $showOneSignalIntegrationAlert) {
            Button("Allow Notifications") {
                Task {
                    await model.updateIOSNotificationsEnabled(true)
                    refreshOneSignalIntegrationAlert()
                }
            }
            Button("Not Now", role: .cancel) {
                showOneSignalIntegrationAlert = false
            }
        } message: {
            Text("Precisamos de sua permissão para enviar notificações.")
        }
        .alert("Error", isPresented: Binding(
            get: { model.errorMessage != nil },
            set: { if !$0 { model.errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(model.errorMessage ?? "")
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
    }
}
