import Foundation
import SwiftUI

struct CompanyDetailView: View {
    @EnvironmentObject private var model: AppModel
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
                VStack(alignment: .leading, spacing: 6) {
                    Text(company.ticker)
                        .font(.title3.bold())
                    Text(company.name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if let price = company.lastPrice {
                        Text(price, format: .currency(code: "BRL"))
                            .font(.headline)
                    }
                    if let change = company.dailyChangePercent {
                        Text(change / 100, format: .percent.precision(.fractionLength(2)))
                            .foregroundStyle(change >= 0 ? .green : .red)
                    }
                }

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
            company = try await APIClient.shared.quote(ticker: company.ticker)
        } catch {
            model.errorMessage = error.localizedDescription
        }
    }
}

struct AlertRow: View {
    let alert: AlertRule

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(alert.metric == .price ? "Price \(alert.operator.label)" : "Move \(alert.operator.label)")
                .font(.caption)
            Text(alert.metric == .price ? currency(alert.threshold) : percent(alert.threshold))
                .font(.headline)
            Text("\(alert.startTime)-\(alert.endTime) every \(alert.frequencyMinutes)m")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    private func currency(_ value: Double) -> String {
        value.formatted(.currency(code: "BRL"))
    }

    private func percent(_ value: Double) -> String {
        String(format: "%.2f%%", value)
    }
}
