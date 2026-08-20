import Foundation

struct Company: Codable, Identifiable, Hashable {
    var id: String { ticker }
    let ticker: String
    let name: String
    let assetType: String
    let logo: String?
    let lastPrice: Double?
    let dailyChangePercent: Double?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case ticker
        case name
        case assetType = "asset_type"
        case logo
        case lastPrice = "last_price"
        case dailyChangePercent = "daily_change_percent"
        case updatedAt = "updated_at"
    }
}

struct CompanyListResponse: Codable {
    let result: [Company]
}

struct Favorite: Codable, Identifiable {
    var id: String { ticker }
    let ticker: String
    let createdAt: String
    let company: Company

    enum CodingKeys: String, CodingKey {
        case ticker
        case createdAt = "created_at"
        case company
    }
}

struct FavoriteListResponse: Codable {
    let result: [Favorite]
}

enum AlertMetric: String, Codable, CaseIterable, Identifiable {
    case price
    case percent

    var id: String { rawValue }
    var label: String {
        AppLanguage.shared.text(self == .price ? "metric.price" : "metric.percent")
    }
}

enum AlertOperator: String, Codable, CaseIterable, Identifiable {
    case gte
    case lte

    var id: String { rawValue }
    var label: String {
        AppLanguage.shared.text(self == .gte ? "operator.gte" : "operator.lte")
    }
}

struct AlertRule: Codable, Identifiable {
    let id: Int
    let userId: String
    let ticker: String
    let enabled: Bool
    let metric: AlertMetric
    let `operator`: AlertOperator
    let threshold: Double
    let baselinePrice: Double?
    let weekdays: [Int]
    let startTime: String
    let endTime: String
    let timezone: String
    let frequencyMinutes: Int
    let cooldownMinutes: Int
    let lastCheckedAt: String?
    let lastTriggeredAt: String?
    let lastPrice: Double?
    let lastPercentChange: Double?
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case ticker
        case enabled
        case metric
        case `operator`
        case threshold
        case baselinePrice = "baseline_price"
        case weekdays
        case startTime = "start_time"
        case endTime = "end_time"
        case timezone
        case frequencyMinutes = "frequency_minutes"
        case cooldownMinutes = "cooldown_minutes"
        case lastCheckedAt = "last_checked_at"
        case lastTriggeredAt = "last_triggered_at"
        case lastPrice = "last_price"
        case lastPercentChange = "last_percent_change"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct AlertRuleListResponse: Codable {
    let result: [AlertRule]
}

struct UserUpsertRequest: Encodable {
    let displayName: String?
    let timezone: String

    enum CodingKeys: String, CodingKey {
        case displayName = "display_name"
        case timezone
    }
}

struct IOSDeviceRegistrationRequest: Encodable {
    let onesignalSubscriptionId: String
    let language: String
    let deviceModel: String
    let deviceOs: String
    let appVersion: String

    enum CodingKeys: String, CodingKey {
        case onesignalSubscriptionId = "onesignal_subscription_id"
        case language
        case deviceModel = "device_model"
        case deviceOs = "device_os"
        case appVersion = "app_version"
    }
}

struct NotificationPreferences: Codable {
    let userId: String
    var iosEnabled: Bool
    var watchosEnabled: Bool
    let iosRegistered: Bool
    let watchosRegistered: Bool
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case iosEnabled = "ios_enabled"
        case watchosEnabled = "watchos_enabled"
        case iosRegistered = "ios_registered"
        case watchosRegistered = "watchos_registered"
        case updatedAt = "updated_at"
    }
}

struct NotificationPreferencesUpdateRequest: Encodable {
    let iosEnabled: Bool?
    let watchosEnabled: Bool?

    enum CodingKeys: String, CodingKey {
        case iosEnabled = "ios_enabled"
        case watchosEnabled = "watchos_enabled"
    }
}

struct FavoriteCreateRequest: Encodable {
    let ticker: String
}

struct AlertRuleCreateRequest: Encodable {
    let ticker: String
    let metric: AlertMetric
    let `operator`: AlertOperator
    let threshold: Double
    let baselinePrice: Double?
    let weekdays: [Int]
    let startTime: String
    let endTime: String
    let timezone: String
    let frequencyMinutes: Int
    let cooldownMinutes: Int
    let enabled: Bool

