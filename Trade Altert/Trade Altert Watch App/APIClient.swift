import Foundation

enum APIError: Error, LocalizedError {
    case invalidURL
    case badResponse(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return AppLanguage.shared.text("api.invalid_url")
        case let .badResponse(status, message):
            return "HTTP \(status): \(message)"
        }
    }
}

actor APIClient {
    static let shared = APIClient()

    private let baseURL = AppConfig.apiBaseURL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    func upsertUser(userId: String, timezone: String) async throws {
        let body = UserUpsertRequest(displayName: nil, timezone: timezone)
        let _: EmptyResponse = try await send("/users/\(userId)", method: "PUT", body: body)
    }

    func registerDevice(userId: String, token: String) async throws {
        let device = WKDeviceSnapshot.current
        let body = DeviceRegistrationRequest(
            apnsToken: token,
            environment: AppConfig.deviceEnvironment,
            language: AppLanguage.shared.code.rawValue,
            deviceModel: device.model,
            deviceOs: device.systemVersion,
            appVersion: device.appVersion
        )
        let _: EmptyResponse = try await send("/users/\(userId)/devices/watchos", method: "POST", body: body)
    }

    func searchCompanies(query: String) async throws -> [Company] {
        let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        let response: CompanyListResponse = try await send("/companies/search?q=\(encoded)&limit=25")
        return response.result
    }

    func quote(ticker: String) async throws -> Company {
        try await send("/companies/\(ticker)?refresh=true")
    }

    func favorites(userId: String) async throws -> [Favorite] {
        let response: FavoriteListResponse = try await send("/users/\(userId)/favorites")
        return response.result
    }

    func addFavorite(userId: String, ticker: String) async throws -> Favorite {
        try await send("/users/\(userId)/favorites", method: "POST", body: FavoriteCreateRequest(ticker: ticker))
    }

    func removeFavorite(userId: String, ticker: String) async throws {
        try await sendNoContent("/users/\(userId)/favorites/\(ticker)", method: "DELETE")
    }

    func alerts(userId: String, ticker: String? = nil) async throws -> [AlertRule] {
        let suffix = ticker.map { "?ticker=\($0)" } ?? ""
        let response: AlertRuleListResponse = try await send("/users/\(userId)/alerts\(suffix)")
        return response.result
    }

    func createAlert(userId: String, request: AlertRuleCreateRequest) async throws -> AlertRule {
        try await send("/users/\(userId)/alerts", method: "POST", body: request)
    }

    func updateAlert(userId: String, alertId: Int, request: AlertRuleUpdateRequest) async throws -> AlertRule {
        try await send("/users/\(userId)/alerts/\(alertId)", method: "PATCH", body: request)
    }

    func deleteAlert(userId: String, alertId: Int) async throws {
        try await sendNoContent("/users/\(userId)/alerts/\(alertId)", method: "DELETE")
    }

    private func send<T: Decodable>(_ path: String, method: String = "GET") async throws -> T {
        let request = try makeRequest(path: path, method: method, body: Optional<EmptyBody>.none)
        return try await decode(request)
    }

    private func send<T: Decodable, Body: Encodable>(_ path: String, method: String, body: Body) async throws -> T {
        let request = try makeRequest(path: path, method: method, body: body)
        return try await decode(request)
    }

    private func sendNoContent(_ path: String, method: String) async throws {
        let request = try makeRequest(path: path, method: method, body: Optional<EmptyBody>.none)
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.badResponse(http.statusCode, "")
        }
    }

    private func makeRequest<Body: Encodable>(path: String, method: String, body: Body?) throws -> URLRequest {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = try encoder.encode(body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return request
    }

    private func decode<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.badResponse(-1, "")
        }
        guard (200..<300).contains(http.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? ""
            throw APIError.badResponse(http.statusCode, message)
        }
        if T.self == EmptyResponse.self {
            return EmptyResponse() as! T
        }
        return try decoder.decode(T.self, from: data)
    }
}

struct EmptyBody: Encodable {}
struct EmptyResponse: Decodable {}
