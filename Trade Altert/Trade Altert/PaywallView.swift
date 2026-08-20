import StoreKit
import SwiftUI

struct PaywallView: View {
    @EnvironmentObject private var purchases: PurchaseStore
    @EnvironmentObject private var language: AppLanguage
    @EnvironmentObject private var model: CompanionAppModel
    @State private var selectedProductID = PurchaseStore.ProductID.proYear
    @State private var showsOtherPlans = false
    @State private var showsTrialWaitAlert = false

    private var selectedProduct: Product? {
        guard selectedProductID != PurchaseStore.ProductID.trialSevenDays else {
            return nil
        }
        guard selectedProductID != PurchaseStore.ProductID.proYear || proYearProduct != nil else {
            return nil
        }
        return purchases.products.first { $0.id == selectedProductID }
    }

    private var proYearProduct: Product? {
        purchases.products.first { $0.id == PurchaseStore.ProductID.proYear }
    }

    private var otherProducts: [Product] {
        purchases.products.filter { $0.id != PurchaseStore.ProductID.proYear }
    }

    private var isTrialSelected: Bool {
        selectedProductID == PurchaseStore.ProductID.trialSevenDays
    }

    private var shouldShowServerTrialCard: Bool {
        !purchases.isTrialActive
    }

    private var canSelectServerTrial: Bool {
        purchases.trialStatus?.status != "pending"
    }

    private var trialTitleKey: String {
        purchases.trialStatus?.status == "expired" && (purchases.trialStatus?.requestCount ?? 0) > 0
            ? "paywall.trial.ended.title"
            : "paywall.trial.title"
    }

    private var paywallTitle: String {
        if purchases.isTrialActive {
            return language.text("paywall.trial.active.paywall_title")
        }

        if purchases.isTrialPending {
            return language.text("paywall.trial.pending.paywall_title")
        }

        return language.text(
            purchases.trialStatus?.status == "expired" && (purchases.trialStatus?.requestCount ?? 0) > 0
                ? "paywall.trial.ended.paywall_title"
                : "paywall.title"
        )
    }

