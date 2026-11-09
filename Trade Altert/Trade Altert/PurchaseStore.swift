import Combine
import Foundation
import StoreKit
import UIKit

@MainActor
final class PurchaseStore: ObservableObject {
    static let shared = PurchaseStore()

    enum ProductID {
        static let lifetimeUnlock = "lifetime_unlock"
        static let proMonth = "pro_month"
        static let proYear = "pro_year"
        static let trialSevenDays = "trial_7_days"
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
    @Published private(set) var trialStatus: IAPTrialStatus?
    @Published private(set) var purchasedProductIDs: Set<String> = []
    @Published private(set) var paidAccessExpiresAt: Date?
    @Published private(set) var introOfferEligibleProductIDs: Set<String> = []
    @Published private(set) var availablePromotion: PromotionOffer?
    @Published private(set) var hasAccess = false
    @Published private(set) var hasResolvedAccess = false
    @Published private(set) var legacyPaidAccess = false
    @Published private(set) var isLoadingProducts = false
    @Published private(set) var isPurchasing = false
    @Published private(set) var isRestoring = false
    @Published var isPresentingOfferCodeRedemption = false
    @Published private(set) var shouldRequestNativeReview = false
    @Published private(set) var trialExtensionDaysGranted = 0
    @Published var message: String?

    private var updatesTask: Task<Void, Never>?
    private var currentUserId: String?
    private var pendingPromotionRedemption: PromotionOffer?
    private var pendingPromotionContext = "unknown"

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

    var isTrialActive: Bool {
        trialStatus?.isActive == true
    }

    var hasPaidAccess: Bool {
        legacyPaidAccess || !purchasedProductIDs.isEmpty
    }

    var isTrialPending: Bool {
        trialStatus?.isPending == true
    }

    var trialDaysLeft: Int {
        trialStatus?.daysLeft ?? 0
    }

    func load() async {
        await load(userId: nil)
    }

    func load(userId: String?) async {
        guard !isLoadingProducts else { return }

        currentUserId = userId
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
        if let userId {
            trialStatus = try? await CompanionAPIClient.shared.iapTrial(userId: userId)
            if isTrialActive && !hasPaidAccess {
                await claimAutomaticTrialExtension(userId: userId)
            }
            refreshNativeReviewEligibility(userId: userId)
            if hasPaidAccess {
                availablePromotion = nil
            } else {
                await loadPromotion(userId: userId)
            }
            updateHasAccess()
        }
        hasResolvedAccess = true
        isLoadingProducts = false
    }

    func requestTrial(userId: String) async -> IAPTrialStatus? {
        do {
            let status = try await CompanionAPIClient.shared.requestIAPTrial(userId: userId)
            trialStatus = status
            updateHasAccess()
            return status
        } catch {
            message = error.localizedDescription
            return nil
        }
    }

    func purchase(_ product: Product) async {
        guard !isPurchasing else { return }

        isPurchasing = true
        message = nil
        defer { isPurchasing = false }

        await recordTelemetry(eventType: "purchase_started", product: product, status: "started")
        do {
            let result: Product.PurchaseResult
            if let currentUserId, let accountToken = UUID(uuidString: currentUserId) {
                result = try await product.purchase(options: [.appAccountToken(accountToken)])
            } else {
                result = try await product.purchase()
            }
            switch result {
            case .success(let verification):
                let transaction = try checkVerified(verification)
                await recordTelemetry(
                    eventType: "purchase_succeeded",
                    product: product,
                    transaction: transaction,
                    status: "succeeded"
                )
                await transaction.finish()
                await refreshPurchasedProducts()
                availablePromotion = nil
            case .pending:
                message = AppLanguage.shared.text("purchase.pending")
                await recordTelemetry(eventType: "purchase_pending", product: product, status: "pending")
            case .userCancelled:
                await recordTelemetry(eventType: "purchase_cancelled", product: product, status: "cancelled")
                break
            @unknown default:
                break
            }
        } catch {
            message = String(format: AppLanguage.shared.text("purchase.error.purchase_failed"), error.localizedDescription)
            await recordTelemetry(
                eventType: "purchase_failed",
                product: product,
                status: "failed",
                reason: "storekit_error",
                details: error.localizedDescription
            )
        }
    }