    enum CodingKeys: String, CodingKey {
        case ticker
        case metric
        case `operator`
        case threshold
        case baselinePrice = "baseline_price"
        case weekdays
        case startTime = "start_time"
        case endTime = "end_time"
        case timezone
        case frequencyMinutes = "frequency_minutes"
        case cooldownMinutes = "cooldown_minutes"
        case enabled
    }
}

struct AlertRuleUpdateRequest: Encodable {
    let enabled: Bool
    let metric: AlertMetric
    let `operator`: AlertOperator
    let threshold: Double
    let baselinePrice: Double?
    let weekdays: [Int]
    let startTime: String
    let endTime: String
    let timezone: String
    let frequencyMinutes: Int
    let cooldownMinutes: Int

    enum CodingKeys: String, CodingKey {
        case enabled
        case metric
        case `operator`
        case threshold
        case baselinePrice = "baseline_price"
        case weekdays
        case startTime = "start_time"
        case endTime = "end_time"
        case timezone
        case frequencyMinutes = "frequency_minutes"
        case cooldownMinutes = "cooldown_minutes"
    }
}

struct AlertRuleEnabledUpdateRequest: Encodable {
    let enabled: Bool
}

struct DeviceRegistrationResponse: Decodable {
    let userId: String
    let onesignalConfigured: Bool
    let onesignalSubscriptionId: String?

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case onesignalConfigured = "onesignal_configured"
        case onesignalSubscriptionId = "onesignal_subscription_id"
    }
}

struct EmptyResponse: Decodable {}

struct IAPTrialStatus: Decodable {
    let productId: String
    let status: String
    let startsAt: String?
    let endsAt: String?
    let nextAvailableAt: String?
    let requestCount: Int
    let canRequest: Bool
    let currentTime: String?
    let elapsedDays: Int?
    let remainingDays: Int?
    let remainingSeconds: Int?
    let totalTrialDays: Int?
    let message: String?

    var isActive: Bool {
        status == "active"
    }

    var isPending: Bool {
        status == "pending"
    }

    var daysLeft: Int {
        if let remainingDays {
            return max(0, remainingDays)
        }

        guard let endsAt, let endDate = Self.date(from: endsAt) else {
            return 0
        }

        let seconds = max(0, endDate.timeIntervalSinceNow)
        return Int(ceil(seconds / 86_400))
    }

    enum CodingKeys: String, CodingKey {
        case productId = "product_id"
        case status
        case startsAt = "starts_at"
        case endsAt = "ends_at"
        case nextAvailableAt = "next_available_at"
        case requestCount = "request_count"
        case canRequest = "can_request"
        case currentTime = "current_time"
        case elapsedDays = "elapsed_days"
        case remainingDays = "remaining_days"
        case remainingSeconds = "remaining_seconds"
        case totalTrialDays = "total_trial_days"
        case message
    }

    private static let isoDateFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private static let fractionalISODateFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static func date(from value: String) -> Date? {
        isoDateFormatter.date(from: value) ?? fractionalISODateFormatter.date(from: value)
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        productId = try container.decode(String.self, forKey: .productId)
        status = try container.decode(String.self, forKey: .status)
        startsAt = try container.decodeIfPresent(String.self, forKey: .startsAt)
        endsAt = try container.decodeIfPresent(String.self, forKey: .endsAt)
        nextAvailableAt = try container.decodeIfPresent(String.self, forKey: .nextAvailableAt)
        requestCount = try container.decode(Int.self, forKey: .requestCount)
        canRequest = try container.decode(Bool.self, forKey: .canRequest)
        currentTime = try container.decodeIfPresent(String.self, forKey: .currentTime)
        elapsedDays = try container.decodeIfPresent(Int.self, forKey: .elapsedDays)
        remainingDays = try container.decodeIfPresent(Int.self, forKey: .remainingDays)
        remainingSeconds = try container.decodeIfPresent(Int.self, forKey: .remainingSeconds)
        totalTrialDays = try container.decodeIfPresent(Int.self, forKey: .totalTrialDays)
        message = try container.decodeIfPresent(String.self, forKey: .message)
    }
}
