import Combine
import Foundation
import UserNotifications
import WatchKit

@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()
    private static let apnsTokenStorageKey = "b3watch.apnsToken"

    @Published var favorites: [Favorite] = []
    @Published var searchResults: [Company] = []
    @Published var alertsByTicker: [String: [AlertRule]] = [:]
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published private(set) var hasAccess = false
    @Published private(set) var accessCheckCompleted = false

    @Published private(set) var userId: String
    private let api = APIClient.shared
    private static let companionPaidAccessStorageKey = "b3watch.companionPaidAccess"
    private static let companionPaidAccessExpiresAtStorageKey = "b3watch.companionPaidAccessExpiresAt"
    private static let companionTrialDaysLeftStorageKey = "b3watch.companionTrialDaysLeft"
    private static let dateFormatter = ISO8601DateFormatter()

    private init() {
        let identity = UserIdentityStore.loadOrCreate()
        userId = identity.userId
        hasAccess = Self.storedPaidAccessIsCurrent()
    }

    func bootstrap() async {
        WatchCompanionSyncService.shared.start(model: self)
        WatchCompanionSyncService.shared.sendUserId(userId)
        await run {
            try await self.api.upsertUser(userId: self.userId, timezone: TimeZone.current.identifier)
            await self.refreshAccessStatusFromServer()
            guard self.hasAccess else {
                self.clearProtectedData()
                return
            }
            await self.requestNotificationPermissionIfNeeded()
            do {
                try await self.registerStoredDeviceIfAvailable()
            } catch {
                self.errorMessage = error.localizedDescription
            }
            self.favorites = try await self.api.favorites(userId: self.userId)
        }
    }

    func refreshFavorites() async {
        await run(requiresAccess: true) {
            self.favorites = try await self.api.favorites(userId: self.userId)
        }
    }

    func refreshTrackedCompanies() async {
        await run(requiresAccess: true) {
            var refreshed = try await self.api.favorites(userId: self.userId)
            for index in refreshed.indices {
                do {
                    let company = try await self.api.quote(ticker: refreshed[index].ticker)
                    refreshed[index] = Favorite(
                        ticker: refreshed[index].ticker,
                        createdAt: refreshed[index].createdAt,
                        company: company
                    )
                } catch {
                    continue
                }
            }
            self.favorites = refreshed
        }
    }

    func search(_ text: String) async {
        guard text.trimmingCharacters(in: .whitespacesAndNewlines).count >= 2 else {
            searchResults = []
            return
        }
        await run(requiresAccess: true) {
            self.searchResults = try await self.api.searchCompanies(query: text)
        }
    }

    func addFavorite(_ ticker: String) async {
        await run(requiresAccess: true) {
            _ = try await self.api.addFavorite(userId: self.userId, ticker: ticker)
            self.favorites = try await self.api.favorites(userId: self.userId)
        }
    }

    func removeFavorite(_ ticker: String) async {
        await run(requiresAccess: true) {
            try await self.api.removeFavorite(userId: self.userId, ticker: ticker)
            self.favorites = try await self.api.favorites(userId: self.userId)
        }
    }

    func loadAlerts(ticker: String) async {
        await run(requiresAccess: true) {
            self.alertsByTicker[ticker] = try await self.api.alerts(userId: self.userId, ticker: ticker)
        }
    }

    func createAlert(_ request: AlertRuleCreateRequest) async {
        await run(requiresAccess: true) {
            _ = try await self.api.createAlert(userId: self.userId, request: request)
            self.alertsByTicker[request.ticker] = try await self.api.alerts(userId: self.userId, ticker: request.ticker)
        }
    }

    func updateAlert(_ alert: AlertRule, request: AlertRuleUpdateRequest) async {
        await run(requiresAccess: true) {
            _ = try await self.api.updateAlert(userId: self.userId, alertId: alert.id, request: request)
            self.alertsByTicker[alert.ticker] = try await self.api.alerts(userId: self.userId, ticker: alert.ticker)
        }
    }

    func updateAlertEnabled(_ alert: AlertRule, enabled: Bool) async {
        await run(requiresAccess: true) {
            _ = try await self.api.updateAlertEnabled(
                userId: self.userId,
                alertId: alert.id,
                enabled: enabled
            )
            self.alertsByTicker[alert.ticker] = try await self.api.alerts(userId: self.userId, ticker: alert.ticker)
        }
    }

    func deleteAlert(_ alert: AlertRule) async {
        await run(requiresAccess: true) {
            try await self.api.deleteAlert(userId: self.userId, alertId: alert.id)
            self.alertsByTicker[alert.ticker] = try await self.api.alerts(userId: self.userId, ticker: alert.ticker)
        }
    }

    func registerDevice(apnsToken: String) async {
        UserDefaults.standard.set(apnsToken, forKey: Self.apnsTokenStorageKey)
        await run {
            try await self.registerDeviceToken(apnsToken)
        }
    }

    func refreshDeviceRegistrationForLanguageChange() async {
        await refreshStoredDeviceRegistration()
    }

    func refreshStoredDeviceRegistration() async {
        guard
            let token = UserDefaults.standard.string(forKey: Self.apnsTokenStorageKey),
            !token.isEmpty
        else {
            return
        }

        await run {
            try await self.registerDeviceToken(token)
        }
    }

    func resendUserIdToCompanion() {
        WatchCompanionSyncService.shared.sendUserId(userId)
    }

    func adoptUserIdFromCompanion(_ companionUserId: String) {
        guard !companionUserId.isEmpty, companionUserId != userId else { return }

        userId = companionUserId
        UserIdentityStore.save(companionUserId)
        WatchCompanionSyncService.shared.sendUserId(companionUserId)
        Task {
            await bootstrap()
        }
    }

    func applyCompanionAccessContext(_ context: [String: Any]) {
        let access = context["has_access"] as? Bool
        if let paidAccess = context["paid_access"] as? Bool {
            UserDefaults.standard.set(paidAccess, forKey: Self.companionPaidAccessStorageKey)
            if let expiresAt = context["paid_access_expires_at"] as? String {
                UserDefaults.standard.set(expiresAt, forKey: Self.companionPaidAccessExpiresAtStorageKey)
            } else {
                UserDefaults.standard.removeObject(forKey: Self.companionPaidAccessExpiresAtStorageKey)
            }
        } else if access == false {
            UserDefaults.standard.set(false, forKey: Self.companionPaidAccessStorageKey)
            UserDefaults.standard.removeObject(forKey: Self.companionPaidAccessExpiresAtStorageKey)
        }

        let trialDaysLeft = context["trial_days_left"] as? Int
        let companionTrialActive = access == true && (trialDaysLeft ?? 0) > 0
        hasAccess = Self.storedPaidAccessIsCurrent() || companionTrialActive
        accessCheckCompleted = true

        if let trialDaysLeft {
            UserDefaults.standard.set(trialDaysLeft, forKey: Self.companionTrialDaysLeftStorageKey)
        } else {
            UserDefaults.standard.removeObject(forKey: Self.companionTrialDaysLeftStorageKey)
        }

        if !hasAccess {
            clearProtectedData()
        }
    }

    func requestPurchaseOnPhone() {
        WatchCompanionSyncService.shared.requestPurchaseOnPhone()
    }

    private func requestNotificationPermissionIfNeeded() async {
        do {
            switch await notificationAuthorizationStatus() {
            case .authorized, .provisional, .ephemeral:
                WKExtension.shared().registerForRemoteNotifications()
            case .notDetermined:
                let granted = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])
                if granted {
                    WKExtension.shared().registerForRemoteNotifications()
                }
            case .denied:
                break
            @unknown default:
                break
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func registerStoredDeviceIfAvailable() async throws {
        guard
            let token = UserDefaults.standard.string(forKey: Self.apnsTokenStorageKey),
            !token.isEmpty
        else {
            return
        }

        try await registerDeviceToken(token)
    }

    private func registerDeviceToken(_ token: String) async throws {
        try await api.registerDevice(userId: userId, token: token)
    }

    private func notificationAuthorizationStatus() async -> UNAuthorizationStatus {
        await withCheckedContinuation { continuation in
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                continuation.resume(returning: settings.authorizationStatus)
            }
        }
    }

    private func refreshAccessStatusFromServer() async {
        let trial = try? await api.iapTrial(userId: userId)
        hasAccess = Self.storedPaidAccessIsCurrent() || trial?.isActive == true
        accessCheckCompleted = true
        if !hasAccess {
            clearProtectedData()
        }
    }

    private func clearProtectedData() {
        favorites = []
        searchResults = []
        alertsByTicker = [:]
    }

    private static func storedPaidAccessIsCurrent() -> Bool {
        guard UserDefaults.standard.bool(forKey: companionPaidAccessStorageKey) else {
            return false
        }
        guard let expiresAt = UserDefaults.standard.string(forKey: companionPaidAccessExpiresAtStorageKey) else {
            return true
        }
        guard let expirationDate = dateFormatter.date(from: expiresAt) else {
            return false
        }
        return expirationDate > Date()
    }

    private func run(requiresAccess: Bool = false, _ operation: @escaping () async throws -> Void) async {
        if requiresAccess && !hasAccess {
            errorMessage = AppLanguage.shared.text("watch.access.message")
            return
        }

        isLoading = true
        errorMessage = nil
        do {
            try await operation()
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}