    func restorePurchases() async {
        guard !isRestoring else { return }

        isRestoring = true
        message = nil
        defer { isRestoring = false }

        await recordTelemetry(eventType: "restore_started", status: "started")
        do {
            try await AppStore.sync()
            await refreshPurchasedProducts()
            if !hasPaidAccess {
                message = AppLanguage.shared.text("purchase.restore.none")
            } else {
                await recordTelemetry(eventType: "restore_succeeded", status: "succeeded")
            }
        } catch {
            message = String(format: AppLanguage.shared.text("purchase.error.restore_failed"), error.localizedDescription)
            await recordTelemetry(
                eventType: "restore_failed",
                status: "failed",
                reason: "storekit_error",
                details: error.localizedDescription
            )
        }
    }

    func localizedPromotionPrice(_ promotion: PromotionOffer) -> String {
        guard let product = products.first(where: { $0.id == promotion.productId }) else {
            return promotion.promotionalPriceBrl.formatted(
                .currency(code: "BRL").locale(Locale(identifier: "pt_BR"))
            )
        }
        let multiplier = Decimal(max(0, 1 - promotion.discountPercent / 100))
        return (product.price * multiplier).formatted(product.priceFormatStyle)
    }

    func beginPromotionRedemption(
        _ promotion: PromotionOffer,
        context: String
    ) async {
        guard promotion.id == availablePromotion?.id, currentUserId != nil else { return }
        await recordPromotionInteraction(
            "redeem_offer_tapped",
            promotion: promotion,
            context: context
        )
        UIPasteboard.general.string = promotion.code
        await recordPromotionInteraction(
            "code_auto_copied",
            promotion: promotion,
            context: context
        )
        pendingPromotionRedemption = promotion
        pendingPromotionContext = context
        isPresentingOfferCodeRedemption = true
        await recordPromotionInteraction(
            "redemption_sheet_presented",
            promotion: promotion,
            context: context
        )
    }

    func setPromotionHiddenOnHome(_ promotion: PromotionOffer, hidden: Bool) async {
        guard promotion.id == availablePromotion?.id,
              promotion.allowHomeSuppression,
              let currentUserId else { return }
        await recordPromotionInteraction(
            hidden ? "dont_show_again_enabled" : "dont_show_again_disabled",
            promotion: promotion,
            context: "home"
        )
        do {
            try await CompanionAPIClient.shared.updatePromotionHomeVisibility(
                userId: currentUserId,
                slug: promotion.slug,
                hideOnHome: hidden
            )
            await loadPromotion(userId: currentUserId)
        } catch {
            message = AppLanguage.shared.text("promotion.error.preference")
            await recordTelemetry(
                eventType: "promotion_home_suppression_failed",
                productId: promotion.productId,
                status: "failed",
                reason: "server_error",
                details: error.localizedDescription
            )
        }
    }

    func handleOfferCodeRedemptionPresentation(_ result: Result<Void, Error>) async {
        let promotion = pendingPromotionRedemption ?? availablePromotion
        let context = pendingPromotionContext
        defer {
            pendingPromotionRedemption = nil
            pendingPromotionContext = "unknown"
        }
        if case .failure(let error) = result {
            message = String(
                format: AppLanguage.shared.text("promotion.error.redemption"),
                error.localizedDescription
            )
            await recordTelemetry(
                eventType: "promotion_redemption_failed",
                productId: availablePromotion?.productId,
                status: "failed",
                reason: "storekit_error",
                details: error.localizedDescription
            )
            if let promotion {
                await recordPromotionInteraction(
                    "redemption_sheet_failed",
                    promotion: promotion,
                    context: context
                )
            }
        } else if let promotion {
            await recordPromotionInteraction(
                "redemption_sheet_completed",
                promotion: promotion,
                context: context
            )
        }
    }

