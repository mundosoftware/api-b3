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

    @Published private(set) var userId: String
    private let api = APIClient.shared

    private init() {
        let identity = UserIdentityStore.loadOrCreate()
        userId = identity.userId
    }

    func bootstrap() async {
        WatchCompanionSyncService.shared.start(model: self)
        WatchCompanionSyncService.shared.sendUserId(userId)
        await run {
            try await self.api.upsertUser(userId: self.userId, timezone: TimeZone.current.identifier)
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
        await run {
            self.favorites = try await self.api.favorites(userId: self.userId)
        }
    }

    func refreshTrackedCompanies() async {
        await run {
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
        await run {
            self.searchResults = try await self.api.searchCompanies(query: text)
        }
    }

    func addFavorite(_ ticker: String) async {
        await run {
            _ = try await self.api.addFavorite(userId: self.userId, ticker: ticker)
            self.favorites = try await self.api.favorites(userId: self.userId)
        }
    }

    func removeFavorite(_ ticker: String) async {
        await run {
            try await self.api.removeFavorite(userId: self.userId, ticker: ticker)
            self.favorites = try await self.api.favorites(userId: self.userId)
        }
    }

    func loadAlerts(ticker: String) async {
        await run {
            self.alertsByTicker[ticker] = try await self.api.alerts(userId: self.userId, ticker: ticker)
        }
    }

    func createAlert(_ request: AlertRuleCreateRequest) async {
        await run {
            _ = try await self.api.createAlert(userId: self.userId, request: request)
            self.alertsByTicker[request.ticker] = try await self.api.alerts(userId: self.userId, ticker: request.ticker)
        }
    }

    func updateAlert(_ alert: AlertRule, request: AlertRuleUpdateRequest) async {
        await run {
            _ = try await self.api.updateAlert(userId: self.userId, alertId: alert.id, request: request)
            self.alertsByTicker[alert.ticker] = try await self.api.alerts(userId: self.userId, ticker: alert.ticker)
        }
    }

    func updateAlertEnabled(_ alert: AlertRule, enabled: Bool) async {
        await run {
            _ = try await self.api.updateAlertEnabled(
                userId: self.userId,
                alertId: alert.id,
                enabled: enabled
            )
            self.alertsByTicker[alert.ticker] = try await self.api.alerts(userId: self.userId, ticker: alert.ticker)
        }
    }

    func deleteAlert(_ alert: AlertRule) async {
        await run {
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

    private func run(_ operation: @escaping () async throws -> Void) async {
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
