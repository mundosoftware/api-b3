import Foundation

enum AppConfig {
    enum Environment {
        case debug
        case production
    }

    enum APIEnvironment: String, CaseIterable, Identifiable, Sendable {
        case production
        case development

        var id: String { rawValue }
    }

    nonisolated static let productionAPIBaseURL = URL(string: "https://163.176.25.219")!
    nonisolated static let apiEnvironmentStorageKey = "tradealert.api-environment"

    #if DEBUG
    nonisolated static let environment: Environment = .debug
    private nonisolated static let developmentAPIBaseURL = URL(string: "https://163.176.25.219/dev")!

    nonisolated static var apiEnvironment: APIEnvironment {
        let stored = UserDefaults.standard.string(forKey: apiEnvironmentStorageKey)
        return stored.flatMap(APIEnvironment.init(rawValue:)) ?? .production
    }

    nonisolated static var apiBaseURL: URL {
        apiEnvironment == .development ? developmentAPIBaseURL : productionAPIBaseURL
    }
    #else
    nonisolated static let environment: Environment = .production
    nonisolated static let apiEnvironment: APIEnvironment = .production
    nonisolated static let apiBaseURL = productionAPIBaseURL
    #endif

    nonisolated static func apiURL(for path: String) -> URL? {
        let relativePath = path.hasPrefix("/") ? String(path.dropFirst()) : path
        let directoryBaseURL = apiBaseURL.appendingPathComponent("")
        return URL(string: relativePath, relativeTo: directoryBaseURL)?.absoluteURL
    }
}