    func recordPromotionInteraction(
        _ eventType: String,
        promotion: PromotionOffer,
        context: String
    ) async {
        guard let currentUserId else { return }
        let device = CompanionDeviceSnapshot.current
        let request = PromotionInteractionRequest(
            eventType: eventType,
            presentationContext: context,
            platform: "ios",
            environment: AppConfig.apiEnvironment.rawValue,
            appVersion: device.appVersion,
            deviceModel: device.model,
            deviceOs: device.systemVersion,
            language: AppLanguage.shared.code.rawValue,
            occurredAt: ISO8601DateFormatter().string(from: Date())
        )
        try? await CompanionAPIClient.shared.recordPromotionInteraction(
            userId: currentUserId,
            slug: promotion.slug,
            request: request
        )
    }

    func consumeNativeReviewRequest() {
        shouldRequestNativeReview = false
        guard let currentUserId else { return }
        UserDefaults.standard.set(true, forKey: reviewRequestedKey(userId: currentUserId))
        UserDefaults.standard.removeObject(forKey: reviewEligibleDateKey(userId: currentUserId))
    }

    func isIntroOfferEligible(for product: Product) -> Bool {
        introOfferEligibleProductIDs.contains(product.id)
    }

    private func observeTransactionUpdates() -> Task<Void, Never> {
        Task { [weak self] in
            for await result in Transaction.updates {
                guard let self else { return }
                guard case .verified(let transaction) = result else { continue }
                await self.processOfferCodeTransaction(transaction)
                await transaction.finish()
                await self.refreshPurchasedProducts()
            }
        }
    }

    private func refreshPurchasedProducts() async {
        var activeProductIDs = Set<String>()
        var latestSubscriptionExpiration: Date?
        var hasNonExpiringAccess = false

        for await result in Transaction.currentEntitlements {
            guard case .verified(let transaction) = result else { continue }
            guard Self.productIDs.contains(transaction.productID) else { continue }
            guard transaction.revocationDate == nil else { continue }
            guard transaction.expirationDate.map({ $0 > Date() }) ?? true else { continue }
            guard !transaction.isUpgraded else { continue }

            activeProductIDs.insert(transaction.productID)
            if let expirationDate = transaction.expirationDate {
                latestSubscriptionExpiration = max(latestSubscriptionExpiration ?? expirationDate, expirationDate)
            } else {
                hasNonExpiringAccess = true
            }
        }

        let hasLegacyAccess = await hasLegacyPaidAppAccess()
        purchasedProductIDs = activeProductIDs
        legacyPaidAccess = hasLegacyAccess
        paidAccessExpiresAt = hasLegacyAccess || hasNonExpiringAccess ? nil : latestSubscriptionExpiration
        updateHasAccess()
    }

    private func claimAutomaticTrialExtension(userId: String) async {
        do {
            let grant = try await CompanionAPIClient.shared.grantTrialEngagementExtension(userId: userId)
            trialStatus = grant.trial
            guard grant.granted else { return }
            trialExtensionDaysGranted = grant.extensionDays
            UserDefaults.standard.set(
                Date().addingTimeInterval(24 * 60 * 60),
                forKey: reviewEligibleDateKey(userId: userId)
            )
        } catch {
            await recordTelemetry(
                eventType: "trial_extension_failed",
                productId: ProductID.trialSevenDays,
                status: "failed",
                reason: "server_error",
                details: error.localizedDescription
            )
        }
    }

    private func loadPromotion(userId: String) async {
        do {
            let hasPriorPurchase = await hasEverPurchased()
            let availability = try await CompanionAPIClient.shared.availablePromotion(
                userId: userId,
                language: AppLanguage.shared.code.rawValue,
                hasPriorPurchase: hasPriorPurchase
            )
            availablePromotion = availability.available ? availability.promotion : nil
        } catch {
            availablePromotion = nil
            await recordTelemetry(
                eventType: "promotion_load_failed",
                status: "failed",
                reason: "server_error",
                details: error.localizedDescription
            )
        }
    }

