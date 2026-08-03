import Foundation

enum AppConfig {
    enum Environment {
        case debug
        case production
    }

    #if DEBUG
    nonisolated static let environment: Environment = .debug
    nonisolated static let apiBaseURL = URL(string: "https://163.176.25.219")!//http://192.168.0.18:8000
    nonisolated static let deviceEnvironment = "development"
    #else
    nonisolated static let environment: Environment = .production
    nonisolated static let apiBaseURL = URL(string: "https://163.176.25.219")!
    nonisolated static let deviceEnvironment = "production"
    #endif
}
