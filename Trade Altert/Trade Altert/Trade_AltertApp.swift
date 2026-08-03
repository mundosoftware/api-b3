//
//  Trade_AltertApp.swift
//  Trade Altert
//
//  Created by Nonato Sousa on 02/08/26.
//

import SwiftUI

@main
struct Trade_AltertApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var model = CompanionAppModel.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(model)
        }
    }
}
