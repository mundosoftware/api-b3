import Combine
import Foundation

@MainActor
final class CompanionAppModel: ObservableObject {
    static let shared = CompanionAppModel()

    @Published var favorites: [Favorite] = []
    @Published var searchResults: [Company] = []
    @Published var alertsByTicker: [String: [AlertRule]] = [:]
    @Published private(set) var preferences: NotificationPreferences?
    @Published var isLoading = false
    @Published var errorMessage: String?

    @Published private(set) var userId: String

    private let api = CompanionAPIClient.shared

    var iosNotificationsEnabled: Bool {
        preferences?.iosEnabled ?? true
    }

    var watchNotificationsEnabled: Bool {
        preferences?.watchosEnabled ?? true
    }

    var iosRegistrationStatus: String {
        preferences?.iosRegistered == true
            ? AppLanguage.shared.text("status.registered")
            : AppLanguage.shared.text("status.not_registered")
    }

    var watchRegistrationStatus: String {
        preferences?.watchosRegistered == true
            ? AppLanguage.shared.text("status.registered")
            : AppLanguage.shared.text("status.not_registered")
    }

    private init() {
        if let stored = UserDefaults.standard.string(forKey: "b3watch.userId") {
            userId = stored
        } else {
            let generated = UUID().uuidString
            UserDefaults.standard.set(generated, forKey: "b3watch.userId")
            userId = generated
        }
    }

    func bootstrap() async {
        CompanionWatchSyncService.shared.start(model: self)
        CompanionWatchSyncService.shared.sendUserId(userId)
        OneSignalService.shared.login(userId: userId)
        await run {
            try await self.api.upsertUser(userId: self.userId, timezone: TimeZone.current.identifier)
            self.preferences = try await self.api.notificationPreferences(userId: self.userId)
            self.favorites = try await self.api.favorites(userId: self.userId)
            try await self.registerIOSDeviceIfEnabled()
        }
    }

    func refreshFavorites() async {
        await run {
            self.favorites = try await self.api.favorites(userId: self.userId)
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

    func deleteAlert(_ alert: AlertRule) async {
        await run {
            try await self.api.deleteAlert(userId: self.userId, alertId: alert.id)
            self.alertsByTicker[alert.ticker] = try await self.api.alerts(userId: self.userId, ticker: alert.ticker)
        }
    }

    func setIOSNotificationsEnabled(_ enabled: Bool) {
        Task {
            await updateIOSNotificationsEnabled(enabled)
        }
    }

    func setWatchNotificationsEnabled(_ enabled: Bool) {
        Task {
            await updateNotificationPreferences(iosEnabled: nil, watchosEnabled: enabled)
        }
    }

    func handleServerSubscriptionAvailable() {
        Task {
            await run {
                try await self.registerIOSDeviceIfEnabled()
            }
        }
    }

    func adoptUserIdFromWatch(_ watchUserId: String) {
        guard !watchUserId.isEmpty, watchUserId != userId else { return }

        userId = watchUserId
        UserDefaults.standard.set(watchUserId, forKey: "b3watch.userId")
        OneSignalService.shared.login(userId: watchUserId)
        Task {
            await bootstrap()
        }
    }

    func updateIOSNotificationsEnabled(_ enabled: Bool) async {
        if enabled {
            let accepted = await OneSignalService.shared.requestPushPermission()
            guard accepted else {
                errorMessage = AppLanguage.shared.text("message.notifications_disabled")
                return
            }
        }

        await updateNotificationPreferences(iosEnabled: enabled, watchosEnabled: nil)
        if enabled {
            await run {
                try await self.registerIOSDeviceIfEnabled()
            }
        }
    }

    private func updateNotificationPreferences(
        iosEnabled: Bool?,
        watchosEnabled: Bool?
    ) async {
        await run {
            self.preferences = try await self.api.updateNotificationPreferences(
                userId: self.userId,
                iosEnabled: iosEnabled,
                watchosEnabled: watchosEnabled
            )
        }
    }

    private func registerIOSDeviceIfEnabled() async throws {
        guard preferences?.iosEnabled != false else { return }
        guard
            let subscriptionId = OneSignalService.shared.currentPushSubscriptionId,
            !subscriptionId.isEmpty,
            !subscriptionId.hasPrefix("local-")
        else {
            return
        }

        try await api.registerIOSDevice(userId: userId, subscriptionId: subscriptionId)
        preferences = try await api.notificationPreferences(userId: userId)
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