    var body: some View {
        ScrollView(.vertical, showsIndicators: true) {
            VStack(alignment: .leading, spacing: 22) {
                header
                features

                plans

                if let message = purchases.message {
                    Label(message, systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }

                actions
            }
            .padding(24)
            .frame(maxWidth: 620)
            .frame(maxWidth: .infinity)
        }
        .background(Color(.systemGroupedBackground))
        .task {
            await purchases.load(userId: model.userId)
            selectedProductID = PurchaseStore.ProductID.proYear
        }
        .onChange(of: purchases.products.map(\.id)) { _, _ in
            guard selectedProductID == PurchaseStore.ProductID.trialSevenDays
                || purchases.products.contains(where: { $0.id == selectedProductID }) else {
                selectedProductID = PurchaseStore.ProductID.proYear
                return
            }
            if selectedProductID == PurchaseStore.ProductID.proYear {
                selectedProductID = PurchaseStore.ProductID.proYear
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            Image(systemName: "chart.line.uptrend.xyaxis")
                .font(.system(size: 42, weight: .semibold))
                .foregroundStyle(.green)

            Text(paywallTitle)
                .font(.largeTitle.bold())
                .multilineTextAlignment(.leading)

            Text(language.text("paywall.subtitle"))
                .font(.body)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 28)
    }

    private var features: some View {
        VStack(alignment: .leading, spacing: 12) {
            PaywallFeatureRow(
                icon: "bell.badge",
                title: language.text("paywall.feature.alerts.title"),
                subtitle: language.text("paywall.feature.alerts.subtitle")
            )
            PaywallFeatureRow(
                icon: "applewatch",
                title: language.text("paywall.feature.watch.title"),
                subtitle: language.text("paywall.feature.watch.subtitle")
            )
            PaywallFeatureRow(
                icon: "arrow.clockwise",
                title: language.text("paywall.feature.restore.title"),
                subtitle: language.text("paywall.feature.restore.subtitle")
            )
        }
    }

    private var plans: some View {
        VStack(alignment: .leading, spacing: 12) {
            if purchases.isLoadingProducts && purchases.products.isEmpty {
                ProgressView(language.text("paywall.loading"))
                    .frame(maxWidth: .infinity, minHeight: 120)
            } else if let proYearProduct {
                FeaturedTrialPlanCard(
                    product: proYearProduct,
                    isSelected: selectedProductID == proYearProduct.id,
                    title: language.text("paywall.enroll.title"),
                    subtitle: subtitle(for: proYearProduct),
                    badge: badge(for: proYearProduct),
                    primaryPrice: promotionalOffer(for: proYearProduct)?.displayPrice ?? proYearProduct.displayPrice,
                    priceCaption: promotionalOffer(for: proYearProduct) == nil
                        ? priceCaption(for: proYearProduct)
                        : promotionalPriceCaption(for: proYearProduct),
                    regularPriceText: regularPriceText(for: proYearProduct),
                    promotionalOfferText: promotionalOfferText(for: proYearProduct),
                    onSelect: {
                        selectedProductID = proYearProduct.id
                    }
                )

                Button {
                    withAnimation(.snappy) {
                        showsOtherPlans.toggle()
                        if !showsOtherPlans {
                            selectedProductID = proYearProduct.id
                        }
                    }
                } label: {
                    Label(
                        showsOtherPlans
                            ? language.text("paywall.other_plans.hide")
                            : language.text("paywall.other_plans.show"),
                        systemImage: showsOtherPlans ? "chevron.up" : "chevron.down"
                    )
                    .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)

                if showsOtherPlans {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(language.text("paywall.other_plans.title"))
                            .font(.headline)

                        ForEach(otherProducts, id: \.id) { product in
                            ProductOptionCard(
                                product: product,
                                isSelected: selectedProductID == product.id,
                                title: title(for: product),
                                subtitle: subtitle(for: product),
                                badge: badge(for: product),
                                priceCaption: priceCaption(for: product),
                                showsTrialTerms: product.subscription != nil,
                                onSelect: {
                                    selectedProductID = product.id
                                }
                            )
                        }

                        if shouldShowServerTrialCard {
                            TrialPlanCard(
                                isSelected: isTrialSelected,
                                isEnabled: canSelectServerTrial,
                                title: language.text(trialTitleKey),
                                subtitle: language.text("paywall.trial.subtitle"),
                                badge: language.text("paywall.badge.trial"),
                                message: purchases.isTrialPending
                                    ? language.text("paywall.trial.wait.message")
                                    : nil,
                                onSelect: {
                                    selectedProductID = PurchaseStore.ProductID.trialSevenDays
                                }
                            )
                        }
                    }
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }
            } else {
                MissingPrimaryPlanView(
                    loadedProductIDs: purchases.products.map(\.id)
                )

                if true {
                    Button {
                        withAnimation(.snappy) {
                            showsOtherPlans.toggle()
                        }
                    } label: {
                        Label(
                            showsOtherPlans
                                ? language.text("paywall.other_plans.hide")
                                : language.text("paywall.other_plans.show"),
                            systemImage: showsOtherPlans ? "chevron.up" : "chevron.down"
                        )
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)

                    if showsOtherPlans {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(language.text("paywall.other_plans.title"))
                                .font(.headline)

                            ForEach(otherProducts, id: \.id) { product in
                                ProductOptionCard(
                                    product: product,
                                    isSelected: selectedProductID == product.id,
                                    title: title(for: product),
                                    subtitle: subtitle(for: product),
                                    badge: badge(for: product),
                                    priceCaption: priceCaption(for: product),
                                    showsTrialTerms: product.subscription != nil,
                                    onSelect: {
                                        selectedProductID = product.id
                                    }
                                )
                            }

                            if shouldShowServerTrialCard {
                                TrialPlanCard(
                                    isSelected: isTrialSelected,
                                    isEnabled: canSelectServerTrial,
                                    title: language.text(trialTitleKey),
                                    subtitle: language.text("paywall.trial.subtitle"),
                                    badge: language.text("paywall.badge.trial"),
                                    message: purchases.isTrialPending
                                        ? language.text("paywall.trial.wait.message")
                                        : nil,
                                    onSelect: {
                                        selectedProductID = PurchaseStore.ProductID.trialSevenDays
                                    }
                                )
                            }
                        }
                        .transition(.opacity.combined(with: .move(edge: .top)))
                    }
                }
            }
        }
    }

