import Foundation

enum AppConfig {
    enum Environment {
        case debug
        case production
    }

    #if DEBUG
    nonisolated static let environment: Environment = .debug
    nonisolated static let apiBaseURL = URL(string: "https://163.176.25.219")!// http://127.0.0.1:8000 or https://163.176.25.219
    #else
    nonisolated static let environment: Environment = .production
    nonisolated static let apiBaseURL = URL(string: "https://163.176.25.219")!
    #endif
}
