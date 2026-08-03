import SwiftUI

struct SearchView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @EnvironmentObject private var language: AppLanguage
    @State private var query = ""

    var body: some View {
        List {
            if query.trimmingCharacters(in: .whitespacesAndNewlines).count < 2 {
                ContentUnavailableView(language.text("empty.search"), systemImage: "magnifyingglass")
            } else if model.searchResults.isEmpty && !model.isLoading {
                ContentUnavailableView(language.text("empty.no_results"), systemImage: "magnifyingglass")
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
                            Label(language.text("action.track"), systemImage: "star")
                        }
                    }
                }
            }
        }
        .navigationTitle(language.text("title.search"))
        .searchable(text: $query, prompt: Text(language.text("prompt.search")))
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