    private var actions: some View {
        VStack(spacing: 12) {
            Button {
                Task {
                    if isTrialSelected && canSelectServerTrial {
                        let status = await purchases.requestTrial(userId: model.userId)
                        if status?.status == "pending" {
                            showsTrialWaitAlert = true
                        }
                    } else if let selectedProduct {
                        await purchases.purchase(selectedProduct)
                    }
                }
            } label: {
                HStack {
                    if purchases.isPurchasing {
                        ProgressView()
                    }
                    Text(primaryActionTitle)
                        .font(.headline)
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(
                (selectedProduct == nil && (!isTrialSelected || !canSelectServerTrial))
                    || purchases.isPurchasing
                    || purchases.isRestoring
            )

            Button {
                Task {
                    await purchases.restorePurchases()
                }
            } label: {
                HStack {
                    if purchases.isRestoring {
                        ProgressView()
                    }
                    Text(language.text("paywall.restore"))
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
            .disabled(purchases.isPurchasing || purchases.isRestoring)

            Link(language.text("paywall.terms_privacy"), destination: PurchaseStore.privacyAndTermsURL)
                .font(.footnote)
        }
        .alert(language.text("paywall.trial.wait.title"), isPresented: $showsTrialWaitAlert) {
            Button(language.text("action.ok"), role: .cancel) {}
        } message: {
            Text(language.text("paywall.trial.wait.message"))
        }
    }

    private var primaryActionTitle: String {
        if isTrialSelected {
            return language.text("paywall.trial.cta")
        }
        guard let selectedProduct else {
            return purchases.isTrialActive
                ? language.text("paywall.subscribe")
                : language.text("paywall.enroll.cta_trial")
        }

        if selectedProduct.id == PurchaseStore.ProductID.lifetimeUnlock {
            return language.text("paywall.buy_lifetime")
        }

        if selectedProduct.id == PurchaseStore.ProductID.proYear {
            if purchases.isTrialActive {
                return language.text("paywall.enroll.cta_subscribe")
            }

            return purchases.isIntroOfferEligible(for: selectedProduct)
                ? language.text("paywall.enroll.cta_trial")
                : language.text("paywall.enroll.cta_subscribe")
        }

        if purchases.isTrialActive {
            return language.text("paywall.subscribe")
        }

        if purchases.isIntroOfferEligible(for: selectedProduct) {
            return language.text("paywall.start_trial")
        }

        return language.text("paywall.subscribe")
    }

    private func title(for product: Product) -> String {
        switch product.id {
        case PurchaseStore.ProductID.proYear:
            return language.text("paywall.product.pro_year.title")
        case PurchaseStore.ProductID.proMonth:
            return language.text("paywall.product.pro_month.title")
        case PurchaseStore.ProductID.lifetimeUnlock:
            return language.text("paywall.product.lifetime.title")
        default:
            return product.displayName
        }
    }

    private func subtitle(for product: Product) -> String {
        switch product.id {
        case PurchaseStore.ProductID.proYear:
            if !purchases.isTrialActive && purchases.isIntroOfferEligible(for: product) {
                return String(format: language.text("paywall.product.pro_year.trial_subtitle"), product.displayPrice)
            }
            return String(format: language.text("paywall.product.pro_year.subtitle"), product.displayPrice)
        case PurchaseStore.ProductID.proMonth:
            return String(format: language.text("paywall.product.pro_month.subtitle"), product.displayPrice)
        case PurchaseStore.ProductID.lifetimeUnlock:
            return language.text("paywall.product.lifetime.subtitle")
        default:
            return product.description
        }
    }

    private func promotionalOfferText(for product: Product) -> String? {
        guard let offer = promotionalOffer(for: product) else {
            return nil
        }

        switch offer.paymentMode {
        case .freeTrial:
            return String(format: language.text("paywall.promo.free_trial"), offerPeriodText(offer))
        case .payUpFront:
            return String(format: language.text("paywall.promo.pay_up_front"), offer.displayPrice, offerPeriodText(offer))
        case .payAsYouGo:
            return String(format: language.text("paywall.promo.pay_as_you_go"), offer.displayPrice, offerPeriodText(offer))
        default:
            return String(format: language.text("paywall.promo.generic"), offer.displayPrice)
        }
    }

    private func promotionalOffer(for product: Product) -> Product.SubscriptionOffer? {
        product.subscription?.promotionalOffers.first
    }

    private func promotionalPriceCaption(for product: Product) -> String {
        guard let offer = promotionalOffer(for: product) else {
            return priceCaption(for: product)
        }

        return offerPeriodText(offer)
    }

    private func regularPriceText(for product: Product) -> String? {
        guard promotionalOffer(for: product) != nil else {
            return nil
        }

        return String(format: language.text("paywall.promo.regular_price"), product.displayPrice)
    }

    private func offerPeriodText(_ offer: Product.SubscriptionOffer) -> String {
        let period = offer.period
        let totalValue = period.value * offer.periodCount

        switch period.unit {
        case .day:
            return unitText(value: totalValue, singularKey: "paywall.period.day", pluralKey: "paywall.period.days")
        case .week:
            return unitText(value: totalValue, singularKey: "paywall.period.week", pluralKey: "paywall.period.weeks")
        case .month:
            return unitText(value: totalValue, singularKey: "paywall.period.month", pluralKey: "paywall.period.months")
        case .year:
            return unitText(value: totalValue, singularKey: "paywall.period.year", pluralKey: "paywall.period.years")
        @unknown default:
            return String(totalValue)
        }
    }

    private func unitText(value: Int, singularKey: String, pluralKey: String) -> String {
        let key = value == 1 ? singularKey : pluralKey
        return String(format: language.text(key), value)
    }

    private func badge(for product: Product) -> String? {
        switch product.id {
        case PurchaseStore.ProductID.proYear:
            return !purchases.isTrialActive && purchases.isIntroOfferEligible(for: product)
                ? language.text("paywall.badge.trial")
                : language.text("paywall.badge.best_value")
        case PurchaseStore.ProductID.lifetimeUnlock:
            return language.text("paywall.badge.once")
        default:
            return nil
        }
    }

    private func priceCaption(for product: Product) -> String {
        switch product.id {
        case PurchaseStore.ProductID.proYear:
            return language.text("paywall.price.year")
        case PurchaseStore.ProductID.proMonth:
            return language.text("paywall.price.month")
        case PurchaseStore.ProductID.lifetimeUnlock:
            return language.text("paywall.price.once")
        default:
            return ""
        }
    }
}

private struct MissingPrimaryPlanView: View {
    @EnvironmentObject private var language: AppLanguage

    let loadedProductIDs: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.title3)
                    .foregroundStyle(.orange)
                    .frame(width: 28)

                VStack(alignment: .leading, spacing: 4) {
                    Text(language.text("paywall.pro_year_unavailable.title"))
                        .font(.headline)

                    Text(language.text("paywall.pro_year_unavailable.message"))
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)

                    #if DEBUG
                    if !loadedProductIDs.isEmpty {
                        Text(String(format: language.text("paywall.loaded_products"), loadedProductIDs.joined(separator: ", ")))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    #endif
                }
            }
        }
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.orange.opacity(0.5), lineWidth: 1)
        }
    }
}