    private func refreshNativeReviewEligibility(userId: String) {
        guard !UserDefaults.standard.bool(forKey: reviewRequestedKey(userId: userId)) else {
            shouldRequestNativeReview = false
            return
        }
        guard let eligibleAt = UserDefaults.standard.object(
            forKey: reviewEligibleDateKey(userId: userId)
        ) as? Date else {
            shouldRequestNativeReview = false
            return
        }
        shouldRequestNativeReview = eligibleAt <= Date()
    }

    private func reviewEligibleDateKey(userId: String) -> String {
        "tradealert\(reviewEnvironmentSuffix).review.eligible-at.\(userId)"
    }

    private func reviewRequestedKey(userId: String) -> String {
        "tradealert\(reviewEnvironmentSuffix).review.requested.\(userId)"
    }

    private var reviewEnvironmentSuffix: String {
        AppConfig.apiEnvironment == .development ? ".development" : ""
    }

    private func hasEverPurchased() async -> Bool {
        for await result in Transaction.all {
            guard case .verified(let transaction) = result else { continue }
            guard Self.productIDs.contains(transaction.productID) else { continue }
            return true
        }
        return false
    }

    private func processOfferCodeTransaction(_ transaction: Transaction) async {
        guard transaction.offer?.type == .code else { return }
        guard let promotion = availablePromotion,
              promotion.productId == transaction.productID,
              let currentUserId else { return }
        do {
            try await CompanionAPIClient.shared.recordPromotionRedemption(
                userId: currentUserId,
                slug: promotion.slug,
                request: PromotionRedemptionRequest(
                    productId: transaction.productID,
                    transactionId: String(transaction.id),
                    originalTransactionId: String(transaction.originalID),
                    offerId: transaction.offer?.id,
                    environment: String(describing: transaction.environment)
                )
            )
            availablePromotion = nil
        } catch {
            message = AppLanguage.shared.text("promotion.error.server_confirmation")
            await recordTelemetry(
                eventType: "promotion_confirmation_failed",
                productId: transaction.productID,
                transaction: transaction,
                status: "failed",
                reason: "server_error",
                details: error.localizedDescription
            )
        }
    }

    private func recordTelemetry(
        eventType: String,
        product: Product? = nil,
        productId: String? = nil,
        transaction: Transaction? = nil,
        status: String? = nil,
        reason: String? = nil,
        details: String? = nil
    ) async {
        guard let currentUserId else { return }
        let device = CompanionDeviceSnapshot.current
        let request = IAPTelemetryRequest(
            eventType: eventType,
            productId: product?.id ?? productId ?? transaction?.productID,
            productType: product.map { String(describing: $0.type) },
            transactionId: transaction.map { String($0.id) },
            originalTransactionId: transaction.map { String($0.originalID) },
            offerId: transaction?.offer?.id,
            offerType: transaction?.offer.map { String(describing: $0.type) },
            storefront: transaction?.storefront.countryCode,
            currencyCode: nil,
            displayPrice: product?.displayPrice,
            price: product.map { NSDecimalNumber(decimal: $0.price).doubleValue },
            status: status,
            reason: reason,
            message: details,
            platform: "ios",
            environment: transaction.map { String(describing: $0.environment) }
                ?? AppConfig.apiEnvironment.rawValue,
            appVersion: device.appVersion,
            deviceModel: device.model,
            deviceOs: device.systemVersion,
            language: AppLanguage.shared.code.rawValue,
            occurredAt: ISO8601DateFormatter().string(from: Date())
        )
        try? await CompanionAPIClient.shared.recordIAPTelemetry(
            userId: currentUserId,
            request: request
        )
    }

    private func updateHasAccess() {
        hasAccess = legacyPaidAccess || !purchasedProductIDs.isEmpty || isTrialActive
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
