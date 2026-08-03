import Foundation

enum AppConfig {
    enum Environment {
        case debug
        case production
    }

    #if DEBUG
    nonisolated static let environment: Environment = .debug
    nonisolated static let apiBaseURL = URL(string: "http://192.168.0.18:8000")!
    #else
    nonisolated static let environment: Environment = .production
    nonisolated static let apiBaseURL = URL(string: "http://163.176.25.219:8000")!
    #endif
}