private struct FeaturedTrialPlanCard: View {
    @EnvironmentObject private var language: AppLanguage

    let product: Product
    let isSelected: Bool
    let title: String
    let subtitle: String
    let badge: String?
    let primaryPrice: String
    let priceCaption: String
    let regularPriceText: String?
    let promotionalOfferText: String?
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                        .font(.title3)
                        .foregroundStyle(isSelected ? .green : .secondary)

                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 8) {
                            Text(title)
                                .font(.title3.bold())
                                .foregroundStyle(.primary)

                            if let badge {
                                Text(badge)
                                    .font(.caption.bold())
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(.green.opacity(0.16), in: Capsule())
                                    .foregroundStyle(.green)
                            }
                        }

                        Text(subtitle)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)

                        if let promotionalOfferText {
                            Label(promotionalOfferText, systemImage: "tag")
                                .font(.subheadline.bold())
                                .foregroundStyle(.green)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }

                    Spacer(minLength: 8)
                }

                HStack(alignment: .firstTextBaseline) {
                    Text(primaryPrice)
                        .font(.title2.bold())
                        .monospacedDigit()
                        .foregroundStyle(.primary)
                    Text(priceCaption)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Spacer()
                }

                if let regularPriceText {
                    Text(regularPriceText)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Divider()

                HStack(spacing: 6) {
                    Image(systemName: "doc.text")
                        .foregroundStyle(.secondary)
                    Link(language.text("paywall.terms_privacy"), destination: PurchaseStore.privacyAndTermsURL)
                    Spacer()
                }
                .font(.footnote)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(16)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8)
                .stroke(isSelected ? Color.green : Color(.separator), lineWidth: isSelected ? 2 : 1)
        }
    }
}

