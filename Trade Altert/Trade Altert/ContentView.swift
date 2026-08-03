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
        }
        .alert("OneSignal Integration Complete", isPresented: $showOneSignalIntegrationAlert) {
            Button("Allow Notifications") {
                model.setIOSNotificationsEnabled(true)
            }
        } message: {
            Text("The OneSignal SDK is installed and connected. Enable notifications to finish push setup.")
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
            showOneSignalIntegrationAlert = true
            model.handleServerSubscriptionAvailable()
        }

        pushSubscriptionObserver = observer
        OneSignalService.shared.addPushSubscriptionObserver(observer)
        observer.evaluate(subscriptionId: OneSignalService.shared.currentPushSubscriptionId)
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
            .environmentObject(CompanionAppModel.shared)
    }
}
