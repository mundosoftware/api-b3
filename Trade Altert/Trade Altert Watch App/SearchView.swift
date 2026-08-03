import SwiftUI

struct SearchView: View {
    @EnvironmentObject private var model: AppModel
    @EnvironmentObject private var language: AppLanguage
    @State private var query = ""

    var body: some View {
        List {
            TextField(language.text("label.ticker"), text: $query)
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
                        Label(language.text("action.track"), systemImage: "star")
                    }
                }
            }
        }
        .navigationTitle(language.text("title.search"))
        .onChange(of: query) { _, value in
            Task { await model.search(value) }
        }
    }
}
