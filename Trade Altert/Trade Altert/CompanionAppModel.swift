import Combine
import Foundation

@MainActor
final class CompanionAppModel: ObservableObject {
    static let shared = CompanionAppModel()

    @Published var favorites: [Favorite] = []
    @Published var searchResults: [Company] = []
    @Published var alertsByTicker: [String: [AlertRule]] = [:]
    @Published private(set) var preferences: NotificationPreferences?
    @Published private(set) var aiOutlookFeatureStatus: AIOutlookFeatureStatus?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var shouldShowPurchasePlansFromWatch = false

    @Published private(set) var userId: String

    private let api = CompanionAPIClient.shared
    private var aiAnalysisCache: [AIAnalysisCacheKey: DecisionSupportAnalysis] = [:]
    private var persistedAIOutlookJobs = AIOutlookJobStateStore.load()
    private var userIdWasGenerated: Bool

    var iosNotificationsEnabled: Bool {
        preferences?.iosEnabled ?? true
    }

    var watchNotificationsEnabled: Bool {
        preferences?.watchosEnabled ?? true
    }

    var aiOutlookEnabled: Bool {
        preferences?.aiOutlookEnabled == true
    }

    var aiOutlookAvailable: Bool {
        aiOutlookFeatureStatus?.enabled ?? true
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
        let identity = UserIdentityStore.loadOrCreate()
        userId = identity.userId
        userIdWasGenerated = identity.isNew
    }

