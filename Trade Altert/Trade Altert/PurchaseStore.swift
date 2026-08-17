import Combine
import Foundation
import StoreKit

@MainActor
final class PurchaseStore: ObservableObject {
    static let shared = PurchaseStore()

    enum ProductID {
        static let lifetimeUnlock = "lifetime_unlock"
        static let proMonth = "pro_month"
        static let proYear = "pro_year"
    }

    static let privacyAndTermsURL = URL(string: "https://mundsoftware.com/trade-alert/privacy.html")!

    private static let productIDs: Set<String> = [
        ProductID.proYear,
        ProductID.proMonth,
        ProductID.lifetimeUnlock,
    ]

    private static let productOrder = [
        ProductID.proYear,
        ProductID.proMonth,
        ProductID.lifetimeUnlock,
    ]

    private static let lastPaidAppVersion = "1.1.0"

    @Published private(set) var products: [Product] = []
    @Published private(set) var purchasedProductIDs: Set<String> = []
    @Published private(set) var introOfferEligibleProductIDs: Set<String> = []
    @Published private(set) var hasAccess = false
    @Published private(set) var hasResolvedAccess = false
    @Published private(set) var legacyPaidAccess = false
    @Published private(set) var isLoadingProducts = false
    @Published private(set) var isPurchasing = false
    @Published private(set) var isRestoring = false
    @Published var message: String?

    private var updatesTask: Task<Void, Never>?

    private init() {
        updatesTask = observeTransactionUpdates()
    }

    deinit {
        updatesTask?.cancel()
    }

    var selectedDefaultProductID: String {
        products.first(where: { $0.id == ProductID.proYear })?.id
            ?? products.first?.id
            ?? ProductID.proYear
    }

    func load() async {
        guard !isLoadingProducts else { return }

        isLoadingProducts = true
        message = nil

        do {
            let storeProducts = try await Product.products(for: Array(Self.productIDs))
            products = storeProducts.sorted(by: productSort)
            introOfferEligibleProductIDs = await eligibleIntroOfferIDs(in: storeProducts)
        } catch {
            message = String(format: AppLanguage.shared.text("purchase.error.load_products"), error.localizedDescription)
        }

        await refreshPurchasedProducts()
        hasResolvedAccess = true
        isLoadingProducts = false
    }

    func purchase(_ product: Product) async {
        guard !isPurchasing else { return }

        isPurchasing = true
        message = nil
        defer { isPurchasing = false }

        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                let transaction = try checkVerified(verification)
                await transaction.finish()
                await refreshPurchasedProducts()
            case .pending:
                message = AppLanguage.shared.text("purchase.pending")
            case .userCancelled:
                break
            @unknown default:
                break
            }
        } catch {
            message = String(format: AppLanguage.shared.text("purchase.error.purchase_failed"), error.localizedDescription)
        }
    }

    func restorePurchases() async {
        guard !isRestoring else { return }

        isRestoring = true
        message = nil
        defer { isRestoring = false }

        do {
            try await AppStore.sync()
            await refreshPurchasedProducts()
            if !hasAccess {
                message = AppLanguage.shared.text("purchase.restore.none")
            }
        } catch {
            message = String(format: AppLanguage.shared.text("purchase.error.restore_failed"), error.localizedDescription)
        }
    }

    func isIntroOfferEligible(for product: Product) -> Bool {
        introOfferEligibleProductIDs.contains(product.id)
    }

    private func observeTransactionUpdates() -> Task<Void, Never> {
        Task { [weak self] in
            for await result in Transaction.updates {
                guard let self else { return }
                guard case .verified(let transaction) = result else { continue }
                await transaction.finish()
                await self.refreshPurchasedProducts()
            }
        }
    }

    private func refreshPurchasedProducts() async {
        var activeProductIDs = Set<String>()

        for await result in Transaction.currentEntitlements {
            guard case .verified(let transaction) = result else { continue }
            guard Self.productIDs.contains(transaction.productID) else { continue }
            guard transaction.revocationDate == nil else { continue }
            guard transaction.expirationDate.map({ $0 > Date() }) ?? true else { continue }
            guard !transaction.isUpgraded else { continue }

            activeProductIDs.insert(transaction.productID)
        }

        let hasLegacyAccess = await hasLegacyPaidAppAccess()
        purchasedProductIDs = activeProductIDs
        legacyPaidAccess = hasLegacyAccess
        hasAccess = hasLegacyAccess || !activeProductIDs.isEmpty
    }

    private func eligibleIntroOfferIDs(in products: [Product]) async -> Set<String> {
        var eligibleProductIDs = Set<String>()

        for product in products {
            guard let subscription = product.subscription else { continue }
            guard subscription.introductoryOffer != nil else { continue }
            if await subscription.isEligibleForIntroOffer {
                eligibleProductIDs.insert(product.id)
            }
        }

        return eligibleProductIDs
    }

    private func productSort(_ lhs: Product, _ rhs: Product) -> Bool {
        let lhsIndex = Self.productOrder.firstIndex(of: lhs.id) ?? Self.productOrder.count
        let rhsIndex = Self.productOrder.firstIndex(of: rhs.id) ?? Self.productOrder.count
        return lhsIndex < rhsIndex
    }

    private func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .verified(let value):
            return value
        case .unverified:
            throw PurchaseError.failedVerification
        }
    }

    private func hasLegacyPaidAppAccess() async -> Bool {
        #if DEBUG
        return false
        #else
        guard case .verified(let appTransaction) = try? await AppTransaction.shared else {
            return false
        }
        return Self.isVersion(appTransaction.originalAppVersion, atMost: Self.lastPaidAppVersion)
        #endif
    }

    private static func isVersion(_ version: String, atMost maxVersion: String) -> Bool {
        let lhs = versionComponents(version)
        let rhs = versionComponents(maxVersion)
        let count = max(lhs.count, rhs.count)

        for index in 0..<count {
            let left = index < lhs.count ? lhs[index] : 0
            let right = index < rhs.count ? rhs[index] : 0
            if left != right {
                return left < right
            }
        }

        return true
    }

    private static func versionComponents(_ version: String) -> [Int] {
        version
            .split(separator: ".")
            .map { Int($0) ?? 0 }
    }
}

private enum PurchaseError: LocalizedError {
    case failedVerification

    var errorDescription: String? {
        switch self {
        case .failedVerification:
            return AppLanguage.shared.text("purchase.error.verification")
        }
    }
}
