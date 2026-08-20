import SwiftUI

struct TrackedCompaniesView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @EnvironmentObject private var language: AppLanguage
    @EnvironmentObject private var purchases: PurchaseStore
    @State private var showPlansSheet = false

    var body: some View {
        List {
            Section {
                if model.favorites.isEmpty {
                    ContentUnavailableView(language.text("empty.no_tracked"), systemImage: "star")
                } else {
                    ForEach(model.favorites) { favorite in
                        NavigationLink {
                            CompanyDetailView(company: favorite.company)
                        } label: {
                            CompanyRow(company: favorite.company)
                        }
                    }
                    .onDelete { indexSet in
                        for index in indexSet {
                            let ticker = model.favorites[index].ticker
                            Task { await model.removeFavorite(ticker) }
                        }
                    }
                }
            }
        }
        .navigationTitle(language.text("title.tracked"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if model.isLoading {
                ToolbarItem(placement: .topBarTrailing) {
                    ProgressView()
                }
            }

            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    showPlansSheet = true
                } label: {
                    Text(language.text("action.plans"))
                        .font(.headline)
                }
            }
        }
        .sheet(isPresented: $showPlansSheet) {
            PurchasePlansSheetView()
                .presentationDetents([.large])
                .interactiveDismissDisabled(false)
        }
        .refreshable {
            await model.refreshFavorites()
        }
    }
}

struct PurchasePlansSheetView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @EnvironmentObject private var purchases: PurchaseStore
    @EnvironmentObject private var language: AppLanguage
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.title2)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .padding(.top, 12)
                .padding(.trailing, 16)
            }

            PaywallView()
        }
        .background(Color(.systemGroupedBackground))
        .task {
            await purchases.load(userId: model.userId)
        }
    }
}

struct CompanyRow: View {
    let company: Company

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(company.ticker)
                    .font(.headline)
                Spacer()
                if let price = company.lastPrice {
                    Text(price, format: .currency(code: "BRL"))
                        .font(.subheadline)
                        .monospacedDigit()
                }
            }

            Text(company.name)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            if let change = company.dailyChangePercent {
                Text(change / 100, format: .percent.precision(.fractionLength(2)))
                    .font(.caption)
                    .foregroundStyle(change >= 0 ? .green : .red)
                    .monospacedDigit()
            }
        }
        .padding(.vertical, 4)
    }
}
