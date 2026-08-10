import Foundation
import Security

enum UserIdentityStore {
    private static let service = "com.mundosoftware.tradealert.user"
    private static let account = "b3watch.userId"
    private static let legacyDefaultsKey = "b3watch.userId"

    static func loadOrCreate() -> (userId: String, isNew: Bool) {
        if let stored = loadFromKeychain(), !stored.isEmpty {
            UserDefaults.standard.set(stored, forKey: legacyDefaultsKey)
            return (stored, false)
        }

        if let legacy = UserDefaults.standard.string(forKey: legacyDefaultsKey), !legacy.isEmpty {
            save(legacy)
            return (legacy, false)
        }

        let generated = UUID().uuidString
        save(generated)
        return (generated, true)
    }

    static func save(_ userId: String) {
        guard !userId.isEmpty, let data = userId.data(using: .utf8) else { return }
        UserDefaults.standard.set(userId, forKey: legacyDefaultsKey)

        var addQuery = baseQuery
        addQuery[kSecValueData as String] = data
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock

        let status = SecItemAdd(addQuery as CFDictionary, nil)
        if status == errSecDuplicateItem {
            SecItemUpdate(baseQuery as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        }
    }

    private static func loadFromKeychain() -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private static var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }
}
