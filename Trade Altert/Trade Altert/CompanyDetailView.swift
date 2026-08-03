import SwiftUI

struct CompanyDetailView: View {
    @EnvironmentObject private var model: CompanionAppModel
    @State private var company: Company

    init(company: Company) {
        _company = State(initialValue: company)
    }

    private var isFavorite: Bool {
        model.favorites.contains { $0.ticker == company.ticker }
    }

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 8) {
                    Text(company.ticker)
                        .font(.title2.bold())
                    Text(company.name)
                        .foregroundStyle(.secondary)
                    if let price = company.lastPrice {
                        Text(price, format: .currency(code: "BRL"))
                            .font(.title3)
                            .monospacedDigit()
                    }
                    if let change = company.dailyChangePercent {
                        Text(change / 100, format: .percent.precision(.fractionLength(2)))
                            .foregroundStyle(change >= 0 ? .green : .red)
                            .monospacedDigit()
                    }
                }
                .padding(.vertical, 4)

                Button {
                    Task {
                        if isFavorite {
                            await model.removeFavorite(company.ticker)
                        } else {
                            await model.addFavorite(company.ticker)
                        }
                    }
                } label: {
                    Label(isFavorite ? "Untrack" : "Track", systemImage: isFavorite ? "star.fill" : "star")
                }
            }

            Section("Alerts") {
                NavigationLink {
                    AlertEditorView(ticker: company.ticker, currentPrice: company.lastPrice)
                } label: {
                    Label("New Alert", systemImage: "bell.badge")
                }

                ForEach(model.alertsByTicker[company.ticker] ?? []) { alert in
                    AlertRow(alert: alert)
                        .swipeActions {
                            Button(role: .destructive) {
                                Task { await model.deleteAlert(alert) }
                            } label: {
                                Label("Delete", systemImage: "trash")
                            }
                        }
                }
            }
        }
        .navigationTitle(company.ticker)
        .task {
            await reload()
            await model.loadAlerts(ticker: company.ticker)
        }
        .refreshable {
            await reload()
            await model.loadAlerts(ticker: company.ticker)
        }
    }

    private func reload() async {
        do {
            company = try await CompanionAPIClient.shared.quote(ticker: company.ticker)
        } catch {
            model.errorMessage = error.localizedDescription
        }
    }
}

struct AlertRow: View {
    let alert: AlertRule

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(alert.metric == .price ? "Price \(alert.operator.label)" : "Move \(alert.operator.label)")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(alert.metric == .price ? currency(alert.threshold) : percent(alert.threshold))
                .font(.headline)
            Text("\(alert.startTime)-\(alert.endTime) every \(alert.frequencyMinutes)m")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 3)
    }

    private func currency(_ value: Double) -> String {
        value.formatted(.currency(code: "BRL"))
    }

    private func percent(_ value: Double) -> String {
        String(format: "%.2f%%", value)
    }
}