private struct ProductOptionCard: View {
    @EnvironmentObject private var language: AppLanguage

    let product: Product
    let isSelected: Bool
    let title: String
    let subtitle: String
    let badge: String?
    let priceCaption: String
    let showsTrialTerms: Bool
    let onSelect: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Button(action: onSelect) {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                        .font(.title3)
                        .foregroundStyle(isSelected ? .green : .secondary)

                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 8) {
                            Text(title)
                                .font(.headline)
                                .foregroundStyle(.primary)

                            if let badge {
                                Text(badge)
                                    .font(.caption.bold())
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(.green.opacity(0.14), in: Capsule())
                                    .foregroundStyle(.green)
                            }
                        }

                        Text(subtitle)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    Spacer(minLength: 8)

                    VStack(alignment: .trailing, spacing: 2) {
                        Text(product.displayPrice)
                            .font(.headline)
                            .monospacedDigit()
                            .foregroundStyle(.primary)
                        Text(priceCaption)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if showsTrialTerms {
                Divider()
                HStack(spacing: 6) {
                    Image(systemName: "doc.text")
                        .foregroundStyle(.secondary)
                    Link(language.text("paywall.terms_privacy"), destination: PurchaseStore.privacyAndTermsURL)
                    Spacer()
                }
                .font(.footnote)
            }
        }
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8)
                .stroke(isSelected ? Color.green : Color(.separator), lineWidth: isSelected ? 2 : 1)
        }
    }
}

private struct PaywallFeatureRow: View {
    let icon: String
    let title: String
    let subtitle: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(.green)
                .frame(width: 28)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline.bold())
                Text(subtitle)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

private struct TrialPlanCard: View {
    let isSelected: Bool
    let isEnabled: Bool
    let title: String
    let subtitle: String
    let badge: String
    let message: String?
    let onSelect: () -> Void

    private var showsSelectedState: Bool {
        isSelected && isEnabled
    }

    var body: some View {
        Button(action: onSelect) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: showsSelectedState ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(showsSelectedState ? .green : .secondary)

                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        Text(title)
                            .font(.headline)
                            .foregroundStyle(.primary)

                        Text(badge)
                            .font(.caption.bold())
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(.green.opacity(0.14), in: Capsule())
                            .foregroundStyle(.green)
                    }

                    Text(subtitle)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)

                    if let message {
                        Text(message)
                            .font(.footnote)
                            .foregroundStyle(.orange)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                Spacer(minLength: 8)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!isEnabled)
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 8))
        .overlay {
            RoundedRectangle(cornerRadius: 8)
                .stroke(
                    showsSelectedState ? Color.green : Color(.separator),
                    lineWidth: showsSelectedState ? 2 : 1
                )
        }
    }
}

struct StoreAccessLoadingView: View {
    @EnvironmentObject private var language: AppLanguage

    var body: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text(language.text("paywall.checking_access"))
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.systemGroupedBackground))
    }
}
