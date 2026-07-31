import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        NavigationStack {
            List {
                NavigationLink {
                    SearchView()
                } label: {
                    Label("Search", systemImage: "magnifyingglass")
                }

                Section("Tracked") {
                    if model.favorites.isEmpty {
                        Text("No tickers")
                            .foregroundStyle(.secondary)
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
            .navigationTitle("B3 Watch")
            .toolbar {
                if model.isLoading {
                    ProgressView()
                }
            }
            .refreshable {
                await model.refreshFavorites()
            }
            .alert("Error", isPresented: Binding(
                get: { model.errorMessage != nil },
                set: { if !$0 { model.errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(model.errorMessage ?? "")
            }
        }
    }
}

struct CompanyRow: View {
    let company: Company

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(company.ticker)
                    .font(.headline)
                Spacer()
                if let price = company.lastPrice {
                    Text(price, format: .currency(code: "BRL"))
                        .font(.caption)
                }
            }
            Text(company.name)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            if let change = company.dailyChangePercent {
                Text(change / 100, format: .percent.precision(.fractionLength(2)))
                    .font(.caption2)
                    .foregroundStyle(change >= 0 ? .green : .red)
            }
        }
    }
}
