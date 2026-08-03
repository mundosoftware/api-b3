//
//  AppDelegate.swift
//  Trade Altert
//
//  Created by Codex on 02/08/26.
//

import UIKit

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        OneSignalService.shared.initialize(launchOptions: launchOptions)
        return true
    }
}
