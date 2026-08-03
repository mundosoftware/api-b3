import SwiftUI

struct SearchView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @State private var query = ""

    var body: some View {
        List {
            if query.trimmingCharacters(in: .whitespacesAndNewlines).count < 2 {
                ContentUnavailableView("Search B3 Tickers", systemImage: "magnifyingglass")
            } else if model.searchResults.isEmpty && !model.isLoading {
                ContentUnavailableView("No Results", systemImage: "magnifyingglass")
            } else {
                ForEach(model.searchResults) { company in
                    NavigationLink {
                        CompanyDetailView(company: company)
                    } label: {
                        CompanyRow(company: company)
                    }
                    .swipeActions {
                        Button {
                            Task { await model.addFavorite(company.ticker) }
                        } label: {
                            Label("Track", systemImage: "star")
                        }
                    }
                }
            }
        }
        .navigationTitle("Search")
        .searchable(text: $query, prompt: "Ticker or company")
        .onSubmit(of: .search) {
            Task { await model.search(query) }
        }
        .onChange(of: query) { _, value in
            Task { await model.search(value) }
        }
        .toolbar {
            if model.isLoading {
                ProgressView()
            }
        }
    }
}
