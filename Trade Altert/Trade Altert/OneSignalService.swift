//
//  OneSignalService.swift
//  Trade Altert
//
//  Created by Codex on 02/08/26.
//

import Foundation
import OneSignalFramework
import UIKit
import UserNotifications

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
        setLanguage(AppLanguage.shared.code.rawValue)
        isInitialized = true
    }

    var currentPushSubscriptionId: String? {
        OneSignal.User.pushSubscription.id
    }

    var hasUsablePushSubscription: Bool {
        guard let id = currentPushSubscriptionId else { return false }
        return !id.isEmpty && !id.hasPrefix("local-")
    }

    func notificationAuthorizationStatus() async -> UNAuthorizationStatus {
        await withCheckedContinuation { continuation in
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                continuation.resume(returning: settings.authorizationStatus)
            }
        }
    }

    func hasNotificationAuthorization() async -> Bool {
        switch await notificationAuthorizationStatus() {
        case .authorized, .provisional, .ephemeral:
            return true
        case .denied, .notDetermined:
            return false
        @unknown default:
            return false
        }
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
        setLanguage(AppLanguage.shared.code.rawValue)
    }

    func logout() {
        OneSignal.logout()
    }

    func setLanguage(_ languageCode: String) {
        OneSignal.User.setLanguage(languageCode)
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
