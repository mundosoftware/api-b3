//
//  OneSignalService.swift
//  Trade Altert
//
//  Created by Codex on 02/08/26.
//

import Foundation
import OneSignalFramework
import UIKit

final class OneSignalService {
    static let shared = OneSignalService()

    private let appId = "ea51ef99-29e6-4d18-8e10-7e36dabfb66e"
    private var isInitialized = false

    private init() {}

    func initialize(launchOptions: [UIApplication.LaunchOptionsKey: Any]?) {
        guard !isInitialized else { return }

        #if DEBUG
        OneSignal.Debug.setLogLevel(.LL_VERBOSE)
        #endif

        OneSignal.initialize(appId, withLaunchOptions: launchOptions)
        isInitialized = true
    }

    var currentPushSubscriptionId: String? {
        OneSignal.User.pushSubscription.id
    }

    func requestPushPermission() async -> Bool {
        await withCheckedContinuation { continuation in
            OneSignal.Notifications.requestPermission({ accepted in
                print("OneSignal push notification permission accepted: \(accepted)")
                continuation.resume(returning: accepted)
            }, fallbackToSettings: true)
        }
    }

    func login(userId: String) {
        OneSignal.login(userId)
    }

    func logout() {
        OneSignal.logout()
    }

    func addEmail(_ email: String) {
        OneSignal.User.addEmail(email)
    }

    func removeEmail(_ email: String) {
        OneSignal.User.removeEmail(email)
    }

    func addSmsNumber(_ smsNumber: String) {
        OneSignal.User.addSms(smsNumber)
    }

    func removeSmsNumber(_ smsNumber: String) {
        OneSignal.User.removeSms(smsNumber)
    }

    func addTag(key: String, value: String) {
        OneSignal.User.addTag(key: key, value: value)
    }

    func removeTag(_ key: String) {
        OneSignal.User.removeTag(key)
    }

    func makePushSubscriptionObserver(onSubscribed: @escaping () -> Void) -> OneSignalPushSubscriptionObserver {
        OneSignalPushSubscriptionObserver(onSubscribed: onSubscribed)
    }

    func addPushSubscriptionObserver(_ observer: OSPushSubscriptionObserver) {
        OneSignal.User.pushSubscription.addObserver(observer)
    }
}
