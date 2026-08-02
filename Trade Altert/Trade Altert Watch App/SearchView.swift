import SwiftUI

struct SearchView: View {
    @EnvironmentObject private var model: AppModel
    @State private var query = ""

    var body: some View {
        List {
            TextField("Ticker", text: $query)
                .onSubmit {
                    Task { await model.search(query) }
                }

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
        .navigationTitle("Search")
        .onChange(of: query) { _, value in
            Task { await model.search(value) }
        }
    }
}