    func bootstrap() async {
        CompanionWatchSyncService.shared.start(model: self)
        CompanionWatchSyncService.shared.sendUserId(userId)
        OneSignalService.shared.login(userId: userId)
        await run {
            try await self.api.upsertUser(userId: self.userId, timezone: TimeZone.current.identifier)
            self.aiOutlookFeatureStatus = try? await self.api.aiOutlookFeatureStatus()
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

    func setIOSNotificationsEnabled(_ enabled: Bool) {
        Task {
            await updateIOSNotificationsEnabled(enabled)
        }
    }

    func setWatchNotificationsEnabled(_ enabled: Bool) {
        Task {
            if enabled {
                CompanionWatchSyncService.shared.sendUserId(userId)
            }
            await updateNotificationPreferences(iosEnabled: nil, watchosEnabled: enabled)
            if enabled {
                CompanionWatchSyncService.shared.sendUserId(userId)
            }
        }
    }

    @discardableResult
    func updateAIOutlookEnabled(_ enabled: Bool) async -> Bool {
        guard aiOutlookAvailable else {
            errorMessage = AppLanguage.shared.text("ai.maintenance.message")
            return false
        }
        isLoading = true
        errorMessage = nil
        do {
            self.preferences = try await self.api.updateNotificationPreferences(
                userId: self.userId,
                iosEnabled: nil,
                watchosEnabled: nil,
                aiOutlookEnabled: enabled
            )
            if enabled, self.preferences?.iosEnabled != false {
                let accepted = await OneSignalService.shared.requestPushPermission()
                if accepted {
                    try await self.registerIOSDeviceIfEnabled(waitForSubscription: true)
                } else {
                    errorMessage = AppLanguage.shared.text("message.notifications_disabled")
                }
            }
        } catch {
            errorMessage = AppLanguage.shared.aiOutlookErrorText(error)
        }
        isLoading = false
        return preferences?.aiOutlookEnabled == enabled
    }

    func refreshAIOutlookFeatureStatus(force: Bool = true) async {
        if !force, aiOutlookFeatureStatus != nil { return }
        isLoading = true
        errorMessage = nil
        do {
            self.aiOutlookFeatureStatus = try await self.api.aiOutlookFeatureStatus()
        } catch {
            errorMessage = AppLanguage.shared.aiOutlookErrorText(error)
        }
        isLoading = false
    }

    func cachedAIAnalysis(ticker: String, interval: String, horizon: Int) -> DecisionSupportAnalysis? {
        aiAnalysisCache[AIAnalysisCacheKey(ticker: ticker, interval: interval, horizon: horizon)]
    }

    func storeAIAnalysis(_ analysis: DecisionSupportAnalysis) {
        aiAnalysisCache[AIAnalysisCacheKey(
            ticker: analysis.ticker,
            interval: analysis.interval,
            horizon: analysis.horizon
        )] = analysis
    }

    func storedAIOutlookJob(
        ticker: String,
        interval: String,
        range: String,
        horizon: Int
    ) -> AIOutlookJob? {
        let key = AIOutlookJobStorageKey(
            userId: userId,
            ticker: ticker,
            interval: interval,
            range: range,
            horizon: horizon
        )
        return persistedAIOutlookJobs.last { $0.key == key }?.job
    }

    func storeAIOutlookJob(_ job: AIOutlookJob) {
        if job.status == .canceled {
            clearAIOutlookJob(job)
            return
        }
        if let analysis = job.result {
            storeAIAnalysis(analysis)
        }
        let stored = PersistedAIOutlookJob(job: job)
        persistedAIOutlookJobs.removeAll { $0.key == stored.key }
        persistedAIOutlookJobs.append(stored)
        if persistedAIOutlookJobs.count > 40 {
            persistedAIOutlookJobs.removeFirst(persistedAIOutlookJobs.count - 40)
        }
        AIOutlookJobStateStore.save(persistedAIOutlookJobs)
    }

    func clearAIOutlookJob(_ job: AIOutlookJob) {
        let key = PersistedAIOutlookJob(job: job).key
        persistedAIOutlookJobs.removeAll { $0.key == key || $0.job.jobId == job.jobId }
        AIOutlookJobStateStore.save(persistedAIOutlookJobs)
    }

    func clearAIOutlookJob(
        ticker: String,
        interval: String,
        range: String,
        horizon: Int
    ) {
        let key = AIOutlookJobStorageKey(
            userId: userId,
            ticker: ticker,
            interval: interval,
            range: range,
            horizon: horizon
        )
        persistedAIOutlookJobs.removeAll { $0.key == key }
        AIOutlookJobStateStore.save(persistedAIOutlookJobs)
    }

    func handleServerSubscriptionAvailable() {
        Task {
            await run {
                try await self.registerIOSDeviceIfEnabled()
            }
        }
    }

    func requestPurchasePlansFromWatch() {
        shouldShowPurchasePlansFromWatch = true
    }

    func adoptUserIdFromWatch(_ watchUserId: String) {
        guard !watchUserId.isEmpty, watchUserId != userId else { return }
        guard userIdWasGenerated else {
            CompanionWatchSyncService.shared.sendUserId(userId)
            return
        }

        userId = watchUserId
        userIdWasGenerated = false
        UserIdentityStore.save(watchUserId)
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

    private func registerIOSDeviceIfEnabled(waitForSubscription: Bool = false) async throws {
        guard preferences?.iosEnabled != false else { return }
        let subscriptionId: String?
        if waitForSubscription {
            subscriptionId = await OneSignalService.shared.waitForUsablePushSubscription()
        } else {
            subscriptionId = OneSignalService.shared.currentPushSubscriptionId
        }
        guard let subscriptionId, !subscriptionId.isEmpty, !subscriptionId.hasPrefix("local-") else {
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

private struct AIAnalysisCacheKey: Hashable {
    let ticker: String
    let interval: String
    let horizon: Int

    init(ticker: String, interval: String, horizon: Int) {
        self.ticker = ticker.uppercased()
        self.interval = interval
        self.horizon = horizon
    }
}

private struct AIOutlookJobStorageKey: Codable, Hashable {
    let userId: String
    let ticker: String
    let interval: String
    let range: String
    let horizon: Int

    init(userId: String, ticker: String, interval: String, range: String, horizon: Int) {
        self.userId = userId
        self.ticker = ticker.uppercased()
        self.interval = interval
        self.range = range
        self.horizon = horizon
    }
}

private struct PersistedAIOutlookJob: Codable {
    let key: AIOutlookJobStorageKey
    let job: AIOutlookJob

    init(job: AIOutlookJob) {
        self.key = AIOutlookJobStorageKey(
            userId: job.userId,
            ticker: job.ticker,
            interval: job.interval,
            range: job.range,
            horizon: job.horizon
        )
        self.job = job
    }
}

private enum AIOutlookJobStateStore {
    private static let storageKey = "tradealert.ai_outlook.jobs"
    private static let encoder = JSONEncoder()
    private static let decoder = JSONDecoder()

    static func load() -> [PersistedAIOutlookJob] {
        guard let data = UserDefaults.standard.data(forKey: storageKey) else { return [] }
        return (try? decoder.decode([PersistedAIOutlookJob].self, from: data)) ?? []
    }

    static func save(_ jobs: [PersistedAIOutlookJob]) {
        guard let data = try? encoder.encode(jobs) else { return }
        UserDefaults.standard.set(data, forKey: storageKey)
    }
}
