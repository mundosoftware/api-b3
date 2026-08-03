import SwiftUI

struct TrackedCompaniesView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @EnvironmentObject private var language: AppLanguage

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
        .toolbar {
            if model.isLoading {
                ProgressView()
            }
        }
        .refreshable {
            await model.refreshFavorites()
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
