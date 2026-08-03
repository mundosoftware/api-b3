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
    var label: String { self == .price ? "Price" : "Percent" }
}

enum AlertOperator: String, Codable, CaseIterable, Identifiable {
    case gte
    case lte

    var id: String { rawValue }
    var label: String { self == .gte ? "Above" : "Below" }
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
    let deviceModel: String
    let deviceOs: String
    let appVersion: String

    enum CodingKeys: String, CodingKey {
        case onesignalSubscriptionId = "onesignal_subscription_id"
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
